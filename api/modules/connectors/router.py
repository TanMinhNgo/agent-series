"""Connector status and audit endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Query


@dataclass(frozen=True)
class ConnectorDependencies:
    services: Callable[[], Any]
    connector_audit_json: Callable[[Any], dict[str, Any]]
    google_slug: str
    github_slug: str
    api_error_responses: dict


def build_router(deps: ConnectorDependencies) -> APIRouter:
    router = APIRouter(tags=["Connectors"])

    @router.get("/api/connectors/google", responses=deps.api_error_responses)
    def google_connector_status() -> dict[str, Any]:
        return deps.services().google_workspace.status()

    @router.get("/api/connectors/google/audit", responses=deps.api_error_responses)
    def google_connector_audit(limit: int = Query(default=12, ge=1, le=50)) -> list[dict[str, Any]]:
        return [deps.connector_audit_json(item) for item in deps.services().google_workspace.repository.list_audit(deps.google_slug, limit)]

    @router.get("/api/connectors/github", responses=deps.api_error_responses)
    def github_connector_status() -> dict[str, Any]:
        return deps.services().github.status()

    @router.get("/api/connectors/github/audit", responses=deps.api_error_responses)
    def github_connector_audit(limit: int = Query(default=12, ge=1, le=50)) -> list[dict[str, Any]]:
        return [deps.connector_audit_json(item) for item in deps.services().github.repository.list_audit(deps.github_slug, limit)]

    return router
