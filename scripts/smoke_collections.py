"""Run a provider-free PostgreSQL smoke test for P1.3 collections.

Creates isolated records, indexes a generated PDF with deterministic fake
embeddings, validates retrieval/citation and always removes its own data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from agent_core.background import BackgroundWorker
from agent_core.config import load_settings
from agent_core.knowledge import KnowledgeService
from agent_core.storage import BackgroundJob, BackgroundJobRepository, ChatRepository, Database, Project, WorkspaceRepository
from api.main import app


class ScopedJobs:
    """Let a worker claim only this smoke test job, never another user's job."""

    def __init__(self, database: Database, job_id: str):
        self.database, self.job_id = database, job_id

    def claim(self, now: datetime):
        with self.database.session() as session:
            job = session.get(BackgroundJob, self.job_id)
            if job is None or job.status != "queued":
                return None
            job.status, job.locked_at, job.attempts = "running", now, job.attempts + 1
            session.commit()
            return job

    def succeed(self, job_id: str) -> None:
        BackgroundJobRepository(self.database).succeed(job_id)

    def fail(self, job_id: str, error: str, now: datetime) -> None:
        BackgroundJobRepository(self.database).fail(job_id, error, now)

    def heartbeat(self, now: datetime, current_job_type: str | None = None, last_error: str | None = None) -> None:
        BackgroundJobRepository(self.database).heartbeat(now, current_job_type, last_error)


def pdf_bytes() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 720, "P1.3 smoke source: collection-only retrieval.")
    canvas.save()
    return stream.getvalue()


def main() -> None:
    settings = load_settings()
    database = Database(settings.database_url)
    workspace, chats = WorkspaceRepository(database), ChatRepository(database)
    knowledge = KnowledgeService(database, settings.knowledge_dir, settings.embedding_model)
    knowledge._embed = lambda values, prefix: [[0.0] * 384 for _ in values]  # type: ignore[method-assign]
    suffix = uuid4().hex[:10]
    project = workspace.create(Project, name=f"__smoke_collections_{suffix}")
    document_id: str | None = None
    try:
        document, created = knowledge.upload("collection-smoke.pdf", pdf_bytes(), project.id)
        assert created
        document_id = document.id
        job = BackgroundJobRepository(database).enqueue_unique(
            "document_index", {"document_id": document.id}, f"document:{document.id}"
        )[0]
        assert BackgroundWorker(ScopedJobs(database, job.id), knowledge).run_once(datetime.now(UTC))
        assert knowledge.list_documents(project.id)[0].status == "ready"

        first = knowledge.create_collection(project.id, "Collection A")
        second = knowledge.create_collection(project.id, "Collection B")
        knowledge.set_collection_documents(first.id, [document.id])
        knowledge.set_collection_documents(second.id, [document.id])
        chat = chats.create("gemini", "smoke-model", project_id=project.id, collection_id=first.id)
        citation = knowledge.search("collection retrieval", project_id=project.id, collection_id=first.id)
        assert f"/api/documents/{document.id}/file#page=1" in citation
        assert knowledge.collection_documents(second.id)[0].id == document.id
        assert knowledge.delete_collection(first.id)
        assert chats.get(chat.id).collection_id is None

        with TestClient(app) as client:
            response = client.get(f"/api/documents/{document.id}/file")
        assert response.status_code == 200 and response.headers["content-type"].startswith("application/pdf")
        print("P1.3 collection smoke passed.")
    finally:
        if document_id:
            knowledge.delete(document_id)
        with database.session() as session:
            item = session.scalar(select(Project).where(Project.id == project.id))
            if item is not None:
                session.delete(item)
                session.commit()


if __name__ == "__main__":
    main()
