"""Chat list and creation endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from agent_core.persistence.store import Project
from agent_core.runtime.credentials import CredentialError
from api.contracts.requests import CreateChatRequest


@dataclass(frozen=True)
class ChatCrudDependencies:
    services: Callable[[], Any]
    chat_json: Callable[[Any], dict[str, Any]]
    available_provider_models: Callable[..., dict[str, list[str]]]
    selected_settings: Callable[..., Any]
    current_user_id: Any
    selected_project_not_found_error: str
    error_responses: dict


def _selected_chat_settings(deps: ChatCrudDependencies, payload: CreateChatRequest) -> Any:
    settings = deps.services().settings
    available = deps.available_provider_models(deps.current_user_id.get())
    provider = payload.provider or (settings.provider if settings.provider in available else next(iter(available), settings.provider))
    model = payload.model or (settings.active_model if settings.active_model in available.get(provider, []) else (available.get(provider) or [settings.active_model])[0])
    try:
        selected = deps.selected_settings(provider, model, deps.current_user_id.get())
    except (ValueError, CredentialError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return selected


def _create_chat(deps: ChatCrudDependencies, payload: CreateChatRequest) -> dict[str, Any]:
    selected = _selected_chat_settings(deps, payload)
    if payload.context_source_chat_id and deps.services().chats.get(payload.context_source_chat_id) is None:
        raise HTTPException(status_code=422, detail="Không tìm thấy chat nguồn để kế thừa context.")
    if payload.project_id and deps.services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
    if payload.collection_id:
        collection = deps.services().knowledge.get_collection(payload.collection_id)
        if collection is None or collection.project_id != payload.project_id:
            raise HTTPException(status_code=422, detail="Collection phải thuộc Project đã chọn.")
    return deps.chat_json(deps.services().chats.create(selected.provider, selected.active_model, payload.context_source_chat_id, payload.project_id, payload.collection_id, payload.mode))


def build_router(deps: ChatCrudDependencies) -> APIRouter:
    router = APIRouter(tags=["Chats"])

    @router.get("/api/chats", responses=deps.error_responses)
    def list_chats(offset: int = Query(default=0, ge=0), limit: int = Query(default=40, ge=1, le=100)) -> dict[str, Any]:
        items, total = deps.services().chats.list(offset=offset, limit=limit)
        next_offset = offset + len(items)
        return {"items": [deps.chat_json(chat) for chat in items], "total": total, "nextOffset": next_offset if next_offset < total else None}

    @router.post("/api/chats", status_code=201, responses=deps.error_responses)
    def create_chat(payload: CreateChatRequest) -> dict[str, Any]:
        return _create_chat(deps, payload)

    return router
