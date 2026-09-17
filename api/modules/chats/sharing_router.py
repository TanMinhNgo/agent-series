"""Chat sharing and prompt-template endpoints."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from api.contracts.requests import PromptTemplateRequest, ShareRequest


@dataclass(frozen=True)
class ChatSharingDependencies:
    services: Callable[[], Any]
    template_model: Any
    project_model: Any
    template_json: Callable[[Any], dict[str, Any]]
    share_json: Callable[[Any], dict[str, Any]]
    selected_project_not_found_error: str
    chat_not_found_error: str
    api_error_responses: dict
    record_project_activity: Callable[..., Any]


def build_router(deps: ChatSharingDependencies) -> APIRouter:
    router = APIRouter()

    @router.get("/api/templates", tags=["Workspace"], responses=deps.api_error_responses)
    def list_templates(project_id: str | None = Query(default=None, alias="projectId")) -> list[dict[str, Any]]:
        with deps.services().chats.database.session() as session:
            statement = select(deps.template_model).order_by(deps.template_model.updated_at.desc())
            if project_id:
                statement = statement.where(deps.template_model.project_id.in_((None, project_id)))
            else:
                statement = statement.where(deps.template_model.project_id.is_(None))
            return [deps.template_json(item) for item in session.scalars(statement)]

    @router.post("/api/templates", status_code=201, tags=["Workspace"], responses=deps.api_error_responses)
    def create_template(payload: PromptTemplateRequest) -> dict[str, Any]:
        if payload.project_id and deps.services().workspace.get(deps.project_model, payload.project_id) is None:
            raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
        return deps.template_json(deps.services().workspace.create(deps.template_model, **payload.model_dump()))

    @router.patch("/api/templates/{template_id}", tags=["Workspace"], responses=deps.api_error_responses)
    def update_template(template_id: str, payload: PromptTemplateRequest) -> dict[str, Any]:
        if payload.project_id and deps.services().workspace.get(deps.project_model, payload.project_id) is None:
            raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
        item = deps.services().workspace.update(deps.template_model, template_id, **payload.model_dump())
        if item is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy template.")
        return deps.template_json(item)

    @router.delete("/api/templates/{template_id}", status_code=204, tags=["Workspace"], responses=deps.api_error_responses)
    def delete_template(template_id: str) -> None:
        if not deps.services().workspace.delete(deps.template_model, template_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy template.")

    @router.post("/api/chats/{chat_id}/share", tags=["Shared chats"], responses=deps.api_error_responses)
    def share_chat(chat_id: str, payload: ShareRequest | None = None) -> dict[str, Any]:
        expires_at = payload.expires_at if payload else None
        if expires_at and expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=422, detail="Thời hạn chia sẻ phải ở tương lai.")
        share = deps.services().chats.create_or_update_share(chat_id, expires_at)
        if share is None:
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
        chat = deps.services().chats.get(chat_id)
        if chat and chat.project_id:
            deps.record_project_activity(chat.project_id, "chat.shared", "chat", chat.id, f"Đã tạo hoặc cập nhật liên kết chia sẻ cho chat {chat.title}.")
        return deps.share_json(share)

    @router.delete("/api/chats/{chat_id}/share", status_code=204, tags=["Shared chats"], responses=deps.api_error_responses)
    def revoke_share(chat_id: str) -> None:
        chat = deps.services().chats.get(chat_id)
        if not deps.services().chats.revoke_share(chat_id):
            raise HTTPException(status_code=404, detail="Chat chưa có liên kết chia sẻ.")
        if chat and chat.project_id:
            deps.record_project_activity(chat.project_id, "chat.share_revoked", "chat", chat.id, f"Đã thu hồi liên kết chia sẻ của chat {chat.title}.")

    @router.get("/api/public/shares/{token}", tags=["Shared chats"], responses=deps.api_error_responses)
    def public_share(token: str) -> dict[str, Any]:
        share = deps.services().chats.get_share(token)
        if share is None or (share.expires_at and share.expires_at <= datetime.now(UTC)):
            raise HTTPException(status_code=404, detail="Liên kết chia sẻ không tồn tại hoặc đã bị thu hồi.")
        return deps.share_json(share)

    return router
