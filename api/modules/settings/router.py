"""Per-user API key endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from agent_core.runtime.credentials import CredentialError
from api.contracts.requests import ApiKeyRequest


@dataclass(frozen=True)
class SettingsRouteDependencies:
    services: Callable[[], Any]
    credential_json: Callable[[Any], dict[str, Any]]
    authentication_required_error: str
    error_responses: dict
    available_provider_models: Callable[..., dict[str, list[str]]]


class AccountSettingsRequest(BaseModel):
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    theme: str
    custom_instructions: str = Field(alias="customInstructions", max_length=10000)
    auto_learn: bool = Field(alias="autoLearn")
    default_provider: str | None = Field(default=None, alias="defaultProvider", min_length=1, max_length=32)
    default_model: str | None = Field(default=None, alias="defaultModel", min_length=1, max_length=160)

    @model_validator(mode="after")
    def valid_values(self):
        self.display_name = self.display_name.strip()
        if not self.display_name or self.theme not in {"system", "light", "dark"}:
            raise ValueError("Tên hoặc giao diện không hợp lệ.")
        if bool(self.default_provider) != bool(self.default_model):
            raise ValueError("Chọn cả provider và model mặc định.")
        return self


def build_router(deps: SettingsRouteDependencies) -> APIRouter:
    router = APIRouter(tags=["Settings"])

    def user(request: Request):
        value = getattr(request.state, "user", None)
        if value is None:
            raise HTTPException(status_code=401, detail=deps.authentication_required_error)
        return value

    @router.get("/api/settings", responses=deps.error_responses)
    def get_settings(request: Request) -> dict[str, Any]:
        current_user = user(request)
        return {"displayName": current_user.display_name or current_user.email.split("@", 1)[0], "email": current_user.email,
                "avatarUrl": current_user.avatar_url, **deps.services().personalization.settings(current_user.id)}

    @router.put("/api/settings", responses=deps.error_responses)
    def update_settings(payload: AccountSettingsRequest, request: Request) -> dict[str, Any]:
        current_user = user(request)
        available = deps.available_provider_models(current_user.id)
        if payload.default_provider and payload.default_model not in available.get(payload.default_provider, []):
            raise HTTPException(status_code=422, detail="Provider hoặc model mặc định không khả dụng.")
        updated = deps.services().auth.repository.update_profile(current_user.id, display_name=payload.display_name)
        saved = deps.services().personalization.update_settings(current_user.id, {
            "theme": payload.theme, "custom_instructions": payload.custom_instructions.strip(),
            "auto_learn": payload.auto_learn, "default_provider": payload.default_provider,
            "default_model": payload.default_model,
        })
        return {"displayName": updated.display_name, "email": updated.email, "avatarUrl": updated.avatar_url, **saved}

    @router.delete("/api/settings/learned-preferences", status_code=204, responses=deps.error_responses)
    def clear_learned(request: Request) -> None:
        deps.services().personalization.clear_learned(user(request).id)

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
