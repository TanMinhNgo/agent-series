"""Chat streaming request orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse


@dataclass(frozen=True)
class ChatStreamController:
    services: Callable[[], Any]
    stream_chat: Callable[..., Any]
    chat_runs: Any
    chat_not_found_error: str
    not_found_marker: str

    def stream(self, chat_id: str, payload: Any) -> StreamingResponse:
        app_services = self.services()
        chat = app_services.chats.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail=self.chat_not_found_error)
        mode = getattr(chat, "mode", "standard")
        if mode != "image" and chat.provider == "ollama" and (payload.attachment_ids or payload.edit_asset_id):
            raise HTTPException(status_code=422, detail="Ollama local hiện chỉ hỗ trợ chat văn bản. Hãy bỏ attachment/file đang sửa hoặc chọn provider cloud.")
        try:
            attachments = app_services.media.for_prompt(payload.attachment_ids)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            artifact_edit = app_services.artifacts.edit_context(payload.edit_asset_id, chat.project_id) if payload.edit_asset_id else None
        except ValueError as exc:
            raise HTTPException(status_code=404 if self.not_found_marker in str(exc) else 422, detail=str(exc)) from exc
        try:
            cancel_event = self.chat_runs.start(chat_id, payload.run_id, chat.user_id) if payload.run_id else Event()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if mode == "plan" and payload.edit_asset_id:
            raise HTTPException(status_code=422, detail="Chế độ Lập kế hoạch không chỉnh sửa hoặc tạo file.")
        if mode == "image" and payload.edit_asset_id:
            raise HTTPException(status_code=422, detail="Chế độ tạo ảnh chỉ sửa ảnh được đính kèm trong tin nhắn.")
        return StreamingResponse(
            self.stream_chat(chat_id, payload.content, attachments, artifact_edit, cancel_event, payload.run_id, payload.research_web),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def cancel(self, chat_id: str, run_id: str) -> dict[str, bool]:
        chat = self.services().chats.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail=self.chat_not_found_error)
        if not self.chat_runs.cancel(chat_id, run_id, chat.user_id):
            raise HTTPException(status_code=409, detail="Lượt tạo phản hồi đã kết thúc hoặc không còn tồn tại.")
        return {"cancelled": True}
