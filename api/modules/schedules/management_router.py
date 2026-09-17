"""Schedule mutation and run-management endpoints."""

from dataclasses import dataclass
from threading import Thread
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from api.contracts.requests import ScheduleUpdateRequest


@dataclass(frozen=True)
class ScheduleManagementDependencies:
    services: Callable[[], Any]
    schedule_model: Any
    project_model: Any
    schedule_repository: Any
    schedule_json: Callable[[Any], dict[str, Any]]
    schedule_run_json: Callable[[Any], dict[str, Any]]
    resolve_schedule_selection: Callable[[str | None, str | None, str | None], tuple[str, str]]
    current_user_id: Callable[[], str | None]
    record_project_activity: Callable[..., Any]
    schedule_run_email: Callable[..., tuple[str, str]]
    public_chat_url: Callable[..., str]
    schedule_worker: Callable[[Any], Any]
    schedule_not_found_error: str
    selected_project_not_found_error: str
    api_error_responses: dict


def build_router(deps: ScheduleManagementDependencies) -> APIRouter:
    router = APIRouter(tags=["Schedules"])

    @router.patch("/api/schedules/{schedule_id}", responses=deps.api_error_responses)
    def update_schedule(schedule_id: str, payload: ScheduleUpdateRequest) -> dict[str, Any]:
        current = deps.services().workspace.get(deps.schedule_model, schedule_id)
        if current is None:
            raise HTTPException(status_code=404, detail=deps.schedule_not_found_error)
        values = payload.model_dump(exclude_unset=True)
        starts_at = values.get("starts_at", current.starts_at)
        ends_at = values.get("ends_at", current.ends_at)
        if ends_at and ends_at < starts_at:
            raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
        project_id = values.get("project_id", current.project_id)
        if project_id and deps.services().workspace.get(deps.project_model, project_id) is None:
            raise HTTPException(status_code=422, detail=deps.selected_project_not_found_error)
        if values.get("status") == "active" and current.status == "completed" and current.recurrence == "once":
            raise HTTPException(status_code=422, detail="Lịch một lần đã hoàn tất; hãy tạo lịch mới để chạy lại.")
        if {"provider", "model"}.intersection(values):
            provider = values.get("provider", current.provider)
            model = values.get("model") if "model" in values else (current.model if "provider" not in values else None)
            try:
                values["provider"], values["model"] = deps.resolve_schedule_selection(provider, model, deps.current_user_id())
            except Exception as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        if any(key in values and values[key] != getattr(current, key) for key in ("starts_at", "recurrence")) and "next_run_at" not in values:
            values["next_run_at"] = values.get("starts_at", current.starts_at)
        item = deps.services().workspace.update(deps.schedule_model, schedule_id, **values)
        if item and {"provider", "model"}.intersection(values) and item.chat_id:
            deps.services().chats.update(item.chat_id, provider=item.provider, model=item.model)
        if item and item.project_id:
            deps.record_project_activity(item.project_id, "schedule.updated", "schedule", item.id, f"Đã cập nhật lịch {item.title}.")
        return deps.schedule_json(item)

    @router.delete("/api/schedules/{schedule_id}", status_code=204, responses=deps.api_error_responses)
    def delete_schedule(schedule_id: str) -> None:
        current = deps.services().workspace.get(deps.schedule_model, schedule_id)
        if current is None or not deps.services().workspace.delete(deps.schedule_model, schedule_id):
            raise HTTPException(status_code=404, detail=deps.schedule_not_found_error)
        if current.project_id:
            deps.record_project_activity(current.project_id, "schedule.deleted", "schedule", schedule_id, f"Đã xóa lịch {current.title}.")

    @router.get("/api/schedules/{schedule_id}/runs", responses=deps.api_error_responses)
    def list_schedule_runs(schedule_id: str, limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
        if deps.services().workspace.get(deps.schedule_model, schedule_id) is None:
            raise HTTPException(status_code=404, detail=deps.schedule_not_found_error)
        return [deps.schedule_run_json(item) for item in deps.schedule_repository(deps.services().chats.database).list_runs(schedule_id, limit)]

    @router.post("/api/schedules/{schedule_id}/run-now", status_code=202, responses=deps.api_error_responses)
    def run_schedule_now(schedule_id: str) -> dict[str, str]:
        schedule = deps.services().workspace.get(deps.schedule_model, schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail=deps.schedule_not_found_error)
        worker = deps.schedule_worker(deps.services())
        try:
            prepared = worker.start_manual(schedule_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if prepared is None:
            raise HTTPException(status_code=404, detail=deps.schedule_not_found_error)
        scheduled, chat, run_id = prepared
        Thread(target=worker.execute, args=(scheduled, run_id, True), daemon=True).start()
        return {"status": "running", "chatId": chat.id, "runId": run_id}

    @router.post("/api/schedules/{schedule_id}/runs/{run_id}/resend-email", responses=deps.api_error_responses)
    def resend_schedule_run_email(schedule_id: str, run_id: str) -> dict[str, Any]:
        schedule = deps.services().workspace.get(deps.schedule_model, schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail=deps.schedule_not_found_error)
        runs = deps.schedule_repository(deps.services().chats.database)
        run = runs.get_run(schedule_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy lần chạy.")
        if run.status != "succeeded":
            raise HTTPException(status_code=409, detail="Chỉ gửi lại email cho lần chạy đã hoàn tất.")
        if run.email_status == "sent":
            raise HTTPException(status_code=409, detail="Email của lần chạy này đã được gửi.")
        user = deps.services().auth.repository.get_user(deps.current_user_id())
        email = deps.services().email
        if not email.enabled or user is None or not user.email:
            raise HTTPException(status_code=422, detail="Chưa cấu hình SMTP hoặc tài khoản không có email.")
        subject, body = deps.schedule_run_email(schedule.title, run.finished_at or run.started_at, run.summary, deps.public_chat_url(deps.services().settings.app_web_url, schedule.chat_id) if schedule.chat_id else None)
        try:
            email.send(user.email, subject, body)
        except Exception as exc:
            runs.record_email(run_id, status="failed", error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return deps.schedule_run_json(runs.record_email(run_id, status="sent"))

    return router
