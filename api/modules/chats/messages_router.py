"""Chat message actions and history endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from api.contracts.requests import BranchChatRequest, FeedbackRequest, PinMessageRequest


@dataclass(frozen=True)
class MessageRouteDependencies:
    services: Callable[[], Any]
    chat_json: Callable[[Any], dict[str, Any]]
    message_json: Callable[[dict[str, Any]], dict[str, Any]]
    library_asset_json: Callable[[Any], dict[str, Any]]
    retrieval_trace_json: Callable[[Any], dict[str, Any]]
    chat_not_found_error: str
    error_responses: dict


def _visible_messages(deps: MessageRouteDependencies, services: Any, chat_id: str) -> list[dict[str, Any]]:
    backfill = getattr(services.chats, "backfill_artifact_links", None)
    if backfill:
        backfill(chat_id)
    history = [item for item in services.chats.history(chat_id) if item["role"] in {"user", "assistant"}]
    ids = [item["message_id"] for item in history if item["role"] == "assistant" and item.get("message_id")]
    artifacts = services.chats.artifacts_by_assistant_message(chat_id, ids) if hasattr(services.chats, "artifacts_by_assistant_message") else {}
    feedback = services.personalization.feedback_by_message_ids(ids)
    traces = services.workspace.retrieval_traces(ids) if hasattr(services.workspace, "retrieval_traces") else {}
    return [deps.message_json({**item, "feedback_kind": feedback.get(item.get("message_id")), "artifacts": [deps.library_asset_json(a) for a in artifacts.get(item.get("message_id", ""), [])], "retrievalTrace": [deps.retrieval_trace_json(t) for t in traces.get(item.get("message_id", ""), [])]} if item["role"] == "assistant" else item) for item in history]


def build_router(deps: MessageRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Chats"])

    @router.get("/api/chats/{chat_id}/messages", responses=deps.error_responses)
    def messages(chat_id: str) -> list[dict[str, Any]]:
        services = deps.services()
        if services.chats.get(chat_id) is None:
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
        return _visible_messages(deps, services, chat_id)

    @router.post("/api/chats/{chat_id}/read", responses=deps.error_responses)
    def mark_chat_read(chat_id: str) -> dict[str, Any]:
        chat = deps.services().chats.set_unread(chat_id, False)
        if chat is None:
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
        return deps.chat_json(chat)

    @router.patch("/api/messages/{message_id}/pin", responses=deps.error_responses)
    def pin_message(message_id: str, payload: PinMessageRequest) -> dict[str, Any]:
        message = deps.services().chats.set_message_pin(message_id, payload.pinned)
        if message is None:
            raise HTTPException(status_code=404, detail="Chỉ có thể ghim message của bạn.")
        return {"messageId": message.id, "pinned": message.pinned}

    @router.post("/api/messages/{message_id}/feedback", status_code=201, responses=deps.error_responses)
    def create_response_feedback(message_id: str, payload: FeedbackRequest) -> dict[str, Any]:
        try:
            item = deps.services().personalization.record_feedback(message_id, payload.kind, payload.note)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"id": item.id, "messageId": item.message_id, "kind": item.kind, "note": item.note}

    return router
