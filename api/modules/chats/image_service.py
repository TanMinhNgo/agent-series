"""Persist image-mode chat turns without coupling them to HTTP routes."""

from __future__ import annotations

from datetime import UTC, datetime
from queue import Queue
from typing import Any, Callable
from uuid import uuid4

from agent_core.ai.history import recent_chat_history
from agent_core.ai.images import ImageGenerationError, OpenAIImageService
from agent_core.ai.providers import build_client
from agent_core.persistence.store import Chat
from agent_core.runtime.agent import selected_settings
from agent_core.runtime.services import Services

ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
CONTEXT_TURNS = 4
CONTEXT_CHARS = 1500
PROMPT_SYSTEM = (
    "Bạn soạn prompt cho model tạo ảnh. Dựa vào đoạn hội thoại và yêu cầu cuối của người dùng, "
    "viết MỘT prompt mô tả ảnh cần vẽ, cụ thể theo đúng chủ đề đang bàn (không quá 120 từ). "
    "Chỉ trả về prompt, không giải thích."
)


def compose_image_prompt(app_services: Services, chat: Chat, content: str, full_history: list[dict[str, Any]]) -> str:
    """Enrich a bare request like "tạo ảnh minh họa" with the chat topic.

    Falls back to the raw request when there is no context or the text model fails,
    so image generation never depends on this extra step.
    """
    turns = [m for m in recent_chat_history(full_history, CONTEXT_TURNS) if m.get("role") in {"user", "assistant"} and m.get("content")]
    if not turns or chat.provider == "ollama":
        return content
    transcript = "\n".join(f"{m['role']}: {str(m['content'])[:CONTEXT_CHARS]}" for m in turns)
    try:
        client = build_client(selected_settings(app_services, chat.provider, chat.model, chat.user_id))
        reply = client.complete(PROMPT_SYSTEM, [{"role": "user", "content": f"{transcript}\n\nYêu cầu tạo ảnh: {content}"}], [])
    except Exception:  # noqa: BLE001
        return content
    return reply.text.strip() or content


def run_image_turn(
    app_services: Services,
    chat: Chat,
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
    prompt = content if attachments else compose_image_prompt(app_services, chat, content, full_history)
    data = image_service.edit(content, attachments[0]) if attachments else image_service.generate(prompt)
    asset = app_services.library.upload(f"image-{uuid4().hex[:8]}.png", "image/png", data, source="generated")
    created_at = datetime.now(UTC).isoformat()
    user: dict[str, Any] = {"role": "user", "content": content, "created_at": created_at}
    if attachments:
        user["attachments"] = [{key: value for key, value in attachments[0].items() if key != "data"}]
    assistant = {
        "role": "assistant",
        "content": (
            f"Đã chỉnh sửa ảnh theo yêu cầu: {content}"
            if attachments
            else f"Đã tạo ảnh {asset.name} theo prompt: {prompt}"
        ),
        "generated_asset_ids": [asset.id],
        "created_at": created_at,
    }
    app_services.chats.replace_history(chat_id, [*full_history, user, assistant])
    events.put(("message", serialize_message(assistant)))
    events.put(("done", {}))
