"""Database-backed worker for persisted AI schedules."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from threading import Event, Thread

from api.main import Services, make_agent, persisted_history, queue_pending_artifacts
from agent_core.artifacts import ArtifactService
from agent_core.config import load_settings
from agent_core.knowledge import KnowledgeService
from agent_core.library import LibraryService
from agent_core.media import MediaService
from agent_core.file_storage import FileStorageService
from agent_core.memory import MemoryService
from agent_core.ollama import OllamaCatalog
from agent_core.personalization import PersonalizationService
from agent_core.notifications import EmailNotificationService, public_chat_url, schedule_run_email
from agent_core.web_search import WebSearchService, WebSourceUnavailable
from agent_core.google_workspace import GOOGLE_WORKSPACE_SLUG, GoogleWorkspaceExecutor, GoogleWorkspaceService
from agent_core.github_app import GITHUB_SLUG, GitHubAppExecutor, GitHubAppService
from agent_core.auth import AuthService
from agent_core.credentials import UserCredentialService
from agent_core.plugin_execution import EXECUTORS, connected_read_tools
from agent_core.storage import AuthRepository, BackgroundJobRepository, Chat, ChatRepository, ConnectorRepository, Database, MediaRepository, ModelRegistryRepository, Schedule, ScheduleRepository, WorkspaceRepository, current_user_id, current_workspace_id

RETRY_DELAYS_MINUTES = (5, 15, 30)
HEARTBEAT_SECONDS = 60


class RunHeartbeat:
    """Keep a long run marked alive so stale recovery never reclaims it.

    Without this, a run slower than the recovery timeout is marked failed while
    still working: the user then sees a failure, may start a duplicate run, and
    the original still finishes and emails. The beat runs on its own thread
    because `execute()` blocks inside a single provider call.
    """

    def __init__(self, runs: ScheduleRepository, run_id: str, interval: float = HEARTBEAT_SECONDS):
        self.runs, self.run_id, self.interval = runs, run_id, interval
        self._stop = Event()
        self._thread = Thread(target=self._beat, daemon=True)

    def _beat(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.runs.touch_run(self.run_id)
            except Exception:  # noqa: BLE001 - a missed beat must never break the run
                pass

    def __enter__(self) -> "RunHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_exc_info) -> None:
        self._stop.set()


class ScheduleWorker:
    def __init__(self, app_services: Services):
        self.services = app_services
        self.runs = ScheduleRepository(app_services.chats.database)

    def run_due(self, now: datetime | None = None) -> int:
        current_time = now or datetime.now(UTC)
        self.runs.recover_stale_runs(current_time)
        claimed = [(schedule, run, False) for schedule, run in self.runs.claim_due(current_time)]
        claimed.extend((schedule, run, True) for schedule, run in self.runs.claim_due_retries(current_time))
        for schedule, run, prompt_persisted in claimed:
            self.execute(schedule, run.id, prompt_persisted=prompt_persisted)
        return len(claimed)

    def start_manual(self, schedule_id: str, now: datetime | None = None) -> tuple[Schedule, Chat, str] | None:
        """Claim and prepare a manual run before the API redirects to its chat."""
        claimed = self.runs.claim_manual(schedule_id, now or datetime.now(UTC))
        if claimed is None:
            return None
        schedule, run = claimed
        chat = self.prepare_chat_for_run(schedule)
        return schedule, chat, run.id

    def ensure_chat(self, schedule: Schedule) -> Chat:
        chat = self.services.chats.get(schedule.chat_id) if schedule.chat_id else None
        if chat is not None:
            if schedule.provider and schedule.model and (chat.provider != schedule.provider or chat.model != schedule.model):
                return self.services.chats.update(chat.id, provider=schedule.provider, model=schedule.model) or chat
            return chat
        provider = schedule.provider or self.services.settings.provider
        model = schedule.model or self.services.settings.active_model
        chat = self.services.chats.create(provider, model)
        chat = self.services.chats.update(chat.id, title=f"Lịch: {schedule.title}") or chat
        self.runs.attach_chat(schedule.id, chat.id)
        return chat

    def prepare_chat_for_run(self, schedule: Schedule) -> Chat:
        """Persist the scheduled prompt once so a queued run never opens an empty chat."""
        chat = self.ensure_chat(schedule)
        history = self.services.chats.history(chat.id)
        history.append({
            "role": "user",
            "content": schedule.prompt or schedule.title,
            "created_at": datetime.now(UTC).isoformat(),
        })
        self.services.chats.replace_history(chat.id, history)
        return chat

    @staticmethod
    def _is_transient_error(error: Exception) -> bool:
        # Missing web sources are never retried: a Tavily error text can contain
        # "timeout" and would otherwise be mistaken for a provider outage.
        if isinstance(error, WebSourceUnavailable):
            return False
        message = str(error).lower()
        return any(marker in message for marker in ("503", "unavailable", "timeout", "timed out", "temporarily", "connection reset"))

    @staticmethod
    def _final_failure_message(chat: Chat, transient: bool, error: Exception | None = None) -> str:
        if isinstance(error, WebSourceUnavailable):
            return (
                f"Lịch trình chưa hoàn tất vì không lấy được nguồn web mới: {error}. "
                "Bản tin không được tạo để tránh nội dung thiếu nguồn. Hãy kiểm tra cấu hình tìm web rồi bấm Chạy ngay."
            )
        if transient:
            return (
                f"Lịch trình chưa hoàn tất vì {chat.provider} / {chat.model} vẫn tạm thời không khả dụng "
                f"sau {len(RETRY_DELAYS_MINUTES)} lần thử lại. Bạn có thể bấm Chạy ngay hoặc đổi model rồi thử lại."
            )
        return "Lịch trình chưa hoàn tất do lỗi không thể tự thử lại. Xem Lần chạy gần đây để kiểm tra và bấm Chạy ngay sau khi đã xử lý."

    @staticmethod
    def _grounded_prompt(prompt: str, context: str) -> str:
        return (
            f"{prompt}\n\n---\nNGUỒN WEB MỚI (bắt buộc dùng, chỉ trích dẫn các URL dưới đây):\n{context}\n---\n"
            "Chỉ tổng hợp từ các nguồn trên; không bổ sung thông tin từ kiến thức sẵn có."
        )

    @classmethod
    def _grounded_history(cls, history: list[dict], prompt: str, web_sources: dict) -> list[dict]:
        """Copy the history with sources folded into the pending user message."""
        if not history or history[-1].get("role") != "user":
            return history
        grounded = {**history[-1], "content": cls._grounded_prompt(prompt, web_sources["context"])}
        return [*history[:-1], grounded]

    def notify(self, schedule: Schedule, run_id: str, chat: Chat, summary: str | None) -> None:
        """Send the completion email after the run is already durably finished."""
        if not schedule.notify_email:
            return
        try:
            email = self.services.email
            recipient = getattr(self.services.auth.repository.get_user(schedule.user_id), "email", None) if schedule.user_id else None
            if not email.enabled or not recipient:
                reason = "SMTP chưa được cấu hình." if not email.enabled else "Tài khoản chủ lịch trình không có email."
                self.runs.record_email(run_id, status="skipped", error=reason)
                return
            subject, body = schedule_run_email(
                schedule.title,
                datetime.now(UTC),
                summary,
                public_chat_url(self.services.settings.app_web_url, chat.id),
            )
            email.send(recipient, subject, body)
        except Exception as exc:  # noqa: BLE001 - delivery must never fail a finished run
            self.runs.record_email(run_id, status="failed", error=str(exc))
            return
        self.runs.record_email(run_id, status="sent")

    def execute(self, schedule: Schedule, run_id: str, prompt_persisted: bool = False) -> None:
        user_token = current_user_id.set(schedule.user_id)
        workspace_token = current_workspace_id.set(schedule.workspace_id)
        try:
            with RunHeartbeat(self.runs, run_id):
                self._run_turn(schedule, run_id, prompt_persisted)
        finally:
            current_workspace_id.reset(workspace_token)
            current_user_id.reset(user_token)

    def _run_turn(self, schedule: Schedule, run_id: str, prompt_persisted: bool) -> None:
        try:
            self._complete_turn(schedule, run_id, prompt_persisted)
        except Exception as exc:  # noqa: BLE001
            self._handle_turn_failure(schedule, run_id, exc)

    def _complete_turn(self, schedule: Schedule, run_id: str, prompt_persisted: bool) -> None:
        chat = self.ensure_chat(schedule) if prompt_persisted else self.prepare_chat_for_run(schedule)
        prompt = schedule.prompt or schedule.title
        try:
            memory_context = self.services.memory.recall(prompt, chat.id, chat.context_source_chat_id)
        except Exception:  # noqa: BLE001
            memory_context = ""
        full_history = self.services.chats.history(chat.id)
        web_sources = self.services.web_search.require_sources(prompt) if schedule.require_web_source else None
        agent = make_agent(
            self.services, chat, memory_context=memory_context,
            plugin_tools=connected_read_tools(self.services.workspace.list_plugins()),
            history=self._grounded_history(full_history, prompt, web_sources) if web_sources else full_history,
            allow_schedule_proposals=False,
        )
        initial_history_length = len(agent.history)
        result = agent.run(prompt, append_user_message=False)
        if result.content_blocks:
            agent.history[-1]["content_blocks"] = result.content_blocks
        saved_history = persisted_history(full_history, agent.history, initial_history_length)
        for item in saved_history[len(full_history):]:
            item.setdefault("created_at", datetime.now(UTC).isoformat())
        if web_sources and saved_history:
            saved_history[-1]["sources"] = web_sources["sources"]
        self.services.chats.replace_history(chat.id, saved_history)
        self.services.chats.set_unread(chat.id, True)
        BackgroundJobRepository(self.services.chats.database).enqueue("memory_index", {"chat_id": chat.id})
        summary = result.text[:500]
        self.runs.finish(run_id, summary=summary)
        try:
            self.notify(schedule, run_id, chat, summary)
        except Exception:  # noqa: BLE001 - the run is already finished; never reopen it
            pass

    def _handle_turn_failure(self, schedule: Schedule, run_id: str, error: Exception) -> None:
        transient = self._is_transient_error(error)
        try:
            chat = self.ensure_chat(schedule)
            if transient and self.runs.schedule_retry(run_id, "Provider tạm thời không khả dụng; đang chờ tự thử lại.", RETRY_DELAYS_MINUTES) is not None:
                return
            history = self.services.chats.history(chat.id)
            history.append({"role": "assistant", "content": self._final_failure_message(chat, transient, error), "created_at": datetime.now(UTC).isoformat()})
            self.services.chats.replace_history(chat.id, history)
            self.services.chats.set_unread(chat.id, True)
        except Exception:  # noqa: BLE001 - report the original failure even if history persistence fails
            pass
        if isinstance(error, WebSourceUnavailable):
            run_error = f"Không lấy được nguồn web mới: {error}"
        elif transient:
            run_error = "Provider tạm thời không khả dụng; đã hết số lần tự thử lại."
        else:
            run_error = "Lỗi không thể tự thử lại; xem cấu hình provider và thử lại."
        self.runs.finish(run_id, error=run_error)


def build_worker() -> ScheduleWorker:
    settings = load_settings()
    database = Database(settings.database_url)
    media_storage = FileStorageService(settings.media_dir, settings.imagekit_private_key, settings.imagekit_url_endpoint)
    knowledge_storage = FileStorageService(settings.knowledge_dir, settings.imagekit_private_key, settings.imagekit_url_endpoint)
    media = MediaService(MediaRepository(database), settings.media_dir, media_storage)
    auth_repository = AuthRepository(database)
    model_registry = ModelRegistryRepository(database)
    model_registry.seed(settings.provider_models)
    connectors = ConnectorRepository(database)
    google_workspace = GoogleWorkspaceService(connectors, settings)
    github = GitHubAppService(connectors, settings)
    EXECUTORS[GOOGLE_WORKSPACE_SLUG] = GoogleWorkspaceExecutor(google_workspace)
    EXECUTORS[GITHUB_SLUG] = GitHubAppExecutor(github)
    services = Services(
        settings=settings,
        chats=ChatRepository(database),
        knowledge=KnowledgeService(database, settings.knowledge_dir, settings.embedding_model, knowledge_storage),
        media=media,
        library=LibraryService(database, settings.media_dir, media_storage),
        artifacts=ArtifactService(database, settings.media_dir, settings.embedding_model, media_storage),
        memory=MemoryService(database, settings.embedding_model),
        workspace=WorkspaceRepository(database),
        google_workspace=google_workspace,
        github=github,
        auth=AuthService(auth_repository, settings),
        model_registry=model_registry,
        credentials=UserCredentialService(auth_repository, settings),
        personalization=PersonalizationService(database),
        web_search=WebSearchService(settings.tavily_api_key),
        email=EmailNotificationService(settings),
        ollama=OllamaCatalog(settings.ollama_base_url),
    )
    queue_pending_artifacts(services)
    return ScheduleWorker(services)


def main() -> None:
    worker = build_worker()
    while True:
        worker.run_due()
        time.sleep(60)


if __name__ == "__main__":
    main()
