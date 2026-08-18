"""PostgreSQL-backed jobs for slow, idempotent local tasks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .knowledge import KnowledgeService
from .artifacts import ArtifactService
from .memory import MemoryService
from .storage import BackgroundJobRepository, ChatRepository


class BackgroundWorker:
    def __init__(self, jobs: BackgroundJobRepository, knowledge: KnowledgeService, memory: MemoryService | None = None, chats: ChatRepository | None = None, media_dir: Path | None = None, artifacts: ArtifactService | None = None):
        self.jobs, self.knowledge, self.memory, self.chats = jobs, knowledge, memory, chats
        self.media_dir = media_dir
        self.artifacts = artifacts

    @staticmethod
    def _delete_stored_file(directory: Path, stored_name: str) -> None:
        root = directory.resolve()
        target = (root / stored_name).resolve()
        if root not in target.parents or target == root:
            raise ValueError("Đường dẫn dọn dẹp file không hợp lệ.")
        if target.exists():
            target.unlink()

    def _cleanup_files(self, files: list[dict]) -> None:
        for file in files:
            storage = file.get("storage")
            if storage == "knowledge":
                directory = self.knowledge.knowledge_dir
            elif storage == "media" and self.media_dir is not None:
                directory = self.media_dir
            else:
                raise ValueError("Kho lưu trữ dọn dẹp file không hợp lệ.")
            self._delete_stored_file(directory, str(file.get("stored_name", "")))

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
            elif job.type == "artifact_index" and self.artifacts:
                self.artifacts.index(str(job.payload["asset_id"]))
            elif job.type == "file_cleanup":
                self._cleanup_files(list(job.payload.get("files", [])))
            else:
                raise ValueError(f"Unsupported job type: {job.type}")
            self.jobs.succeed(job.id)
        except Exception as exc:  # noqa: BLE001
            self.jobs.fail(job.id, str(exc), now)
            self.jobs.heartbeat(now, last_error=str(exc))
        else:
            self.jobs.heartbeat(now)
        return True
