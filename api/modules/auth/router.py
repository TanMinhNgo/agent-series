"""Authentication HTTP endpoints."""

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from agent_core.runtime.auth import AuthError


@dataclass(frozen=True)
class AuthRouteDependencies:
    services: Callable[[], Any]
    user_json: Callable[[Any], dict[str, Any]]
    session_cookie: str
    error_responses: dict


def build_router(deps: AuthRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Authentication"])

    @router.get("/api/auth/me", responses=deps.error_responses)
    def auth_me(request: Request) -> dict[str, Any]:
        user = deps.services().auth.session_user(request.cookies.get(deps.session_cookie))
        return {"user": deps.user_json(user) if user else None}

    @router.get("/api/auth/google/authorize", responses=deps.error_responses)
    def start_google_sign_in(email: str | None = Query(default=None, max_length=320)) -> RedirectResponse:
        try:
            return RedirectResponse(deps.services().auth.google_authorization_url(email), status_code=302)
        except AuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/api/auth/google/callback", responses=deps.error_responses)
    def complete_google_sign_in(code: str | None = Query(default=None), state: str | None = Query(default=None), error: str | None = Query(default=None)) -> RedirectResponse:
        base_url = deps.services().settings.app_web_url
        if error or not code or not state:
            return RedirectResponse(f"{base_url}/login?{urlencode({'authError': 'Google sign-in đã bị hủy hoặc không hoàn tất.'})}", status_code=303)
        try:
            _user, session_token = deps.services().auth.complete_google_sign_in(code, state)
        except AuthError as exc:
            return RedirectResponse(f"{base_url}/login?{urlencode({'authError': str(exc)})}", status_code=303)
        response = RedirectResponse(f"{base_url}/?auth=google", status_code=303)
        response.set_cookie(deps.session_cookie, session_token, httponly=True, samesite="lax", secure=base_url.startswith("https://"), max_age=deps.services().settings.auth_session_days * 86400, path="/")
        return response

    @router.post("/api/auth/logout", status_code=204, responses=deps.error_responses)
    def auth_logout(request: Request, response: Response) -> None:
        deps.services().auth.logout(request.cookies.get(deps.session_cookie))
        response.delete_cookie(deps.session_cookie, path="/")

    return router
