"""Persist image-mode chat turns without coupling them to HTTP routes."""

from __future__ import annotations

from datetime import UTC, datetime
from queue import Queue
from typing import Any, Callable
from uuid import uuid4

from agent_core.ai.images import ImageGenerationError, OpenAIImageService
from agent_core.runtime.services import Services

ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}


def run_image_turn(
    app_services: Services,
    chat_id: str,
    content: str,
    attachments: list[dict],
    full_history: list[dict[str, Any]],
    events: Queue,
    serialize_message: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    if len(attachments) > 1:
        raise ValueError("Chế độ tạo ảnh chỉ hỗ trợ một ảnh đính kèm cho mỗi lần chỉnh sửa.")
    if attachments and attachments[0].get("mimeType") not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValueError("Chỉ hỗ trợ PNG, JPEG hoặc WebP khi chỉnh sửa ảnh.")

    events.put(("status", {"message": "Đang tạo ảnh..."}))
    image_service = OpenAIImageService(app_services.settings.openai_api_key, app_services.settings.openai_image_model)
    data = image_service.edit(content, attachments[0]) if attachments else image_service.generate(content)
    asset = app_services.library.upload(f"image-{uuid4().hex[:8]}.png", "image/png", data, source="generated")
    created_at = datetime.now(UTC).isoformat()
    user: dict[str, Any] = {"role": "user", "content": content, "created_at": created_at}
    if attachments:
        user["attachments"] = [{key: value for key, value in attachments[0].items() if key != "data"}]
    assistant = {
        "role": "assistant",
        "content": "Đây là ảnh đã tạo." if not attachments else "Đây là ảnh đã chỉnh sửa.",
        "generated_asset_ids": [asset.id],
        "created_at": created_at,
    }
    app_services.chats.replace_history(chat_id, [*full_history, user, assistant])
    events.put(("message", serialize_message(assistant)))
    events.put(("done", {}))
