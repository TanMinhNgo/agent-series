"""Application composition: builds the FastAPI app and wires the feature routers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from agent_core.ai.ollama import OllamaError
from agent_core.content.indexing import enqueue_artifact_index as _enqueue_artifact_index, queue_pending_artifacts
from agent_core.integrations.github_app import GITHUB_SLUG, GitHubConnectorError
from agent_core.integrations.google_workspace import GOOGLE_WORKSPACE_SLUG, GoogleConnectorError
from agent_core.integrations.notifications import public_chat_url, schedule_run_email
from agent_core.integrations.plugin_catalog import CATALOG, catalog_json, find_catalog_plugin
from agent_core.persistence.store import (
    BackgroundJob, BackgroundJobRepository, Chat, ChatMessage, Document, LibraryAsset, MediaAttachment, Plugin, Project,
    PromptTemplate, Schedule, ScheduleRepository, User, WorkspaceInvitation, WorkspaceMember, current_user_id, current_workspace_id,
)
from agent_core.runtime.agent import selected_settings as _selected_settings
from agent_core.runtime.auth import SESSION_COOKIE
from agent_core.runtime.config import Settings
from agent_core.runtime.services import Services, build_services
from api.contracts.requests import ScheduleProposalPayload
from api.http import openapi
from api.http.auth_middleware import AuthMiddlewareDependencies, install as install_auth_middleware
from api.http.openapi import API_ERROR_RESPONSES, AUTHENTICATION_REQUIRED_ERROR, CHAT_DETAIL_PATH, JSON_MEDIA_TYPE
from api.modules.admin.router import AdminRouteDependencies, build_router as build_admin_router
from api.modules.auth.router import AuthRouteDependencies, build_router as build_auth_router
from api.modules.chats.actions_router import ChatActionDependencies, build_router as build_chat_actions_router
from api.modules.chats.crud_router import ChatCrudDependencies, build_router as build_chat_crud_router
from api.modules.chats.detail_router import ChatDetailDependencies, build_router as build_chat_detail_router
from api.modules.chats.memory_router import MemoryRouteDependencies, build_router as build_memory_router
from api.modules.chats.messages_router import MessageRouteDependencies, build_router as build_message_router
from api.modules.chats.module import ChatModule
from api.modules.chats.router import build_router as build_chat_stream_router
from api.modules.chats.sharing_router import ChatSharingDependencies, build_router as build_chat_sharing_router
from api.modules.common.serializers import (
    chat_json, collection_json, connector_audit_json, credential_json, document_json, invitation_json, library_asset_json,
    plugin_json, project_activity_json, project_json, retrieval_trace_json, schedule_json, schedule_run_json, share_json,
    template_json, workspace_json,
)
from api.modules.connectors.oauth_router import ConnectorOAuthDependencies, build_router as build_connector_oauth_router
from api.modules.connectors.router import ConnectorDependencies, build_router as build_connector_router
from api.modules.integrations.router import IntegrationRouteDependencies, build_router as build_integration_router
from api.modules.knowledge.router import KnowledgeDependencies, build_router as build_knowledge_router
from api.modules.media.library_router import LibraryDependencies, build_router as build_library_router
from api.modules.media.router import MediaRouteDependencies, build_router as build_media_router
from api.modules.plugins.router import PluginDependencies, build_router as build_plugin_router
from api.modules.projects.router import ProjectRouteDependencies, build_router as build_project_router
from api.modules.schedules.management_router import ScheduleManagementDependencies, build_router as build_schedule_management_router
from api.modules.schedules.proposal_router import ScheduleProposalDependencies, build_router as build_schedule_proposal_router
from api.modules.schedules.router import ScheduleRouteDependencies, build_router as build_schedule_router
from api.modules.settings.router import SettingsRouteDependencies, build_router as build_settings_router
from api.modules.system.router import SystemRouteDependencies, build_router as build_system_router
from api.modules.workflows.router import build_router as build_workflow_router
from api.modules.workspaces.router import WorkspaceDependencies, build_router as build_workspace_router

NOT_FOUND_MARKER = "Không tìm thấy"
SELECTED_PROJECT_NOT_FOUND_ERROR = "Dự án được chọn không tồn tại."
ARTIFACT_NOT_FOUND_ERROR = "Không tìm thấy artifact."
CHAT_NOT_FOUND_ERROR = "Không tìm thấy chat."
COLLECTION_NOT_FOUND_ERROR = "Không tìm thấy collection."
DOCUMENT_NOT_FOUND_ERROR = "Không tìm thấy tài liệu."
PROJECT_NOT_FOUND_ERROR = "Không tìm thấy dự án."
SCHEDULE_NOT_FOUND_ERROR = "Không tìm thấy lịch trình."


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.services = build_services()
    queue_pending_artifacts(app.state.services)
    yield


app = FastAPI(
    title="Agent Series API",
    version="1.0.0",
    description="API cho AI chat, RAG PDF, thư viện memory và workspace local.",
    openapi_tags=[
        {"name": "System", "description": "Kiểm tra trạng thái và đọc cấu hình client an toàn."},
        {"name": "Chats", "description": "Tạo, quản lý và lấy lịch sử hội thoại."},
        {"name": "Chat streaming", "description": "Gửi tin nhắn đến agent qua Server-Sent Events (SSE)."},
        {"name": "Memory library", "description": "Kho memory dài hạn cục bộ của người dùng hiện tại."},
        {"name": "Personal library", "description": "Kho file cá nhân upload hoặc do AI tạo."},
        {"name": "Shared chats", "description": "Tạo và đọc snapshot chat được chia sẻ bằng token."},
        {"name": "Knowledge base", "description": "Upload và quản lý PDF dùng cho RAG."},
        {"name": "Media", "description": "Upload ảnh và tệp đính kèm để dùng trong tin nhắn."},
        {"name": "Projects", "description": "Quản lý dự án trong workspace."},
        {"name": "Schedules", "description": "Quản lý lịch trình trong workspace."},
        {"name": "Plugins", "description": "Quản lý plugin tích hợp trong workspace."},
        {"name": "Plugin catalog", "description": "Khám phá và cài catalog plugin mẫu cho workspace local."},
        {"name": "Connectors", "description": "Kết nối OAuth và audit cho các tích hợp chỉ đọc."},
    ],
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
openapi.install(app)


def services() -> Services:
    return app.state.services


install_auth_middleware(app, AuthMiddlewareDependencies(services, SESSION_COOKIE, current_user_id, current_workspace_id, JSON_MEDIA_TYPE))
chat_module = ChatModule(services, CHAT_NOT_FOUND_ERROR, NOT_FOUND_MARKER)


def media_json(media: MediaAttachment) -> dict[str, Any]:
    return {"id": media.id, "name": media.original_name, "mimeType": media.mime_type, "url": services().media.url_for(media), "sizeBytes": media.size_bytes}


def user_json(user) -> dict[str, Any]:
    role = "system_admin" if services().auth.is_system_admin(user) else user.role
    return {"id": user.id, "email": user.email, "displayName": user.display_name, "role": role, "isActive": user.is_active}


def record_project_activity(project_id: str | None, event_type: str, subject_type: str, subject_id: str | None, summary: str) -> None:
    """Keep endpoint behavior compatible with lightweight service doubles in tests."""
    writer = getattr(getattr(services(), "workspace", None), "add_project_activity", None)
    if project_id and writer is not None:
        writer(project_id, event_type, subject_type, subject_id, summary)


def record_workspace_activity(event_type: str, subject_type: str, subject_id: str | None, summary: str) -> None:
    """Workspace-wide events are shown in every Project activity feed."""
    writer = getattr(getattr(services(), "workspace", None), "add_project_activity", None)
    if writer is not None:
        writer(None, event_type, subject_type, subject_id, summary)


def require_system_admin(request: Request):
    user = getattr(request.state, "user", None)
    if user is None or not services().auth.is_system_admin(user):
        raise HTTPException(status_code=403, detail="Chỉ system admin mới được truy cập.")  # NOSONAR - protected routes declare API_ERROR_RESPONSES
    return user


def selected_settings(provider: str, model: str, user_id: str | None) -> Settings:
    return _selected_settings(services(), provider, model, user_id)


def available_provider_models(user_id: str | None, ollama_models: tuple[str, ...] | None = None) -> dict[str, list[str]]:
    app_services = services()
    configured = app_services.settings.configured_provider_models()
    personal_providers = {item.provider for item in app_services.credentials.list_metadata(user_id)} if user_id else set()
    active = app_services.model_registry.active()
    providers = {
        provider: [model for model in models if model in active.get(provider, ())]
        for provider, models in app_services.settings.provider_models.items()
        if (provider in configured or provider in personal_providers) and any(model in active.get(provider, ()) for model in models)
    }
    if ollama_models is None:
        try:
            models = app_services.ollama.models()
        except OllamaError:
            models = ()
    else:
        models = ollama_models
    if models:
        providers["ollama"] = list(models)
    return providers


def resolve_schedule_selection(provider: str | None, model: str | None, user_id: str | None) -> tuple[str, str]:
    settings = services().settings
    available = available_provider_models(user_id)
    resolved_provider = provider or (
        settings.provider if settings.active_model in available.get(settings.provider, []) else next(iter(available), settings.provider)
    )
    resolved_model = model or (
        settings.active_model if settings.active_model in available.get(resolved_provider, []) else (available.get(resolved_provider) or [settings.active_model])[0]
    )
    selected = selected_settings(resolved_provider, resolved_model, user_id)
    return selected.provider, selected.active_model


def ollama_status() -> dict[str, Any]:
    try:
        return {"available": True, "message": None, "models": list(services().ollama.models())}
    except OllamaError as exc:
        return {"available": False, "message": str(exc), "models": []}


def enqueue_document_index(document: Document) -> BackgroundJob:
    jobs = BackgroundJobRepository(services().chats.database)
    job, created = jobs.enqueue_unique("document_index", {"document_id": document.id}, dedupe_key=f"document:{document.id}")
    if created:
        with services().chats.database.session() as session:
            stored = session.get(Document, document.id)
            if stored:
                stored.status, stored.error = "queued", None
                session.commit()
                document.status, document.error = stored.status, stored.error
    return job


def enqueue_artifact_index(asset: LibraryAsset, app_services: Services | None = None) -> BackgroundJob | None:
    return _enqueue_artifact_index(asset, app_services or services())


def queue_file_cleanup(session, files: list[dict[str, str]], dedupe_key: str) -> None:
    """Persist cleanup work with the destructive DB transaction, never before it."""
    if files:
        session.add(BackgroundJob(type="file_cleanup", payload={"files": files}, dedupe_key=dedupe_key, max_attempts=10))


def set_plugin_connection(catalog_slug: str, status: str, enabled: bool | None = None) -> None:
    plugin = services().workspace.get_plugin_by_catalog_slug(catalog_slug)
    if plugin is None:
        return
    values: dict[str, Any] = {"connection_status": status}
    if enabled is not None:
        values["enabled"] = enabled
    services().workspace.update(Plugin, plugin.id, **values)


def _schedule_worker(services_instance: Any) -> Any:
    from agent_core.jobs.scheduler import ScheduleWorker
    return ScheduleWorker(services_instance)


# Late-bound lambdas keep module-level helpers patchable in tests.
provider_models = lambda *args: available_provider_models(*args)  # noqa: E731
errors = API_ERROR_RESPONSES
for router in (
    build_chat_stream_router(chat_module.controller, errors),
    build_system_router(SystemRouteDependencies(services, ollama_status, provider_models, SESSION_COOKIE, errors, BackgroundJobRepository, lambda: datetime.now(UTC))),
    build_auth_router(AuthRouteDependencies(services, user_json, SESSION_COOKIE, errors)),
    build_settings_router(SettingsRouteDependencies(services, credential_json, AUTHENTICATION_REQUIRED_ERROR, errors)),
    build_admin_router(AdminRouteDependencies(services, require_system_admin, user_json, errors)),
    build_media_router(MediaRouteDependencies(services, media_json, errors)),
    build_memory_router(MemoryRouteDependencies(services, errors)),
    build_project_router(ProjectRouteDependencies(services, project_json, chat_json, document_json, library_asset_json, schedule_json, project_activity_json, record_project_activity, PROJECT_NOT_FOUND_ERROR, errors, queue_file_cleanup)),
    build_workflow_router(errors, services),
    build_integration_router(IntegrationRouteDependencies(services, record_project_activity, ARTIFACT_NOT_FOUND_ERROR, errors)),
    build_schedule_router(ScheduleRouteDependencies(services, schedule_json, resolve_schedule_selection, current_user_id, record_project_activity, SELECTED_PROJECT_NOT_FOUND_ERROR, errors)),
    build_chat_crud_router(ChatCrudDependencies(services, chat_json, provider_models, selected_settings, current_user_id, SELECTED_PROJECT_NOT_FOUND_ERROR, errors)),
    build_message_router(MessageRouteDependencies(services, chat_json, chat_module.message_json, library_asset_json, retrieval_trace_json, CHAT_NOT_FOUND_ERROR, errors)),
    build_chat_actions_router(ChatActionDependencies(services, chat_json, CHAT_NOT_FOUND_ERROR, errors)),
    build_chat_sharing_router(ChatSharingDependencies(services, PromptTemplate, Project, template_json, share_json, SELECTED_PROJECT_NOT_FOUND_ERROR, CHAT_NOT_FOUND_ERROR, errors, record_project_activity)),
    build_chat_detail_router(ChatDetailDependencies(services, chat_json, selected_settings, current_user_id.get, record_project_activity, CHAT_NOT_FOUND_ERROR, SELECTED_PROJECT_NOT_FOUND_ERROR, errors, CHAT_DETAIL_PATH, Project)),
    build_knowledge_router(KnowledgeDependencies(services, BackgroundJobRepository, Project, document_json, collection_json, record_project_activity, COLLECTION_NOT_FOUND_ERROR, DOCUMENT_NOT_FOUND_ERROR, errors, Document, BackgroundJob, enqueue_document_index, queue_file_cleanup)),
    build_library_router(LibraryDependencies(services, Project, LibraryAsset, library_asset_json, enqueue_artifact_index, queue_file_cleanup, record_project_activity, SELECTED_PROJECT_NOT_FOUND_ERROR, ARTIFACT_NOT_FOUND_ERROR, NOT_FOUND_MARKER, errors)),
    build_schedule_management_router(ScheduleManagementDependencies(
        services, Schedule, Project, ScheduleRepository, schedule_json, schedule_run_json, resolve_schedule_selection, current_user_id.get,
        record_project_activity, schedule_run_email, public_chat_url, _schedule_worker, SCHEDULE_NOT_FOUND_ERROR, SELECTED_PROJECT_NOT_FOUND_ERROR, errors,
    )),
    build_schedule_proposal_router(ScheduleProposalDependencies(services, Chat, ChatMessage, Schedule, ScheduleProposalPayload, schedule_json, CHAT_NOT_FOUND_ERROR, errors)),
    build_workspace_router(WorkspaceDependencies(services, current_workspace_id.get, workspace_json, invitation_json, record_workspace_activity, errors, WorkspaceMember, WorkspaceInvitation, User)),
    build_plugin_router(PluginDependencies(services, Plugin, CATALOG, find_catalog_plugin, catalog_json, plugin_json, GOOGLE_WORKSPACE_SLUG, errors)),
    build_connector_router(ConnectorDependencies(services, connector_audit_json, GOOGLE_WORKSPACE_SLUG, GITHUB_SLUG, errors)),
    build_connector_oauth_router(ConnectorOAuthDependencies(services, set_plugin_connection, GOOGLE_WORKSPACE_SLUG, GITHUB_SLUG, GoogleConnectorError, GitHubConnectorError, errors)),
):
    app.include_router(router)
