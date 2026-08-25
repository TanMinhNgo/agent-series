"""Database-backed worker for persisted AI schedules."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from api.main import Services, make_agent, persisted_history, queue_pending_artifacts
from agent_core.artifacts import ArtifactService
from agent_core.config import load_settings
from agent_core.knowledge import KnowledgeService
from agent_core.library import LibraryService
from agent_core.media import MediaService
from agent_core.memory import MemoryService
from agent_core.ollama import OllamaCatalog
from agent_core.personalization import PersonalizationService
from agent_core.web_search import WebSearchService
from agent_core.google_workspace import GoogleWorkspaceService
from agent_core.auth import AuthService
from agent_core.credentials import UserCredentialService
from agent_core.plugin_execution import connected_read_tools
from agent_core.storage import AuthRepository, BackgroundJobRepository, Chat, ChatRepository, ConnectorRepository, Database, MediaRepository, ModelRegistryRepository, Schedule, ScheduleRepository, WorkspaceRepository, current_user_id


class ScheduleWorker:
    def __init__(self, app_services: Services):
        self.services = app_services
        self.runs = ScheduleRepository(app_services.chats.database)

    def run_due(self, now: datetime | None = None) -> int:
        current_time = now or datetime.now(UTC)
        self.runs.recover_stale_runs(current_time)
        claimed = self.runs.claim_due(current_time)
        for schedule, run in claimed:
            self.execute(schedule, run.id)
        return len(claimed)

    def run_now(self, schedule_id: str, now: datetime | None = None) -> bool:
        claimed = self.runs.claim_manual(schedule_id, now or datetime.now(UTC))
        if claimed is None:
            return False
        schedule, run = claimed
        self.execute(schedule, run.id)
        return True

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
            return chat
        chat = self.services.chats.create(self.services.settings.provider, self.services.settings.active_model)
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
        message = str(error).lower()
        return any(marker in message for marker in ("503", "unavailable", "timeout", "timed out", "temporarily", "connection reset"))

    def execute(self, schedule: Schedule, run_id: str, prompt_persisted: bool = False) -> None:
        user_token = current_user_id.set(schedule.user_id)
        try:
            # ContextVar values do not cross into worker threads. Restore the
            # owner so user-scoped repositories can access this schedule's chat.
            # An old ownerless linked chat is safely replaced on its next run.
            chat = self.ensure_chat(schedule) if prompt_persisted else self.prepare_chat_for_run(schedule)
            try:
                memory_context = self.services.memory.recall(
                    schedule.prompt or schedule.title, chat.id, chat.context_source_chat_id
                )
            except Exception:  # noqa: BLE001
                memory_context = ""
            plugin_tools = connected_read_tools(self.services.workspace.list_plugins())
            full_history = self.services.chats.history(chat.id)
            prompt = schedule.prompt or schedule.title
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    agent = make_agent(
                        self.services,
                        chat,
                        memory_context=memory_context,
                        plugin_tools=plugin_tools,
                        history=full_history,
                        allow_schedule_proposals=False,
                    )
                    initial_history_length = len(agent.history)
                    result = agent.run(prompt, append_user_message=False)
                    break
                except Exception as exc:  # noqa: BLE001 - retry only transient provider failures
                    last_error = exc
                    if attempt == 2 or not self._is_transient_error(exc):
                        raise
                    time.sleep(2 ** (attempt + 1))
            else:  # pragma: no cover - loop either breaks or raises
                raise last_error or RuntimeError("Không thể chạy lịch trình.")
            if result.content_blocks:
                agent.history[-1]["content_blocks"] = result.content_blocks
            saved_history = persisted_history(full_history, agent.history, initial_history_length)
            turn_created_at = datetime.now(UTC).isoformat()
            for item in saved_history[len(full_history):]:
                item.setdefault("created_at", turn_created_at)
            self.services.chats.replace_history(chat.id, saved_history)
            self.services.chats.set_unread(chat.id, True)
            BackgroundJobRepository(self.services.chats.database).enqueue("memory_index", {"chat_id": chat.id})
            self.runs.finish(run_id, summary=result.text[:500])
        except Exception as exc:  # noqa: BLE001
            try:
                chat = self.ensure_chat(schedule)
                history = self.services.chats.history(chat.id)
                history.append({
                    "role": "assistant",
                    "content": "Lịch trình chưa hoàn tất do provider đang tạm thời không khả dụng. Bạn có thể xem chi tiết trong Lần chạy gần đây và bấm Chạy ngay để thử lại.",
                    "created_at": datetime.now(UTC).isoformat(),
                })
                self.services.chats.replace_history(chat.id, history)
                self.services.chats.set_unread(chat.id, True)
            except Exception:
                pass
            self.runs.finish(run_id, error=str(exc))
        finally:
            current_user_id.reset(user_token)


def build_worker() -> ScheduleWorker:
    settings = load_settings()
    database = Database(settings.database_url)
    media = MediaService(MediaRepository(database), settings.media_dir)
    auth_repository = AuthRepository(database)
    model_registry = ModelRegistryRepository(database)
    model_registry.seed(settings.provider_models)
    services = Services(
        settings=settings,
        chats=ChatRepository(database),
        knowledge=KnowledgeService(database, settings.knowledge_dir, settings.embedding_model),
        media=media,
        library=LibraryService(database, settings.media_dir),
        artifacts=ArtifactService(database, settings.media_dir, settings.embedding_model),
        memory=MemoryService(database, settings.embedding_model),
        workspace=WorkspaceRepository(database),
        google_workspace=GoogleWorkspaceService(ConnectorRepository(database), settings),
        auth=AuthService(auth_repository, settings),
        model_registry=model_registry,
        credentials=UserCredentialService(auth_repository, settings),
        personalization=PersonalizationService(database),
        web_search=WebSearchService(settings.tavily_api_key),
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
