"""Project overview and creation endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from agent_core.persistence.store import BackgroundJobRepository, Chat, Document, LibraryAsset, Project, Schedule, User
from api.contracts.requests import DeleteProjectRequest, ProjectConnectorScopeRequest, ProjectRequest
from api.modules.projects.service import delete_project as delete_project_service


@dataclass(frozen=True)
class ProjectRouteDependencies:
    services: Callable[[], Any]
    project_json: Callable[[Any], dict[str, Any]]
    chat_json: Callable[[Any], dict[str, Any]]
    document_json: Callable[[Any, Any], dict[str, Any]]
    library_asset_json: Callable[[Any], dict[str, Any]]
    schedule_json: Callable[[Any], dict[str, Any]]
    project_activity_json: Callable[[Any, Any], dict[str, Any]]
    record_project_activity: Callable[..., None]
    project_not_found_error: str
    error_responses: dict
    queue_file_cleanup: Callable[..., None]


def build_router(deps: ProjectRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Projects"])

    @router.get("/api/projects", responses=deps.error_responses)
    def list_projects() -> list[dict[str, Any]]:
        return [deps.project_json(item) for item in deps.services().workspace.list(Project)]

    @router.post("/api/projects", status_code=201, responses=deps.error_responses)
    def create_project(payload: ProjectRequest) -> dict[str, Any]:
        project = deps.services().workspace.create(Project, **payload.model_dump())
        deps.record_project_activity(project.id, "project.created", "project", project.id, f"Đã tạo Project {project.name}.")
        return deps.project_json(project)

    @router.get("/api/projects/{project_id}", responses=deps.error_responses)
    def get_project(project_id: str) -> dict[str, Any]:
        services = deps.services()
        project = services.workspace.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=deps.project_not_found_error)
        with services.chats.database.session() as session:
            chats = list(session.scalars(select(Chat).where(Chat.project_id == project_id).order_by(Chat.updated_at.desc())))
            documents = list(session.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())))
            assets = list(session.scalars(select(LibraryAsset).where(LibraryAsset.project_id == project_id).order_by(LibraryAsset.created_at.desc())))
            schedules = list(session.scalars(select(Schedule).where(Schedule.project_id == project_id).order_by(Schedule.starts_at.desc())))
            activity = services.workspace.project_activity(project_id)
            actor_ids = [item.actor_user_id for item in activity if item.actor_user_id]
            actors = {item.id: item for item in session.scalars(select(User).where(User.id.in_(actor_ids))).all()} if actor_ids else {}
        jobs = BackgroundJobRepository(services.chats.database)
        scopes = services.workspace.connector_scopes(project_id)
        return {"project": deps.project_json(project), "chats": [deps.chat_json(item) for item in chats[:8]], "documents": [deps.document_json(item, jobs.latest_for_document(item.id)) for item in documents], "assets": [deps.library_asset_json(item) for item in assets[:12]], "projectSources": [deps.library_asset_json(item) for item in assets if item.is_project_source], "schedules": [deps.schedule_json(item) for item in schedules[:8]], "activity": [deps.project_activity_json(item, actors.get(item.actor_user_id)) for item in activity], "connectorScopes": [{"connectorSlug": item.connector_slug, "config": item.config} for item in scopes]}

    @router.put("/api/projects/{project_id}/connector-scopes", responses=deps.error_responses)
    def save_project_connector_scope(project_id: str, payload: ProjectConnectorScopeRequest) -> dict[str, Any]:
        if deps.services().workspace.get(Project, project_id) is None:
            raise HTTPException(status_code=404, detail=deps.project_not_found_error)
        scope = deps.services().workspace.save_connector_scope(project_id, payload.connector_slug, payload.config)
        deps.record_project_activity(project_id, "connector.scope_updated", "connector", scope.id, f"Đã cập nhật nguồn {payload.connector_slug} cho Project.")
        return {"connectorSlug": scope.connector_slug, "config": scope.config}

    @router.patch("/api/projects/{project_id}", responses=deps.error_responses)
    def update_project(project_id: str, payload: ProjectRequest) -> dict[str, Any]:
        item = deps.services().workspace.update(Project, project_id, **payload.model_dump())
        if item is None:
            raise HTTPException(status_code=404, detail=deps.project_not_found_error)
        deps.record_project_activity(project_id, "project.updated", "project", project_id, f"Đã cập nhật Project {item.name}.")
        return deps.project_json(item)

    @router.delete("/api/projects/{project_id}", responses=deps.error_responses)
    def delete_project(project_id: str, payload: DeleteProjectRequest) -> dict[str, Any]:
        try:
            return delete_project_service(deps.services().chats.database, project_id, payload.confirm_name, deps.queue_file_cleanup, deps.project_not_found_error)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
