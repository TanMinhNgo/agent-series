"""FastAPI routes for chat streaming."""

from fastapi import APIRouter

from api.contracts.requests import ChatRequest
from api.modules.chats.controller import ChatStreamController


def build_router(controller: ChatStreamController, error_responses: dict) -> APIRouter:
    router = APIRouter(tags=["Chat streaming"])

    @router.post("/api/chats/{chat_id}/stream", responses=error_responses)
    def chat_stream(chat_id: str, payload: ChatRequest):
        return controller.stream(chat_id, payload)

    @router.post("/api/chats/{chat_id}/runs/{run_id}/cancel", status_code=202, responses=error_responses)
    def cancel_chat_run(chat_id: str, run_id: str) -> dict[str, bool]:
        return controller.cancel(chat_id, run_id)

    return router
