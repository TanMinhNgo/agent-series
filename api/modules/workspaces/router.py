"""Workspace membership and invitation endpoints."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import or_, select

from api.contracts.requests import WorkspaceInvitationRequest, WorkspaceMemberRoleRequest, WorkspaceRequest


@dataclass(frozen=True)
class WorkspaceDependencies:
    services: Callable[[], Any]
    current_workspace_id: Callable[[], str | None]
    workspace_json: Callable[..., dict[str, Any]]
    invitation_json: Callable[[Any], dict[str, Any]]
    record_workspace_activity: Callable[..., Any]
    api_error_responses: dict
    workspace_member_model: Any
    workspace_invitation_model: Any
    user_model: Any


def _create_invitation(deps: WorkspaceDependencies, payload: WorkspaceInvitationRequest, request: Request) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Email lời mời không hợp lệ.")
    item = deps.services().workspace.invite(deps.current_workspace_id(), email, payload.role, request.state.user.id, datetime.now(UTC) + timedelta(days=7))
    deps.record_workspace_activity("workspace.invitation_created", "workspace_invitation", item.id, f"Đã mời {email} vào workspace với quyền {payload.role}.")
    result = deps.invitation_json(item)
    result["inviteUrl"] = f"{deps.services().settings.app_web_url}/?invite={item.id}"
    result["emailStatus"] = "pending"
    if deps.services().email.enabled:
        try:
            deps.services().email.send(email, "Lời mời vào Agent Series workspace", f"Bạn được mời vào workspace Agent Series với quyền {payload.role}.\n\nMở lời mời: {result['inviteUrl']}")
            result["emailStatus"] = "sent"
        except Exception:
            pass
    return result


def _find_invitable_users(deps: WorkspaceDependencies, q: str) -> list[dict[str, str | None]]:
    workspace_id, term = deps.current_workspace_id(), q.strip()
    with deps.services().chats.database.session() as session:
        existing = select(deps.workspace_member_model.user_id).where(deps.workspace_member_model.workspace_id == workspace_id)
        pending = select(deps.workspace_invitation_model.email).where(deps.workspace_invitation_model.workspace_id == workspace_id)
        statement = select(deps.user_model).where(deps.user_model.is_active.is_(True), deps.user_model.id.not_in(existing), deps.user_model.email.not_in(pending), or_(deps.user_model.email.ilike(f"%{term}%"), deps.user_model.display_name.ilike(f"%{term}%"))).order_by(deps.user_model.email).limit(10).execution_options(skip_user_scope=True)
        admin_email = (deps.services().settings.system_admin_email or "").strip().lower()
        return [{"id": user.id, "email": user.email, "displayName": user.display_name} for user in session.scalars(statement) if user.email.lower() != admin_email]


def build_router(deps: WorkspaceDependencies) -> APIRouter:
    router = APIRouter(tags=["Workspaces"])

    def owner(request: Request):
        membership = getattr(request.state, "workspace_membership", None)
        if membership is None or membership.role != "owner":
            raise HTTPException(status_code=403, detail="Chỉ owner workspace mới được thực hiện thao tác này.")
        return membership

    @router.get("/api/workspaces", responses=deps.api_error_responses)
    def list_workspaces(request: Request) -> list[dict[str, Any]]:
        user = request.state.user
        return [deps.workspace_json(item, membership) for item, membership in deps.services().workspace.list_for_user(user.id)]

    @router.post("/api/workspaces", status_code=201, responses=deps.api_error_responses)
    def create_workspace(payload: WorkspaceRequest, request: Request) -> dict[str, Any]:
        item = deps.services().workspace.create_workspace(request.state.user.id, payload.name.strip())
        return deps.workspace_json(item, deps.services().workspace.membership(item.id, request.state.user.id))

    @router.get("/api/workspaces/current/members", responses=deps.api_error_responses)
    def list_workspace_members(request: Request) -> list[dict[str, Any]]:
        owner(request)
        with deps.services().chats.database.session() as session:
            rows = session.execute(select(deps.workspace_member_model, deps.user_model).join(deps.user_model).where(deps.workspace_member_model.workspace_id == deps.current_workspace_id()).execution_options(skip_user_scope=True)).all()
        return [{"userId": member.user_id, "email": user.email, "displayName": user.display_name, "role": member.role} for member, user in rows]

    @router.get("/api/workspaces/current/invitations", responses=deps.api_error_responses)
    def list_workspace_invitations(request: Request) -> list[dict[str, Any]]:
        owner(request)
        return [deps.invitation_json(item) for item in deps.services().workspace.invitations(deps.current_workspace_id())]

    @router.get("/api/workspaces/current/invitable-users", responses=deps.api_error_responses)
    def find_invitable_workspace_users(request: Request, q: str = Query(min_length=2, max_length=160)) -> list[dict[str, str | None]]:
        owner(request)
        return _find_invitable_users(deps, q)

    @router.post("/api/workspaces/current/invitations", status_code=201, responses=deps.api_error_responses)
    def create_workspace_invitation(payload: WorkspaceInvitationRequest, request: Request) -> dict[str, Any]:
        owner(request)
        return _create_invitation(deps, payload, request)

    @router.delete("/api/workspaces/current/invitations/{invitation_id}", status_code=204, responses=deps.api_error_responses)
    def cancel_workspace_invitation(invitation_id: str, request: Request) -> None:
        owner(request)
        if not deps.services().workspace.cancel_invitation(deps.current_workspace_id(), invitation_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy lời mời.")
        deps.record_workspace_activity("workspace.invitation_revoked", "workspace_invitation", invitation_id, "Đã thu hồi lời mời vào workspace.")

    @router.patch("/api/workspaces/current/members/{user_id}", responses=deps.api_error_responses)
    def update_workspace_member(user_id: str, payload: WorkspaceMemberRoleRequest, request: Request) -> dict[str, str]:
        membership = owner(request)
        if membership.user_id == user_id and payload.role != "owner":
            raise HTTPException(status_code=422, detail="Owner hiện tại không thể tự hạ quyền.")
        item = deps.services().workspace.update_member_role(deps.current_workspace_id(), user_id, payload.role)
        if item is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy thành viên.")
        return {"userId": item.user_id, "role": item.role}

    @router.delete("/api/workspaces/current/members/{user_id}", status_code=204, responses=deps.api_error_responses)
    def remove_workspace_member(user_id: str, request: Request) -> None:
        membership = owner(request)
        if membership.user_id == user_id:
            raise HTTPException(status_code=422, detail="Owner hiện tại không thể tự rời workspace.")
        if not deps.services().workspace.remove_member(deps.current_workspace_id(), user_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy thành viên.")

    @router.post("/api/workspaces/invitations/{invitation_id}/accept", responses=deps.api_error_responses)
    def accept_workspace_invitation(invitation_id: str, request: Request) -> dict[str, str]:
        member = deps.services().workspace.accept_invitation(invitation_id, request.state.user.id, request.state.user.email, datetime.now(UTC))
        if member is None:
            raise HTTPException(status_code=404, detail="Lời mời không tồn tại, đã hết hạn hoặc không dành cho tài khoản này.")
        return {"workspaceId": member.workspace_id, "role": member.role}

    return router
