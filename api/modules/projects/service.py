"""Transactional project lifecycle operations."""

from sqlalchemy import func, select

from agent_core.persistence.store import BackgroundJob, Chat, Document, LibraryAsset, Project, Schedule


def delete_project(database, project_id: str, confirm_name: str, queue_file_cleanup, project_not_found_error: str) -> dict:
    with database.session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError(project_not_found_error)
        if confirm_name != project.name:
            raise ValueError("Tên xác nhận chưa khớp với tên dự án.")
        documents = list(session.scalars(select(Document).where(Document.project_id == project_id)))
        assets = list(session.scalars(select(LibraryAsset).where(LibraryAsset.project_id == project_id)))
        chats_count = session.scalar(select(func.count()).select_from(Chat).where(Chat.project_id == project_id)) or 0
        schedules_count = session.scalar(select(func.count()).select_from(Schedule).where(Schedule.project_id == project_id)) or 0
        ids = [item.id for item in documents]
        if ids:
            for job in session.scalars(select(BackgroundJob).where(BackgroundJob.type == "document_index", BackgroundJob.dedupe_key.in_([f"document:{item_id}" for item_id in ids]), BackgroundJob.status.in_(("queued", "running")))).all():
                job.status, job.locked_at, job.last_error = "cancelled", None, "Dự án đã bị xóa."
        queue_file_cleanup(session, [*[{"storage": "knowledge", "stored_name": item.stored_name, "storage_provider": item.storage_provider, "storage_file_id": item.storage_file_id} for item in documents], *[{"storage": "media", "stored_name": item.stored_name, "storage_provider": item.storage_provider, "storage_file_id": item.storage_file_id} for item in assets]], f"project-cleanup:{project_id}")
        session.delete(project)
        session.commit()
        return {"deleted": {"chats": chats_count, "documents": len(documents), "assets": len(assets), "schedules": schedules_count}, "fileCleanupQueued": bool(documents or assets)}
