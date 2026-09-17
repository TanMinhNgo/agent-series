"""Chat attachment endpoints."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response


@dataclass(frozen=True)
class MediaRouteDependencies:
    services: Callable[[], Any]
    media_json: Callable[[Any], dict[str, Any]]
    error_responses: dict


def build_router(deps: MediaRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Media"])

    @router.post("/api/media", status_code=201, responses=deps.error_responses)
    async def upload_media(files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
        try:
            uploaded = [deps.services().media.upload(file.filename or "image", file.content_type or "", await file.read()) for file in files]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return [deps.media_json(item) for item in uploaded]

    @router.get("/api/media/{media_id}/file", responses=deps.error_responses)
    def media_file(media_id: str) -> Response:
        records = deps.services().media.repository.get_many([media_id])
        if not records:
            raise HTTPException(status_code=404, detail="Không tìm thấy ảnh đính kèm.")
        media = records[0]
        if media.storage_provider == "imagekit":
            return RedirectResponse(deps.services().media.storage.signed_url(media.storage_provider, media.stored_name, media.storage_file_id), status_code=307)
        path = Path(deps.services().settings.media_dir) / media.stored_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Không tìm thấy ảnh đính kèm.")
        return FileResponse(path, media_type=media.mime_type, filename=media.original_name, content_disposition_type="inline")

    return router
