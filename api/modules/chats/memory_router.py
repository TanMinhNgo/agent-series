"""Long-term memory endpoints owned by the chat domain."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException


@dataclass(frozen=True)
class MemoryRouteDependencies:
    services: Callable[[], Any]
    error_responses: dict


def build_router(deps: MemoryRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Memory library"])

    @router.get("/api/memories", responses=deps.error_responses)
    def memories(query: str = "") -> list[dict[str, Any]]:
        return deps.services().memory.list(query)

    @router.delete("/api/memories/{memory_id}", status_code=204, responses=deps.error_responses)
    def forget_memory(memory_id: str) -> None:
        if not deps.services().memory.forget(memory_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy memory.")

    @router.delete("/api/memories", status_code=204, responses=deps.error_responses)
    def forget_all_memories() -> None:
        deps.services().memory.forget_all()

    return router
