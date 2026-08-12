"""Local image storage and hydration for multimodal chat requests."""

from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4

from .storage import MediaAttachment, MediaRepository

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class MediaService:
    def __init__(self, repository: MediaRepository, media_dir: Path):
        self.repository = repository
        self.media_dir = media_dir
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, name: str, mime_type: str, content: bytes) -> MediaAttachment:
        if mime_type not in ALLOWED_TYPES:
            raise ValueError("Chỉ hỗ trợ ảnh JPEG, PNG, WebP hoặc GIF.")
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError("Ảnh phải có dung lượng từ 1 byte đến 10 MB.")
        suffix = Path(name).suffix.lower() or ".bin"
        stored_name = f"{uuid4().hex}{suffix}"
        (self.media_dir / stored_name).write_bytes(content)
        return self.repository.create(
            original_name=name[:255], stored_name=stored_name, mime_type=mime_type, size_bytes=len(content)
        )

    def for_prompt(self, attachment_ids: list[str]) -> list[dict]:
        if not attachment_ids:
            return []
        records = self.repository.get_many(attachment_ids)
        by_id = {record.id: record for record in records}
        missing = [item for item in attachment_ids if item not in by_id]
        if missing:
            raise ValueError("Có ảnh đính kèm không tồn tại.")
        return [self._payload(by_id[item]) for item in attachment_ids]

    def hydrate_history(self, history: list[dict]) -> list[dict]:
        ids = [attachment["id"] for message in history for attachment in message.get("attachments") or []]
        if not ids:
            return history
        records = {item.id: item for item in self.repository.get_many(ids)}
        hydrated: list[dict] = []
        for message in history:
            copy = dict(message)
            if copy.get("attachments"):
                copy["attachments"] = [self._payload(records[item["id"]]) for item in copy["attachments"] if item["id"] in records]
            hydrated.append(copy)
        return hydrated

    def _payload(self, media: MediaAttachment) -> dict:
        content = (self.media_dir / media.stored_name).read_bytes()
        return {
            "id": media.id, "name": media.original_name, "mimeType": media.mime_type,
            "url": f"/uploads/{media.stored_name}", "data": base64.b64encode(content).decode("ascii"),
        }
