"""Local image storage and hydration for multimodal chat requests."""

from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4

from .storage import MediaAttachment, MediaRepository, current_user_id
from .file_storage import FileStorageService

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class MediaService:
    def __init__(self, repository: MediaRepository, media_dir: Path, storage: FileStorageService | None = None):
        self.repository = repository
        self.media_dir = media_dir
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.storage = storage or FileStorageService(media_dir)

    def upload(self, name: str, mime_type: str, content: bytes) -> MediaAttachment:
        if mime_type not in ALLOWED_TYPES:
            raise ValueError("Chỉ hỗ trợ ảnh JPEG, PNG, WebP hoặc GIF.")
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError("Ảnh phải có dung lượng từ 1 byte đến 10 MB.")
        stored = self.storage.upload(content, name, "chat")
        return self.repository.create(
            original_name=name[:255], stored_name=stored.stored_name, storage_provider=stored.provider,
            storage_file_id=stored.file_id, mime_type=mime_type, size_bytes=len(content)
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

    def url_for(self, media: MediaAttachment) -> str:
        if media.storage_provider == "local":
            migrated = self.storage.migrate_local(media.stored_name, media.original_name, "chat")
            if migrated:
                media = self.repository.replace_storage(media.id, migrated.provider, migrated.stored_name, migrated.file_id) or media
        if media.storage_provider != "imagekit":
            return f"/api/media/{media.id}/file"
        return self.storage.signed_url(media.storage_provider, media.stored_name, media.storage_file_id)

    def _payload(self, media: MediaAttachment) -> dict:
        if media.storage_provider == "local":
            migrated = self.storage.migrate_local(media.stored_name, media.original_name, "chat")
            if migrated:
                media = self.repository.replace_storage(media.id, migrated.provider, migrated.stored_name, migrated.file_id) or media
        content = self.storage.read(media.storage_provider, media.stored_name, media.storage_file_id)
        return {
            "id": media.id, "name": media.original_name, "mimeType": media.mime_type,
            "url": self.url_for(media), "data": base64.b64encode(content).decode("ascii"),
        }
