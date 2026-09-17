"""Schedule CRUD endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from agent_core.persistence.store import Project, Schedule
from agent_core.runtime.credentials import CredentialError
from api.contracts.requests import ScheduleRequest


@dataclass(frozen=True)
class ScheduleRouteDependencies:
    services: Callable[[], Any]
    schedule_json: Callable[[Any], dict[str, Any]]
    resolve_selection: Callable[..., tuple[str, str]]
    current_user_id: Any
    record_project_activity: Callable[..., None]
    selected_project_not_found_error: str
    error_responses: dict


def build_router(deps: ScheduleRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Schedules"])

    @router.get("/api/schedules", responses=deps.error_responses)
    def list_schedules() -> list[dict[str, Any]]:
        return [deps.schedule_json(item) for item in deps.services().workspace.list(Schedule)]

    @router.post("/api/schedules", status_code=201, responses=deps.error_responses)
    def create_schedule(payload: ScheduleRequest) -> dict[str, Any]:
        if payload.ends_at and payload.ends_at < payload.starts_at:
            raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
        if payload.project_id and deps.services().workspace.get(Project, payload.project_id) is None:
            raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
        values = payload.model_dump()
        try:
            values["provider"], values["model"] = deps.resolve_selection(payload.provider, payload.model, deps.current_user_id.get())
        except (ValueError, CredentialError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        values["next_run_at"] = values["next_run_at"] or values["starts_at"]
        schedule = deps.services().workspace.create(Schedule, **values)
        if schedule.project_id:
            deps.record_project_activity(schedule.project_id, "schedule.created", "schedule", schedule.id, f"Đã tạo lịch {schedule.title}.")
        return deps.schedule_json(schedule)

    return router
