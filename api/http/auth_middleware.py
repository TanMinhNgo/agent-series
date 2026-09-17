"""Authentication and workspace authorization middleware."""

import json
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Request, Response


@dataclass(frozen=True)
class AuthMiddlewareDependencies:
    services: Callable[[], Any]
    session_cookie: str
    current_user_id: Any
    current_workspace_id: Any
    json_media_type: str


def install(app: Any, deps: AuthMiddlewareDependencies) -> None:
    @app.middleware("http")
    async def require_authenticated_api_user(request: Request, call_next):
        path = request.url.path
        public_prefixes = ("/api/health", "/api/config", "/api/auth/", "/api/public/shares/", "/docs", "/openapi.json")
        if not path.startswith("/api/") or path.startswith(public_prefixes) or request.method == "OPTIONS":
            return await call_next(request)
        user = deps.services().auth.session_user(request.cookies.get(deps.session_cookie))
        if user is None:
            return Response(content=json.dumps({"detail": "Cần đăng nhập để truy cập workspace."}, ensure_ascii=False), status_code=401, media_type=deps.json_media_type)
        requested_workspace_id = request.headers.get("X-Workspace-ID")
        membership = deps.services().workspace.membership(requested_workspace_id, user.id) if requested_workspace_id else deps.services().workspace.default_for_user(user.id)
        accepting_invitation = path.endswith("/accept")
        if membership is None and not (path == "/api/workspaces" or accepting_invitation):
            return Response(content=json.dumps({"detail": "Không tìm thấy workspace bạn có quyền truy cập."}, ensure_ascii=False), status_code=403, media_type=deps.json_media_type)
        if membership and request.method in {"POST", "PATCH", "PUT", "DELETE"} and membership.role == "viewer" and not accepting_invitation and path != "/api/workspaces":
            return Response(content=json.dumps({"detail": "Bạn chỉ có quyền xem trong workspace này."}, ensure_ascii=False), status_code=403, media_type=deps.json_media_type)
        token = deps.current_user_id.set(user.id)
        workspace_token = deps.current_workspace_id.set(membership.workspace_id) if membership else None
        request.state.user = user
        request.state.workspace_membership = membership
        try:
            return await call_next(request)
        finally:
            if workspace_token is not None:
                deps.current_workspace_id.reset(workspace_token)
            deps.current_user_id.reset(token)
