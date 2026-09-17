"""System-administration endpoints."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request

from agent_core.persistence.store import BackgroundJobRepository, ConnectorRepository
from api.contracts.requests import AdminModelStatusRequest, AdminUserStatusRequest


@dataclass(frozen=True)
class AdminRouteDependencies:
    services: Callable[[], Any]
    require_system_admin: Callable[[Request], Any]
    user_json: Callable[[Any], dict[str, Any]]
    error_responses: dict


def build_router(deps: AdminRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["System admin"])

    @router.get("/api/admin/overview", responses=deps.error_responses)
    def admin_overview(request: Request) -> dict[str, Any]:
        deps.require_system_admin(request)
        services = deps.services()
        configured = services.settings.configured_provider_models()
        providers = {name: {"models": [], "configured": bool(configured.get(name))} for name in services.settings.provider_models}
        for model in services.model_registry.list():
            providers.setdefault(model.provider, {"models": [], "configured": bool(configured.get(model.provider))})
            providers[model.provider]["models"].append({"id": model.model_id, "displayName": model.display_name, "isActive": model.is_active})
        return {"counts": services.auth.repository.system_counts(), "worker": BackgroundJobRepository(services.chats.database).worker_status(datetime.now(UTC)), "providers": providers}

    @router.get("/api/admin/users", responses=deps.error_responses)
    def admin_users(request: Request, q: str | None = Query(default=None, max_length=160), offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100)) -> dict[str, Any]:
        deps.require_system_admin(request)
        rows, total = deps.services().auth.repository.list_users(q, offset, limit)
        return {"items": [{**deps.user_json(user), "createdAt": user.created_at.isoformat(), "lastSignInAt": last.isoformat() if last else None} for user, last in rows], "total": total}

    @router.patch("/api/admin/users/{user_id}/active", responses=deps.error_responses)
    def admin_set_user_active(user_id: str, payload: AdminUserStatusRequest, request: Request) -> dict[str, Any]:
        admin = deps.require_system_admin(request)
        if user_id == admin.id and not payload.is_active:
            raise HTTPException(status_code=422, detail="Không thể tự vô hiệu hóa system admin.")
        user = deps.services().auth.repository.set_user_active(user_id, payload.is_active)
        if user is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy user.")
        deps.services().auth.repository.add_system_audit("user_activated" if payload.is_active else "user_deactivated", actor_user_id=admin.id, subject_user_id=user.id, summary=f"{'Kích hoạt' if payload.is_active else 'Vô hiệu hóa'} user.")
        return deps.user_json(user)

    @router.patch("/api/admin/models/{provider}/{model_id}/active", responses=deps.error_responses)
    def admin_set_model_active(provider: str, model_id: str, payload: AdminModelStatusRequest, request: Request) -> dict[str, Any]:
        admin = deps.require_system_admin(request)
        model = deps.services().model_registry.set_active(provider, model_id, payload.is_active)
        if model is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy model.")
        deps.services().auth.repository.add_system_audit("model_activated" if model.is_active else "model_deactivated", actor_user_id=admin.id, summary=f"{'Kích hoạt' if model.is_active else 'Vô hiệu hóa'} {model.provider}/{model.model_id}.")
        return {"id": model.model_id, "displayName": model.display_name, "isActive": model.is_active}

    @router.get("/api/admin/credentials", responses=deps.error_responses)
    def admin_credentials(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
        deps.require_system_admin(request)
        rows, total = deps.services().auth.repository.provider_credential_metadata(offset, limit)
        return {"items": [{"id": item.id, "userId": user.id, "userEmail": user.email, "provider": item.provider, "keyHint": item.key_hint, "validatedAt": item.validated_at.isoformat(), "updatedAt": item.updated_at.isoformat()} for item, user in rows], "total": total}

    @router.get("/api/admin/audit", responses=deps.error_responses)
    def admin_audit(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
        deps.require_system_admin(request)
        repository = deps.services().auth.repository
        rows, total = repository.list_system_audit(offset, limit)
        return {"items": [{"id": item.id, "eventType": item.event_type, "actorUserId": item.actor_user_id, "actorEmail": (repository.get_user(item.actor_user_id).email if item.actor_user_id and repository.get_user(item.actor_user_id) else None), "subjectUserId": item.subject_user_id, "subjectEmail": (repository.get_user(item.subject_user_id).email if item.subject_user_id and repository.get_user(item.subject_user_id) else None), "summary": item.summary, "createdAt": item.created_at.isoformat()} for item in rows], "total": total}

    @router.get("/api/admin/plugin-connections", responses=deps.error_responses)
    def admin_plugin_connections(request: Request, q: str | None = Query(default=None, max_length=160), connector_slug: str | None = Query(default=None, max_length=80), status: str | None = Query(default=None, max_length=32), offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100)) -> dict[str, Any]:
        deps.require_system_admin(request)
        rows, total = ConnectorRepository(deps.services().chats.database).list_connection_metadata(offset, limit, q, connector_slug, status)
        return {"items": [{"id": row["id"], "userId": row["user_id"], "userEmail": row["user_email"], "connectorSlug": row["connector_slug"], "status": row["status"], "scopeCount": len(row["scopes"] or []), "expiresAt": row["expires_at"].isoformat() if row["expires_at"] else None, "createdAt": row["created_at"].isoformat(), "updatedAt": row["updated_at"].isoformat()} for row in rows], "total": total}

    return router
