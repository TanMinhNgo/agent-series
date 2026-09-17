"""Schedule proposal confirmation endpoints."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select


@dataclass(frozen=True)
class ScheduleProposalDependencies:
    services: Callable[[], Any]
    chat_model: Any
    chat_message_model: Any
    schedule_model: Any
    proposal_payload_model: Any
    schedule_json: Callable[[Any], dict[str, Any]]
    chat_not_found_error: str
    api_error_responses: dict


def build_router(deps: ScheduleProposalDependencies) -> APIRouter:
    router = APIRouter(tags=["Schedules"])

    def find_block(session: Any, chat_id: str, proposal_id: str):
        messages = session.scalars(
            select(deps.chat_message_model)
            .where(deps.chat_message_model.chat_id == chat_id, deps.chat_message_model.role == "assistant")
            .order_by(deps.chat_message_model.position)
            .with_for_update()
        ).all()
        for message in messages:
            blocks = deepcopy(message.content_blocks or [])
            for block in blocks:
                config = block.get("config") if isinstance(block, dict) else None
                if isinstance(config, dict) and block.get("type") == "schedule-proposal" and config.get("proposalId") == proposal_id:
                    return message, blocks, config
        raise HTTPException(status_code=404, detail="Không tìm thấy đề xuất lịch trình.")

    def mutate(chat_id: str, proposal_id: str, action: Literal["confirm", "dismiss"]) -> dict[str, Any]:
        source_chat = deps.services().chats.get(chat_id)
        if source_chat is None:
            raise HTTPException(status_code=404, detail=deps.chat_not_found_error)
        with deps.services().chats.database.session() as session:
            message, blocks, config = find_block(session, chat_id, proposal_id)
            status = config.get("status")
            if action == "confirm":
                if status == "confirmed":
                    return {"status": "confirmed", "proposalId": proposal_id, "scheduleId": config.get("scheduleId")}
                if status != "pending":
                    raise HTTPException(status_code=409, detail="Đề xuất này đã bị hủy.")
                try:
                    proposal = deps.proposal_payload_model.model_validate(config)
                except Exception as exc:
                    raise HTTPException(status_code=422, detail="Đề xuất lịch trình không hợp lệ.") from exc
                schedule = deps.schedule_model(
                    title=proposal.title,
                    prompt=proposal.prompt,
                    starts_at=proposal.starts_at,
                    recurrence=proposal.recurrence,
                    timezone=proposal.timezone,
                    project_id=config.get("projectId"),
                    provider=source_chat.provider,
                    model=source_chat.model,
                    status="active",
                    next_run_at=proposal.starts_at,
                )
                session.add(schedule)
                session.flush()
                config.update(status="confirmed", scheduleId=schedule.id)
                message.content_blocks = blocks
                session.commit()
                return {"status": "confirmed", "proposalId": proposal_id, "scheduleId": schedule.id, "schedule": deps.schedule_json(schedule)}
            if status == "pending":
                config["status"] = "dismissed"
                message.content_blocks = blocks
                session.commit()
            return {"status": config.get("status"), "proposalId": proposal_id}

    @router.post("/api/chats/{chat_id}/schedule-proposals/{proposal_id}/confirm", status_code=201, responses=deps.api_error_responses)
    def confirm_chat_schedule_proposal(chat_id: str, proposal_id: str) -> dict[str, Any]:
        return mutate(chat_id, proposal_id, "confirm")

    @router.post("/api/chats/{chat_id}/schedule-proposals/{proposal_id}/dismiss", responses=deps.api_error_responses)
    def dismiss_chat_schedule_proposal(chat_id: str, proposal_id: str) -> dict[str, Any]:
        return mutate(chat_id, proposal_id, "dismiss")

    return router
