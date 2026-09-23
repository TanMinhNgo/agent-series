"""Reusable workflow recipe catalog."""

from contextlib import contextmanager
from typing import Callable
from fastapi import APIRouter, HTTPException, Header, Query
from agent_core.workflows.contracts import WorkflowConfig, RunInput, RetryInput, WorkflowScheduleInput
from agent_core.workflows.repository import WorkflowRepository, WorkflowConflict
from agent_core.workflows.executor import authorize, validate_config
from agent_core.persistence.store import Schedule, Workflow, current_user_id, current_workspace_id
from sqlalchemy import select



@contextmanager
def _access(services: Callable, project_id: str, write: bool = False):
    try:
        app_services = services()
        authorize(app_services, project_id, write)
        yield app_services, WorkflowRepository(app_services.chats.database)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except WorkflowConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _start_run(services: Callable, project_id: str, workflow_id: str, payload: RunInput, idempotency_key: str | None):
    with _access(services, project_id, True) as (app_services, repo):
        workflow = repo.get(project_id, workflow_id)
        validate_config(app_services, project_id, workflow.config)
        if idempotency_key and len(idempotency_key) > 160:
            raise HTTPException(422, "Idempotency-Key quá dài.")
        if idempotency_key is not None and not idempotency_key.strip():
            raise HTTPException(422, "Idempotency-Key không được để trống.")
        return run_json(repo.enqueue(workflow, payload, idempotency_key=idempotency_key))


def _create_schedule(services: Callable, project_id: str, workflow_id: str, payload: WorkflowScheduleInput):
    with _access(services, project_id, True) as (app_services, repo):
        workflow = repo.get(project_id, workflow_id)
        validate_config(app_services, project_id, workflow.config)
        with app_services.chats.database.session() as session:
            session.scalar(select(Workflow.id).where(Workflow.id == workflow_id).with_for_update())
            if session.scalar(select(Schedule.id).where(Schedule.workflow_id == workflow_id)):
                raise WorkflowConflict("Workflow đã có lịch. Hãy tạm dừng hoặc xóa lịch hiện có trước.")
            schedule = Schedule(title=payload.title or workflow.name, starts_at=payload.nextRunAt,
                project_id=project_id, workflow_id=workflow.id,
                recurrence="daily" if workflow.config["template"] == "daily-ai-digest" else "weekly",
                status="active", next_run_at=payload.nextRunAt, timezone=payload.timezone,
                user_id=current_user_id.get(), workspace_id=current_workspace_id.get())
            session.add(schedule); session.commit()
            return {"id": schedule.id, "workflowId": workflow.id, "nextRunAt": schedule.next_run_at.isoformat(), "recurrence": schedule.recurrence, "timezone": schedule.timezone}


def build_router(error_responses: dict, services=None) -> APIRouter:
    router = APIRouter(tags=["Workflows"], responses=error_responses)

    @router.get("/api/workflow-recipes")
    def workflow_recipes() -> list[dict[str, object]]:
        return [
            {"id": "daily-ai-digest", "title": "Daily AI digest", "description": "Tóm tắt nguồn web lấy khi lịch chạy; chưa xác minh ngày xuất bản.", "sourceType": "web", "prompt": "Tổng hợp nguồn web vừa tìm được về AI, nêu nguồn; không khẳng định ngày xuất bản khi nguồn không cung cấp.", "recurrence": "daily", "notifyEmail": True, "requiresRepository": False},
            {"id": "github-weekly-summary", "title": "GitHub weekly summary", "description": "Tổng hợp issue và PR cập nhật trong kỳ.", "sourceType": "github", "prompt": "Dùng GitHub đã chọn cho Project để tổng hợp issue, PR và workflow trong tuần; tạo báo cáo Markdown có nguồn.", "recurrence": "weekly", "notifyEmail": True, "requiresRepository": True},
            {"id": "project-report", "title": "Project report", "description": "Tổng hợp các tài liệu đã ghim trong Project.", "sourceType": "library", "prompt": "Tổng hợp tiến độ Project từ các nguồn đã ghim và tạo báo cáo Markdown.", "recurrence": "weekly", "notifyEmail": True, "requiresRepository": False},
        ]

    def access(project_id, write=False):
        return _access(services, project_id, write)

    @router.get("/api/projects/{project_id}/workflows")
    def list_workflows(project_id: str):
        with access(project_id) as (_, repo):
            return [workflow_json(item) for item in repo.list(project_id)]

    @router.post("/api/projects/{project_id}/workflows", status_code=201)
    def create_workflow(project_id: str, payload: WorkflowConfig):
        with access(project_id, True) as (app_services, repo):
            validate_config(app_services, project_id, payload.model_dump())
            return workflow_json(repo.save(project_id, payload))

    @router.patch("/api/projects/{project_id}/workflows/{workflow_id}")
    def edit_workflow(project_id: str, workflow_id: str, payload: dict):
        with access(project_id, True) as (app_services, repo):
            previous = repo.get(project_id, workflow_id)
            config = WorkflowConfig.model_validate({**previous.config, **payload})
            validate_config(app_services, project_id, config.model_dump())
            return workflow_json(repo.save(project_id, config, workflow_id))

    @router.post("/api/projects/{project_id}/workflows/{workflow_id}/runs", status_code=202)
    def start_run(project_id: str, workflow_id: str, payload: RunInput, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        return _start_run(services, project_id, workflow_id, payload, idempotency_key)

    @router.post("/api/projects/{project_id}/workflows/{workflow_id}/schedule", status_code=201)
    def create_schedule(project_id: str, workflow_id: str, payload: WorkflowScheduleInput):
        return _create_schedule(services, project_id, workflow_id, payload)

    @router.post("/api/projects/{project_id}/workflow-runs/{run_id}/cancel")
    def cancel_run(project_id: str, run_id: str):
        with access(project_id, True) as (_, repo):
            return run_json(repo.cancel(project_id, run_id))

    @router.post("/api/projects/{project_id}/workflow-runs/{run_id}/retry")
    def retry_run(project_id: str, run_id: str, payload: RetryInput | None = None):
        with access(project_id, True) as (_, repo):
            payload = payload or RetryInput()
            return run_json(repo.retry_run(project_id, run_id, payload.stepId, payload.confirmResend))

    @router.get("/api/projects/{project_id}/workflows/{workflow_id}/runs")
    def list_runs(project_id: str, workflow_id: str, status: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100)):
        with access(project_id) as (_, repo):
            return [run_json(item) for item in repo.runs(project_id, workflow_id, status=status, limit=limit)]

    @router.get("/api/projects/{project_id}/workflow-runs/{run_id}")
    def run_detail(project_id: str, run_id: str):
        with access(project_id) as (app_services, repo):
            run, steps = repo.detail(project_id, run_id)
            member = app_services.workspace.membership(current_workspace_id.get(), current_user_id.get())
            return {**run_json(run), "canWrite": member.role in {"owner", "editor"}, "snapshot": run.snapshot, "steps": [{"id": item.step_id, "status": item.status, "attempt": item.attempt, "retryAt": iso(item.retry_at), "output": ({"reason": "Đang lưu báo cáo."} if item.step_id == "artifact" and item.status != "succeeded" else item.output), "error": item.error, "startedAt": iso(item.started_at), "finishedAt": iso(item.finished_at)} for item in steps]}

    return router


def iso(value):
    return value.isoformat() if value else None


def workflow_json(item):
    return {"id": item.id, "projectId": item.project_id, "revision": item.revision, **item.config}


def run_json(item):
    return {"id": item.id, "workflowId": item.workflow_id, "projectId": item.project_id, "status": item.status, "error": item.error, "artifactId": item.artifact_id, "cancelRequested": item.cancel_requested, "startsAt": iso(item.starts_at), "endsAt": iso(item.ends_at), "createdAt": iso(item.created_at), "startedAt": iso(item.started_at), "finishedAt": iso(item.finished_at)}
