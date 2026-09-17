"""Per-user API key endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request

from agent_core.runtime.credentials import CredentialError
from api.contracts.requests import ApiKeyRequest


@dataclass(frozen=True)
class SettingsRouteDependencies:
    services: Callable[[], Any]
    credential_json: Callable[[Any], dict[str, Any]]
    authentication_required_error: str
    error_responses: dict


def build_router(deps: SettingsRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Settings"])

    def user(request: Request):
        value = getattr(request.state, "user", None)
        if value is None:
            raise HTTPException(status_code=401, detail=deps.authentication_required_error)
        return value

    @router.get("/api/settings/api-keys", responses=deps.error_responses)
    def list_api_keys(request: Request) -> dict[str, Any]:
        return {"items": [deps.credential_json(item) for item in deps.services().credentials.list_metadata(user(request).id)]}

    @router.put("/api/settings/api-keys/{provider}", responses=deps.error_responses)
    def save_api_key(provider: str, payload: ApiKeyRequest, request: Request) -> dict[str, Any]:
        current_user = user(request)
        try:
            item = deps.services().credentials.save(current_user.id, provider, payload.api_key)
        except CredentialError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        deps.services().auth.repository.add_system_audit("user_api_key_saved", actor_user_id=current_user.id, summary=f"Cập nhật API key {provider}.")
        return deps.credential_json(item)

    @router.delete("/api/settings/api-keys/{provider}", status_code=204, responses=deps.error_responses)
    def delete_api_key(provider: str, request: Request) -> None:
        current_user = user(request)
        try:
            deleted = deps.services().credentials.delete(current_user.id, provider)
        except CredentialError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Chưa có API key cho provider này.")
        deps.services().auth.repository.add_system_audit("user_api_key_deleted", actor_user_id=current_user.id, summary=f"Xóa API key {provider}.")

    return router
