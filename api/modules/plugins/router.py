"""Plugin catalog and plugin CRUD endpoints."""

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from api.contracts.requests import PluginRequest, PluginUpdateRequest


@dataclass(frozen=True)
class PluginDependencies:
    services: Callable[[], Any]
    plugin_model: Any
    catalog: Any
    find_catalog_plugin: Callable[[str], Any]
    catalog_json: Callable[..., dict[str, Any]]
    plugin_json: Callable[[Any], dict[str, Any]]
    google_workspace_slug: str
    api_error_responses: dict


def build_router(deps: PluginDependencies) -> APIRouter:
    router = APIRouter()

    @router.get("/api/plugins", tags=["Plugins"], responses=deps.api_error_responses)
    def list_plugins() -> list[dict[str, Any]]:
        return [deps.plugin_json(item) for item in deps.services().workspace.list(deps.plugin_model)]

    @router.get("/api/plugin-catalog", tags=["Plugin catalog"], responses=deps.api_error_responses)
    def plugin_catalog() -> list[dict[str, Any]]:
        installed = deps.services().workspace.catalog_plugin_ids()
        return [deps.catalog_json(item, installed.get(item.slug)) for item in deps.catalog]

    @router.post("/api/plugin-catalog/{slug}/install", status_code=201, tags=["Plugin catalog"], responses=deps.api_error_responses)
    def install_catalog_plugin(slug: str) -> dict[str, Any]:
        item = deps.find_catalog_plugin(slug)
        if item is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy plugin trong catalog.")
        existing = deps.services().workspace.get_plugin_by_catalog_slug(slug)
        if existing is not None:
            return deps.plugin_json(existing)
        try:
            plugin = deps.services().workspace.create(deps.plugin_model, slug=item.slug, name=item.name, description=item.description, enabled=False, config={}, catalog_slug=item.slug, category=item.category, capabilities=list(item.capabilities), connection_status="not_connected")
        except IntegrityError:
            plugin = deps.services().workspace.get_plugin_by_catalog_slug(slug)
            if plugin is None:
                raise
        return deps.plugin_json(plugin)

    @router.post("/api/plugins", status_code=201, tags=["Plugins"], responses=deps.api_error_responses)
    def create_plugin(payload: PluginRequest) -> dict[str, Any]:
        try:
            return deps.plugin_json(deps.services().workspace.create(deps.plugin_model, **payload.model_dump()))
        except IntegrityError as exc:
            raise HTTPException(status_code=422, detail="Slug plugin đã tồn tại.") from exc

    @router.patch("/api/plugins/{plugin_id}", tags=["Plugins"], responses=deps.api_error_responses)
    def update_plugin(plugin_id: str, payload: PluginUpdateRequest) -> dict[str, Any]:
        current = deps.services().workspace.get(deps.plugin_model, plugin_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy plugin.")
        connected = deps.services().google_workspace.status()["status"] == "connected" if current.catalog_slug == deps.google_workspace_slug else current.connection_status == "connected"
        if payload.enabled and current.catalog_slug and not connected:
            raise HTTPException(status_code=422, detail="Plugin catalog chưa được kết nối nên chưa thể bật.")
        try:
            item = deps.services().workspace.update(deps.plugin_model, plugin_id, **payload.model_dump(exclude_unset=True))
        except IntegrityError as exc:
            raise HTTPException(status_code=422, detail="Slug plugin đã tồn tại.") from exc
        return deps.plugin_json(item)

    @router.delete("/api/plugins/{plugin_id}", status_code=204, tags=["Plugins"], responses=deps.api_error_responses)
    def delete_plugin(plugin_id: str) -> None:
        if not deps.services().workspace.delete(deps.plugin_model, plugin_id):
            raise HTTPException(status_code=404, detail="Không tìm thấy plugin.")

    return router
