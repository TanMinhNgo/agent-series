"""Personal library artifact endpoints."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select

from api.contracts.requests import UpdateArtifactRequest


@dataclass(frozen=True)
class LibraryDependencies:
    services: Callable[[], Any]
    project_model: Any
    library_asset_model: Any
    library_asset_json: Callable[[Any], dict[str, Any]]
    enqueue_artifact_index: Callable[..., Any]
    queue_file_cleanup: Callable[..., Any]
    record_project_activity: Callable[..., Any]
    selected_project_not_found_error: str
    artifact_not_found_error: str
    not_found_marker: str
    api_error_responses: dict


def build_router(deps: LibraryDependencies) -> APIRouter:
    router = APIRouter(tags=["Personal library"])

    @router.get("/api/library/assets", responses=deps.api_error_responses)
    def list_library_assets(query: str = "", scope: Literal["all", "global", "project"] = "all", project_id: str | None = Query(default=None, alias="projectId")) -> list[dict[str, Any]]:
        if scope == "project" and not project_id:
            raise HTTPException(status_code=422, detail="Cần chọn Project để lọc file.")
        return [deps.library_asset_json(item) for item in deps.services().library.list(query, project_id, scope)]

    @router.post("/api/library/assets", status_code=201, responses=deps.api_error_responses)
    async def upload_library_assets(files: list[UploadFile] = File(...), project_id: str | None = Form(default=None, alias="projectId")) -> dict[str, list[dict[str, Any]]]:
        uploaded, errors = [], []
        if project_id and deps.services().workspace.get(deps.project_model, project_id) is None:
            raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
        for file in files:
            name = file.filename or "file"
            try:
                asset = deps.services().library.upload(name, file.content_type or "", await file.read(), project_id=project_id)
                deps.enqueue_artifact_index(asset)
                uploaded.append(deps.library_asset_json(asset))
                if project_id:
                    deps.record_project_activity(project_id, "artifact.uploaded", "artifact", asset.id, f"Đã thêm file {asset.name}.")
            except ValueError as exc:
                errors.append({"name": name, "message": str(exc)})
        return {"items": uploaded, "errors": errors}

    @router.patch("/api/library/assets/{asset_id}", responses=deps.api_error_responses)
    def update_library_asset(asset_id: str, payload: UpdateArtifactRequest) -> dict[str, Any]:
        values = payload.model_dump(exclude_unset=True)
        project_id = values.get("project_id")
        if project_id and deps.services().workspace.get(deps.project_model, project_id) is None:
            raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
        try:
            item = deps.services().library.update(asset_id, name=values.get("name"), project_id=project_id, is_project_source=values.get("is_project_source"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=404, detail=deps.artifact_not_found_error)
        deps.enqueue_artifact_index(item)
        if getattr(item, "project_id", None):
            if "is_project_source" in values:
                event = "project_source.pinned" if item.is_project_source else "project_source.unpinned"
                summary = f"Đã {'ghim' if item.is_project_source else 'bỏ ghim'} file {item.name} làm nguồn Project."
            else:
                event, summary = "artifact.updated", f"Đã cập nhật file {item.name}."
            deps.record_project_activity(item.project_id, event, "artifact", item.id, summary)
        return deps.library_asset_json(item)

    @router.post("/api/library/assets/{asset_id}/versions", status_code=201, responses=deps.api_error_responses)
    async def create_library_asset_version(asset_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        try:
            item = deps.services().library.create_version(asset_id, file.filename or "artifact", file.content_type or "", await file.read())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        deps.enqueue_artifact_index(item)
        if getattr(item, "project_id", None):
            deps.record_project_activity(item.project_id, "artifact.version_created", "artifact", item.id, f"Đã tạo version {item.version} của {item.name}.")
        return deps.library_asset_json(item)

    @router.post("/api/library/assets/{asset_id}/restore", status_code=201, responses=deps.api_error_responses)
    def restore_library_asset_version(asset_id: str) -> dict[str, Any]:
        try:
            item = deps.services().library.restore_version(asset_id)
        except ValueError as exc:
            message = str(exc)
            raise HTTPException(status_code=404 if deps.not_found_marker in message else 422, detail=message) from exc
        deps.enqueue_artifact_index(item)
        return deps.library_asset_json(item)

    @router.get("/api/library/assets/{asset_id}/versions", responses=deps.api_error_responses)
    def list_library_asset_versions(asset_id: str) -> list[dict[str, Any]]:
        items = deps.services().library.versions(asset_id)
        if not items:
            raise HTTPException(status_code=404, detail=deps.artifact_not_found_error)
        return [deps.library_asset_json(item) for item in items]

    @router.get("/api/library/assets/{asset_id}/preview", responses=deps.api_error_responses)
    def preview_library_asset(asset_id: str) -> dict[str, Any]:
        try:
            return deps.services().artifacts.preview(asset_id)
        except ValueError as exc:
            message = str(exc)
            raise HTTPException(status_code=404 if deps.not_found_marker in message else 422, detail=message) from exc

    @router.get("/api/library/assets/{asset_id}/diff", responses=deps.api_error_responses)
    def diff_library_asset(asset_id: str) -> dict[str, Any]:
        try:
            return deps.services().artifacts.diff(asset_id)
        except ValueError as exc:
            message = str(exc)
            raise HTTPException(status_code=404 if deps.not_found_marker in message else 422, detail=message) from exc

    @router.get("/api/library/assets/{asset_id}/file", responses=deps.api_error_responses)
    def library_asset_file(asset_id: str) -> Response:
        asset = deps.services().library.ensure_remote(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail=deps.artifact_not_found_error)
        if asset.storage_provider == "imagekit":
            return RedirectResponse(deps.services().library.storage.signed_url(asset.storage_provider, asset.stored_name, asset.storage_file_id), status_code=307)
        path = Path(deps.services().settings.media_dir) / asset.stored_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy file artifact.")
        return FileResponse(path, media_type=asset.mime_type, filename=asset.name, content_disposition_type="inline")

    @router.post("/api/library/assets/{asset_id}/reindex", status_code=202, responses=deps.api_error_responses)
    def reindex_library_asset(asset_id: str) -> dict[str, Any]:
        with deps.services().chats.database.session() as session:
            asset = session.get(deps.library_asset_model, asset_id)
            if asset is None:
                raise HTTPException(status_code=404, detail=deps.artifact_not_found_error)
            if not asset.is_project_source:
                raise HTTPException(status_code=422, detail="Chỉ Project Source mới cần index.")
            asset.index_status, asset.index_error = "queued", None
            session.commit()
        deps.enqueue_artifact_index(asset)
        return deps.library_asset_json(asset)

    @router.delete("/api/library/assets/{asset_id}", status_code=204, responses=deps.api_error_responses)
    def delete_library_asset(asset_id: str) -> None:
        with deps.services().chats.database.session() as session:
            asset = session.get(deps.library_asset_model, asset_id)
            if asset is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy file trong Thư viện.")
            versions = session.scalars(select(deps.library_asset_model).where(deps.library_asset_model.artifact_id == asset.artifact_id)).all()
            project_id, asset_name = asset.project_id, asset.name
            deps.queue_file_cleanup(
                session,
                [{"storage": "media", "stored_name": item.stored_name, "storage_provider": item.storage_provider, "storage_file_id": item.storage_file_id} for item in versions],
                f"artifact-cleanup:{asset.artifact_id}",
            )
            for item in versions:
                session.delete(item)
            session.commit()
        if project_id:
            deps.record_project_activity(project_id, "artifact.deleted", "artifact", asset_id, f"Đã xóa file {asset_name}.")

    return router
