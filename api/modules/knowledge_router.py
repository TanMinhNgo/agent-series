"""Knowledge-base document and collection endpoints."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from fastapi import File, Form, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response

from api.contracts.requests import CollectionDocumentsRequest, KnowledgeCollectionRequest


@dataclass(frozen=True)
class KnowledgeDependencies:
    services: Callable[[], Any]
    background_jobs: Callable[[Any], Any]
    project_model: Any
    document_json: Callable[..., dict[str, Any]]
    collection_json: Callable[..., dict[str, Any]]
    record_project_activity: Callable[..., Any]
    collection_not_found_error: str
    document_not_found_error: str
    api_error_responses: dict
    document_model: Any = None
    background_job_model: Any = None
    enqueue_document_index: Callable[..., Any] | None = None
    queue_file_cleanup: Callable[..., Any] | None = None


def build_router(deps: KnowledgeDependencies) -> APIRouter:
    router = APIRouter(tags=["Knowledge base"])

    @router.get("/api/documents", responses=deps.api_error_responses)
    def documents() -> list[dict[str, Any]]:
        jobs = deps.background_jobs(deps.services().chats.database)
        return [deps.document_json(item, jobs.latest_for_document(item.id)) for item in deps.services().knowledge.list_documents()]

    @router.get("/api/projects/{project_id}/collections", responses=deps.api_error_responses)
    def list_collections(project_id: str) -> list[dict[str, Any]]:
        if deps.services().workspace.get(deps.project_model, project_id) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy Project.")
        return [deps.collection_json(item, deps.services().knowledge.collection_documents(item.id)) for item in deps.services().knowledge.list_collections(project_id)]

    @router.post("/api/projects/{project_id}/collections", status_code=201, responses=deps.api_error_responses)
    def create_collection(project_id: str, payload: KnowledgeCollectionRequest) -> dict[str, Any]:
        if deps.services().workspace.get(deps.project_model, project_id) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy Project.")
        try:
            item = deps.services().knowledge.create_collection(project_id, payload.name, payload.description)
            deps.record_project_activity(project_id, "collection.created", "collection", item.id, f"Đã tạo collection {item.name}.")
            return deps.collection_json(item, [])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.patch("/api/collections/{collection_id}", responses=deps.api_error_responses)
    def update_collection(collection_id: str, payload: KnowledgeCollectionRequest) -> dict[str, Any]:
        try:
            item = deps.services().knowledge.update_collection(collection_id, payload.name, payload.description)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=404, detail=deps.collection_not_found_error)
        deps.record_project_activity(item.project_id, "collection.updated", "collection", item.id, f"Đã cập nhật collection {item.name}.")
        return deps.collection_json(item, deps.services().knowledge.collection_documents(item.id))

    @router.put("/api/collections/{collection_id}/documents", responses=deps.api_error_responses)
    def set_collection_documents(collection_id: str, payload: CollectionDocumentsRequest) -> dict[str, Any]:
        try:
            item = deps.services().knowledge.get_collection(collection_id)
            if item is None:
                raise HTTPException(status_code=404, detail=deps.collection_not_found_error)
            documents = deps.services().knowledge.set_collection_documents(collection_id, payload.document_ids)
            deps.record_project_activity(item.project_id, "collection.documents_updated", "collection", item.id, f"Đã cập nhật tài liệu cho collection {item.name}.")
            return deps.collection_json(item, documents)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/api/collections/{collection_id}", status_code=204, responses=deps.api_error_responses)
    def delete_collection(collection_id: str) -> None:
        item = deps.services().knowledge.get_collection(collection_id)
        if item is None or not deps.services().knowledge.delete_collection(collection_id):
            raise HTTPException(status_code=404, detail=deps.collection_not_found_error)
        deps.record_project_activity(item.project_id, "collection.deleted", "collection", collection_id, f"Đã xóa collection {item.name}.")

    @router.get("/api/documents/{document_id}/file", responses=deps.api_error_responses)
    def document_file(document_id: str) -> Response:
        document = deps.services().knowledge.ensure_remote(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=deps.document_not_found_error)
        if document.storage_provider == "imagekit":
            return RedirectResponse(deps.services().knowledge.storage.signed_url(document.storage_provider, document.stored_name, document.storage_file_id), status_code=307)
        path = Path(deps.services().settings.knowledge_dir) / document.stored_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy file tài liệu.")
        return FileResponse(path, media_type="application/pdf", filename=document.original_name, content_disposition_type="inline")

    @router.post("/api/documents", status_code=201, responses=deps.api_error_responses)
    async def upload_documents(files: list[UploadFile] = File(...), project_id: str | None = Form(default=None)) -> list[dict[str, Any]]:
        if project_id and deps.services().workspace.get(deps.project_model, project_id) is None:
            raise HTTPException(status_code=422, detail="Không tìm thấy Project.")
        uploaded = []
        try:
            for file in files:
                document, created = deps.services().knowledge.upload(file.filename or "document.pdf", await file.read(), project_id)
                if created or document.status != "ready":
                    deps.enqueue_document_index(document)
                uploaded.append(document)
                if project_id:
                    deps.record_project_activity(project_id, "document.uploaded", "document", document.id, f"Đã thêm tài liệu {document.original_name}.")
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        jobs = deps.background_jobs(deps.services().chats.database)
        return [deps.document_json(item, jobs.latest_for_document(item.id)) for item in uploaded]

    @router.post("/api/documents/{document_id}/reindex", status_code=202, responses=deps.api_error_responses)
    def reindex_document(document_id: str) -> dict[str, Any]:
        document = next((item for item in deps.services().knowledge.list_documents() if item.id == document_id), None)
        if document is None:
            raise HTTPException(status_code=404, detail=deps.document_not_found_error)
        return deps.document_json(document, deps.enqueue_document_index(document))

    @router.delete("/api/documents/{document_id}", status_code=204, responses=deps.api_error_responses)
    def delete_document(document_id: str) -> None:
        with deps.services().chats.database.session() as session:
            document = session.get(deps.document_model, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail=deps.document_not_found_error)
            project_id, document_name = document.project_id, document.original_name
            jobs = session.scalars(select(deps.background_job_model).where(deps.background_job_model.type == "document_index", deps.background_job_model.dedupe_key == f"document:{document.id}", deps.background_job_model.status.in_(("queued", "running")))).all()
            for job in jobs:
                job.status, job.locked_at, job.last_error = "cancelled", None, "Tài liệu đã bị xóa."
            deps.queue_file_cleanup(session, [{"storage": "knowledge", "stored_name": document.stored_name, "storage_provider": document.storage_provider, "storage_file_id": document.storage_file_id}], f"document-cleanup:{document.id}")
            session.delete(document)
            session.commit()
        if project_id:
            deps.record_project_activity(project_id, "document.deleted", "document", document_id, f"Đã xóa tài liệu {document_name}.")

    return router
