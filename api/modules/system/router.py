"""Public system endpoints."""

from typing import Any

from fastapi import APIRouter, Request


def build_router(deps) -> APIRouter:
    router = APIRouter(tags=["System"])

    @router.get("/api/health", responses=deps.error_responses)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/config", responses=deps.error_responses)
    def config(request: Request) -> dict[str, Any]:
        settings = deps.services().settings
        user = deps.services().auth.session_user(request.cookies.get(deps.session_cookie))
        local_status = deps.ollama_status()
        providers = deps.available_provider_models(user.id if user else None, tuple(local_status["models"]))
        default_provider = settings.provider if settings.active_model in providers.get(settings.provider, []) else next(iter(providers), settings.provider)
        default_model = settings.active_model if settings.active_model in providers.get(default_provider, []) else (providers.get(default_provider) or [settings.active_model])[0]
        return {"providers": providers, "defaultProvider": default_provider, "defaultModel": default_model, "providerStatus": {"ollama": local_status}}

    @router.get("/api/worker/status", responses=deps.error_responses)
    def worker_status() -> dict[str, Any]:
        return deps.background_job_repository(deps.services().chats.database).worker_status(deps.now())

    return router
