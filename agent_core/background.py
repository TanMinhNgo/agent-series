"""PostgreSQL-backed jobs for slow, idempotent local tasks."""

from __future__ import annotations

from datetime import UTC, datetime

from .knowledge import KnowledgeService
from .memory import MemoryService
from .storage import BackgroundJobRepository, ChatRepository


class BackgroundWorker:
    def __init__(self, jobs: BackgroundJobRepository, knowledge: KnowledgeService, memory: MemoryService | None = None, chats: ChatRepository | None = None):
        self.jobs, self.knowledge, self.memory, self.chats = jobs, knowledge, memory, chats

    def run_once(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        job = self.jobs.claim(now)
        if job is None:
            return False
        self.jobs.heartbeat(now, current_job_type=job.type)
        try:
            if job.type == "document_index":
                document = self.knowledge.index(str(job.payload["document_id"]))
                if getattr(document, "status", None) == "failed":
                    raise RuntimeError(getattr(document, "error", None) or "Không thể index tài liệu.")
            elif job.type == "memory_index" and self.memory and self.chats:
                chat_id = str(job.payload["chat_id"])
                self.memory.index_history(chat_id, self.chats.history(chat_id))
            else:
                raise ValueError(f"Unsupported job type: {job.type}")
            self.jobs.succeed(job.id)
        except Exception as exc:  # noqa: BLE001
            self.jobs.fail(job.id, str(exc), now)
            self.jobs.heartbeat(now, last_error=str(exc))
        else:
            self.jobs.heartbeat(now)
        return True
