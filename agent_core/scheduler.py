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
from agent_core.plugin_execution import connected_read_tools
from agent_core.storage import BackgroundJobRepository, ChatRepository, Database, MediaRepository, Schedule, ScheduleRepository, WorkspaceRepository


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

    def execute(self, schedule: Schedule, run_id: str) -> None:
        try:
            chat_id = schedule.chat_id
            if not chat_id:
                chat = self.services.chats.create(self.services.settings.provider, self.services.settings.active_model)
                chat = self.services.chats.update(chat.id, title=f"Lịch: {schedule.title}") or chat
                self.runs.attach_chat(schedule.id, chat.id)
                chat_id = chat.id
            chat = self.services.chats.get(chat_id)
            if chat is None:
                raise RuntimeError("Không thể mở chat của lịch trình.")
            try:
                memory_context = self.services.memory.recall(
                    schedule.prompt or schedule.title, chat.id, chat.context_source_chat_id
                )
            except Exception:  # noqa: BLE001
                memory_context = ""
            plugin_tools = connected_read_tools(self.services.workspace.list_plugins())
            full_history = self.services.chats.history(chat.id)
            agent = make_agent(self.services, chat, memory_context, plugin_tools=plugin_tools, history=full_history)
            initial_history_length = len(agent.history)
            result = agent.run(schedule.prompt or schedule.title)
            if result.content_blocks:
                agent.history[-1]["content_blocks"] = result.content_blocks
            saved_history = persisted_history(full_history, agent.history, initial_history_length)
            self.services.chats.replace_history(chat.id, saved_history)
            BackgroundJobRepository(self.services.chats.database).enqueue("memory_index", {"chat_id": chat.id})
            self.runs.finish(run_id, summary=result.text[:500])
        except Exception as exc:  # noqa: BLE001
            self.runs.finish(run_id, error=str(exc))


def build_worker() -> ScheduleWorker:
    settings = load_settings()
    database = Database(settings.database_url)
    media = MediaService(MediaRepository(database), settings.media_dir)
    services = Services(
        settings=settings,
        chats=ChatRepository(database),
        knowledge=KnowledgeService(database, settings.knowledge_dir, settings.embedding_model),
        media=media,
        library=LibraryService(database, settings.media_dir),
        artifacts=ArtifactService(database, settings.media_dir, settings.embedding_model),
        memory=MemoryService(database, settings.embedding_model),
        workspace=WorkspaceRepository(database),
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
