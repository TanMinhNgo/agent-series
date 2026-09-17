"""OAuth authorize, callback and disconnect endpoints."""

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse


@dataclass(frozen=True)
class ConnectorOAuthDependencies:
    services: Callable[[], Any]
    set_plugin_connection: Callable[[str, str, bool | None], Any]
    google_slug: str
    github_slug: str
    google_error: type[Exception]
    github_error: type[Exception]
    api_error_responses: dict


def build_router(deps: ConnectorOAuthDependencies) -> APIRouter:
    router = APIRouter(tags=["Connectors"])

    @router.post("/api/connectors/google/authorize", responses=deps.api_error_responses)
    def google_authorize(drive_write: bool = Query(default=False, alias="driveWrite")) -> dict[str, str]:
        if deps.services().workspace.get_plugin_by_catalog_slug(deps.google_slug) is None:
            raise HTTPException(status_code=422, detail="Hãy thêm Google Workspace từ catalog trước khi kết nối.")
        try:
            return {"authorizationUrl": deps.services().google_workspace.authorization_url(drive_write)}
        except deps.google_error as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/api/connectors/google/callback", include_in_schema=False)
    def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
        base_url = deps.services().settings.app_web_url
        if error or not code or not state:
            return RedirectResponse(f"{base_url}/plugins?{urlencode({'google': 'cancelled'})}", status_code=303)
        try:
            deps.services().google_workspace.complete_authorization(code, state)
            deps.set_plugin_connection(deps.google_slug, "connected")
            user = request.state.user
            deps.services().auth.repository.add_system_audit("plugin_connected", actor_user_id=user.id, subject_user_id=user.id, summary="Đã kết nối Google Workspace (chỉ đọc).")
            result = "connected"
        except deps.google_error:
            result = "failed"
        return RedirectResponse(f"{base_url}/plugins?{urlencode({'google': result})}", status_code=303)

    @router.delete("/api/connectors/google", status_code=204, responses=deps.api_error_responses)
    def google_disconnect(request: Request) -> None:
        deps.services().google_workspace.disconnect()
        deps.set_plugin_connection(deps.google_slug, "not_connected", enabled=False)
        user = request.state.user
        deps.services().auth.repository.add_system_audit("plugin_disconnected", actor_user_id=user.id, subject_user_id=user.id, summary="Đã ngắt Google Workspace.")

    @router.post("/api/connectors/github/authorize", responses=deps.api_error_responses)
    def github_authorize() -> dict[str, str]:
        if deps.services().workspace.get_plugin_by_catalog_slug(deps.github_slug) is None:
            raise HTTPException(status_code=422, detail="Hãy thêm GitHub từ catalog trước khi kết nối.")
        try:
            return {"authorizationUrl": deps.services().github.authorization_url()}
        except deps.github_error as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/api/connectors/github/callback", include_in_schema=False)
    def github_callback(request: Request, installation_id: str | None = None, state: str | None = None, setup_action: str | None = None) -> RedirectResponse:
        base_url = deps.services().settings.app_web_url
        if setup_action == "update" or not installation_id or not state:
            return RedirectResponse(f"{base_url}/plugins?{urlencode({'github': 'cancelled'})}", status_code=303)
        try:
            deps.services().github.complete_installation(installation_id, state)
            deps.set_plugin_connection(deps.github_slug, "connected")
            user = request.state.user
            deps.services().auth.repository.add_system_audit("plugin_connected", actor_user_id=user.id, subject_user_id=user.id, summary="Đã kết nối GitHub App (chỉ đọc).")
            result = "connected"
        except deps.github_error:
            result = "failed"
        return RedirectResponse(f"{base_url}/plugins?{urlencode({'github': result})}", status_code=303)

    @router.delete("/api/connectors/github", status_code=204, responses=deps.api_error_responses)
    def github_disconnect(request: Request) -> None:
        deps.services().github.disconnect()
        deps.set_plugin_connection(deps.github_slug, "not_connected", enabled=False)
        user = request.state.user
        deps.services().auth.repository.add_system_audit("plugin_disconnected", actor_user_id=user.id, subject_user_id=user.id, summary="Đã ngắt GitHub App.")

    return router
