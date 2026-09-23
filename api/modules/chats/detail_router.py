"""Chat detail and lifecycle endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from api.contracts.requests import UpdateChatRequest


@dataclass(frozen=True)
class ChatDetailDependencies:
    services: Callable[[], Any]
    chat_json: Callable[[Any], dict[str, Any]]
    selected_settings: Callable[[str, str, str | None], Any]
    current_user_id: Callable[[], str | None]
    record_project_activity: Callable[..., Any]
    chat_not_found_error: str
    selected_project_not_found_error: str
    api_error_responses: dict
    chat_detail_path: str
    project_model: Any


def _update_values(deps: ChatDetailDependencies, chat: Any, payload: UpdateChatRequest) -> dict[str, Any]:
    provider, model = payload.provider or chat.provider, payload.model or chat.model
    deps.selected_settings(provider, model, deps.current_user_id())
    if payload.project_id and deps.services().workspace.get(deps.project_model, payload.project_id) is None:
        raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
    if "collection_id" in payload.model_fields_set and payload.collection_id:
        collection = deps.services().knowledge.get_collection(payload.collection_id)
        target_project = payload.project_id if "project_id" in payload.model_fields_set else chat.project_id
        if collection is None or collection.project_id != target_project:
            raise HTTPException(status_code=422, detail="Collection phải thuộc Project của chat.")
    values = {"provider": provider, "model": model}
    for field in ("title", "pinned", "archived", "project_id", "collection_id", "mode"):
        if field in payload.model_fields_set:
            values[field] = getattr(payload, field)
    if "project_id" in payload.model_fields_set and "collection_id" not in payload.model_fields_set:
        values["collection_id"] = None
    return values


def _record_move(deps: ChatDetailDependencies, chat: Any, previous_project_id: str | None) -> None:
    if previous_project_id == chat.project_id:
        return
    if previous_project_id:
        deps.record_project_activity(previous_project_id, "chat.removed", "chat", chat.id, f"Đã chuyển chat {chat.title} ra khỏi Project.")
    if chat.project_id:
        deps.record_project_activity(chat.project_id, "chat.added", "chat", chat.id, f"Đã thêm chat {chat.title} vào Project.")


def _update_chat(deps: ChatDetailDependencies, chat_id: str, payload: UpdateChatRequest) -> dict[str, Any]:
    try:
        chat = deps.services().chats.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
        previous_project_id = chat.project_id
        chat = deps.services().chats.update(chat_id, **_update_values(deps, chat, payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
    if "project_id" in payload.model_fields_set:
        _record_move(deps, chat, previous_project_id)
    return deps.chat_json(chat)


def build_router(deps: ChatDetailDependencies) -> APIRouter:
    router = APIRouter(tags=["Chats"], prefix="")

    @router.get(deps.chat_detail_path, responses=deps.api_error_responses)
    def get_chat(chat_id: str) -> dict[str, Any]:
        chat = deps.services().chats.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
        return deps.chat_json(chat)

    @router.patch(deps.chat_detail_path, responses=deps.api_error_responses)
    def update_chat(chat_id: str, payload: UpdateChatRequest) -> dict[str, Any]:
        return _update_chat(deps, chat_id, payload)

    @router.delete(deps.chat_detail_path, status_code=204, responses=deps.api_error_responses)
    def delete_chat(chat_id: str) -> None:
        if not deps.services().chats.delete(chat_id):
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)

    return router
