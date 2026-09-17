"""Chat branch, regeneration and pin endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from api.contracts.requests import BranchChatRequest


@dataclass(frozen=True)
class ChatActionDependencies:
    services: Callable[[], Any]
    chat_json: Callable[[Any], dict[str, Any]]
    chat_not_found_error: str
    error_responses: dict


def build_router(deps: ChatActionDependencies) -> APIRouter:
    router = APIRouter(tags=["Chats"])

    @router.post("/api/chats/{chat_id}/branches", status_code=201, responses=deps.error_responses)
    def create_chat_branch(chat_id: str, payload: BranchChatRequest) -> dict[str, Any]:
        try:
            return deps.chat_json(deps.services().chats.create_branch(chat_id, payload.assistant_message_id))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/chats/{chat_id}/regenerate", responses=deps.error_responses)
    def prepare_chat_regeneration(chat_id: str, payload: BranchChatRequest) -> dict[str, str]:
        try:
            return {"content": deps.services().chats.prepare_regeneration(chat_id, payload.assistant_message_id)}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/chats/{chat_id}/pins", responses=deps.error_responses)
    def list_chat_pins(chat_id: str) -> list[dict[str, Any]]:
        if deps.services().chats.get(chat_id) is None:
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
        return [{"messageId": message.id, "position": message.position, "content": message.content} for message in deps.services().chats.chat_pins(chat_id)]

    return router
