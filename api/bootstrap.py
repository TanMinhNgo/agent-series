"""Application composition: builds the FastAPI app and wires the feature routers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from threading import Event, Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from api.http.auth_middleware import AuthMiddlewareDependencies, install as install_auth_middleware
from api.modules.common.serializers import (
    chat_json as _chat_json,
    collection_json as _collection_json,
    document_json as _document_json,
    library_asset_json as _library_asset_json,
    plugin_json as _plugin_json,
    project_activity_json as _project_activity_json,
    project_json as _project_json,
    retrieval_trace_json as _retrieval_trace_json,
    schedule_json as _schedule_json,
    schedule_run_json as _schedule_run_json,
    share_json as _share_json,
    template_json as _template_json,
)
from api.modules.chats.runtime.history import (
    created_artifact_ids as _created_artifact_ids,
    ollama_recent_history as _ollama_recent_history,
    persisted_history as _persisted_history,
    recent_chat_history as _recent_chat_history,
)
from api.modules.chats.runtime.context import (
    ChatGenerationContext as _ChatGenerationContext,
    ContextDependencies as _ContextDependencies,
    load_generation_context as _load_generation_context,
)
from api.modules.chats.runtime.persistence import (
    PersistenceDependencies as _PersistenceDependencies,
    persist_generation as _persist_generation,
    persist_static_response as _persist_static_response,
)
from api.modules.chats.runtime.generation import (
    is_ollama_tool_echo as _is_ollama_tool_echo,
    model_error_message as _model_error_message,
    small_talk_response as _small_talk_response,
    should_search_web as _should_search_web,
    web_context_from_result as _web_context_from_result,
)
from api.modules.chats.runtime.tools import project_connector_tools as _project_connector_tools
from api.modules.chats.runtime.stream import StreamDependencies, stream_chat as _stream_chat
from agent_core.runtime.agent import AgentDependencies, agent_system_prompt as _agent_system_prompt, build_agent as _make_agent, selected_settings as _selected_settings
from agent_core.content.indexing import enqueue_artifact_index as _enqueue_artifact_index, queue_pending_artifacts
from api.modules.chats.runtime.turn import run_agent_turn as _run_agent_turn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from sqlalchemy import select

from agent_core.ai.agent import Agent, AgentCancelled
from agent_core.content.artifacts import ArtifactEditContext, ArtifactService
from agent_core.runtime.config import Settings, load_settings
from agent_core.runtime.credentials import CredentialError, UserCredentialService
from agent_core.knowledge.rag import NO_DOCUMENTS_RESULT, KnowledgeService, build_knowledge_tool
from agent_core.knowledge.memory import MemoryService
from agent_core.ai.ollama import OllamaCatalog, OllamaError
from agent_core.integrations.google_workspace import GOOGLE_WORKSPACE_SLUG, GoogleConnectorError
from agent_core.integrations.github_app import GITHUB_SLUG, GitHubAppExecutor, GitHubAppService, GitHubConnectorError
from agent_core.integrations.plugin_catalog import CATALOG, catalog_json, find_catalog_plugin
from agent_core.integrations.plugin_execution import EXECUTORS
from agent_core.ai.providers import build_client
from agent_core.ai.images import ImageGenerationError
from agent_core.persistence.store import BackgroundJob, BackgroundJobRepository, Chat, ChatMessage, ChatRepository, Database, Document, LibraryAsset, MediaAttachment, Plugin, Project, PromptTemplate, Schedule, ScheduleRepository, User, Workspace, WorkspaceInvitation, WorkspaceMember, WorkspaceRepository, current_user_id, current_workspace_id
from agent_core.runtime.auth import SESSION_COOKIE
from agent_core.runtime.services import Services, build_services
from agent_core.tools import ToolRegistry, ToolSpec, build_default_registry
from agent_core.integrations.notifications import public_chat_url, schedule_run_email
from agent_core.integrations.web_search import WebSearchService, sources_from_web_steps

VIETNAM_TIMEZONE = "Asia/Ho_Chi_Minh"
NOT_FOUND_MARKER = "Không tìm thấy"
JSON_MEDIA_TYPE = "application/json"
AUTHENTICATION_REQUIRED_ERROR = "Cần đăng nhập."
SELECTED_PROJECT_NOT_FOUND_ERROR = "Dự án được chọn không tồn tại."
ARTIFACT_NOT_FOUND_ERROR = "Không tìm thấy artifact."
CHAT_NOT_FOUND_ERROR = "Không tìm thấy chat."
COLLECTION_NOT_FOUND_ERROR = "Không tìm thấy collection."
DOCUMENT_NOT_FOUND_ERROR = "Không tìm thấy tài liệu."
PROJECT_NOT_FOUND_ERROR = "Không tìm thấy dự án."
SCHEDULE_NOT_FOUND_ERROR = "Không tìm thấy lịch trình."
API_ERROR_SCHEMA_REFERENCE = "#/components/schemas/ApiError"
CHAT_DETAIL_PATH = "/api/chats/{chat_id}"
FORBIDDEN_ACTION_DESCRIPTION = "Không có quyền thực hiện thao tác này."
INVALID_STATE_DESCRIPTION = "Trạng thái hiện tại không cho phép thao tác."
API_ERROR_RESPONSES = {
    403: {"description": FORBIDDEN_ACTION_DESCRIPTION},
    404: {"description": "Không tìm thấy tài nguyên."},
    409: {"description": INVALID_STATE_DESCRIPTION},
    422: {"description": "Dữ liệu yêu cầu không hợp lệ."},
    502: {"description": "Dịch vụ phụ thuộc trả lỗi."},
    503: {"description": "Dịch vụ tạm thời không khả dụng."},
}

class ChatRunRegistry:
    """In-memory cancellation flags for active chat streams in this API process."""

    def __init__(self):
        self._lock = Lock()
        self._runs: dict[tuple[str, str], tuple[str, Event]] = {}

    def start(self, chat_id: str, run_id: str, user_id: str) -> Event:
        with self._lock:
            key = (chat_id, run_id)
            if key in self._runs:
                raise ValueError("Lượt tạo phản hồi này đang chạy.")
            # ponytail: a short in-process scan; use a persisted per-chat lease if API workers scale out.
            if any(active_chat_id == chat_id for active_chat_id, _ in self._runs):
                raise ValueError("Chat này đang tạo phản hồi. Hãy chờ lượt hiện tại hoàn tất.")
            event = Event()
            self._runs[key] = (user_id, event)
            return event

    def cancel(self, chat_id: str, run_id: str, user_id: str) -> bool:
        with self._lock:
            run = self._runs.get((chat_id, run_id))
            if run is None or run[0] != user_id:
                return False
            run[1].set()
            return True

    def finish(self, chat_id: str, run_id: str | None) -> None:
        if not run_id:
            return
        with self._lock:
            self._runs.pop((chat_id, run_id), None)


chat_runs = ChatRunRegistry()


from api.contracts.requests import (
    BranchChatRequest, ChatRequest, CollectionDocumentsRequest, FeedbackRequest,
    KnowledgeCollectionRequest, ProjectRequest, ScheduleProposalPayload, ScheduleRequest,
    ScheduleUpdateRequest, ShareRequest, UpdateArtifactRequest, UpdateChatRequest,
    WorkspaceInvitationRequest,
)
from api.modules.chats.image_service import run_image_turn

def media_json(media: MediaAttachment) -> dict[str, Any]:
    return {"id": media.id, "name": media.original_name, "mimeType": media.mime_type, "url": services().media.url_for(media), "sizeBytes": media.size_bytes}


def message_json(message: dict[str, Any]) -> dict[str, Any]:
    result = dict(message)
    if "message_id" in result:
        result["messageId"] = result.pop("message_id")
    if "content_blocks" in result:
        result["contentBlocks"] = result.pop("content_blocks") or []
    if "feedback_kind" in result:
        result["feedbackKind"] = result.pop("feedback_kind")
    if "created_at" in result:
        result["createdAt"] = result.pop("created_at")
    if "generated_asset_ids" in result:
        assets = [services().library.get(asset_id) for asset_id in result.pop("generated_asset_ids")]
        result["generatedAssets"] = [library_asset_json(asset) for asset in assets if asset is not None]
    return result


SOURCE_LINK_PATTERN = re.compile(r"\[([^\[\]\n]+)\]\((/api/documents/[^)#]+(?:#[^)]+)?)\)")


def _source_label_only(line: str) -> bool:
    label = line.strip().rstrip(":-–—").strip().casefold()
    parts = label.split()
    if parts in (["nguồn"], ["source"], ["sources"], ["tham", "khảo"]):
        return True
    return len(parts) == 2 and parts[0] == "nguồn" and parts[1].isdecimal()


def _tighten_punctuation(line: str) -> str:
    result: list[str] = []
    for character in line:
        if character in ",.;:!?":
            while result and result[-1].isspace():
                result.pop()
        result.append(character)
    return "".join(result)


def detach_response_sources(content: str, external_sources: list[dict[str, str]] | None = None) -> tuple[str, list[dict[str, str]]]:
    """Move document links out of the visible answer into the message source menu."""
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for name, url in SOURCE_LINK_PATTERN.findall(content):
        if url not in seen:
            sources.append({"name": name, "url": url, "kind": "library"})
            seen.add(url)
    for source in external_sources or []:
        url = source.get("url", "")
        if url.startswith("https://") and url not in seen:
            sources.append({"name": source.get("name", url), "url": url, "kind": "external"})
            seen.add(url)
    if not sources:
        return content, []
    # A citation may appear at the end of a useful sentence. Remove only the
    # link itself; dropping the complete line would silently discard answer text.
    lines = []
    for line in content.splitlines():
        cleaned_line = SOURCE_LINK_PATTERN.sub("", line).rstrip()
        cleaned_line = _tighten_punctuation(cleaned_line)
        if _source_label_only(cleaned_line):
            continue
        lines.append(cleaned_line)
    cleaned = "\n".join(lines).strip()
    return cleaned or "Đã sử dụng nguồn để trả lời.", sources


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


def sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


OLLAMA_RAG_MAX_DISTANCE = 0.45


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def services() -> Services:
    return app.state.services


install_auth_middleware(app, AuthMiddlewareDependencies(services, SESSION_COOKIE, current_user_id, current_workspace_id, JSON_MEDIA_TYPE))


def user_json(user) -> dict[str, Any]:
    role = "system_admin" if services().auth.is_system_admin(user) else user.role
    return {"id": user.id, "email": user.email, "displayName": user.display_name, "role": role, "isActive": user.is_active}


def workspace_json(item: Workspace, membership: WorkspaceMember) -> dict[str, Any]:
    return {"id": item.id, "name": item.name, "isPersonal": item.is_personal, "role": membership.role}


def invitation_json(item: WorkspaceInvitation) -> dict[str, Any]:
    return {"id": item.id, "email": item.email, "role": item.role, "expiresAt": item.expires_at.isoformat(), "createdAt": item.created_at.isoformat()}


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


def credential_json(item) -> dict[str, Any]:
    return {
        "provider": item.provider,
        "keyHint": item.key_hint,
        "validatedAt": item.validated_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
    }


def enqueue_document_index(document: Document) -> BackgroundJob:
    jobs = BackgroundJobRepository(services().chats.database)
    job, created = jobs.enqueue_unique(
        "document_index",
        {"document_id": document.id},
        dedupe_key=f"document:{document.id}",
    )
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
    if not files:
        return
    session.add(
        BackgroundJob(
            type="file_cleanup",
            payload={"files": files},
            dedupe_key=dedupe_key,
            max_attempts=10,
        )
    )


def connector_audit_json(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "eventType": item.event_type,
        "toolName": item.tool_name,
        "summary": item.summary,
        "createdAt": item.created_at.isoformat(),
    }


def set_plugin_connection(catalog_slug: str, status: str, enabled: bool | None = None) -> None:
    plugin = services().workspace.get_plugin_by_catalog_slug(catalog_slug)
    if plugin is None:
        return
    values: dict[str, Any] = {"connection_status": status}
    if enabled is not None:
        values["enabled"] = enabled
    services().workspace.update(Plugin, plugin.id, **values)


def run_agent_turn(app_services: Services, chat: Chat, chat_id: str, content: str, attachments: list[dict], artifact_edit: ArtifactEditContext | None, cancel_event: Event, full_history: list[dict[str, Any]], events: Queue, research_web: bool = False) -> None:
    return _run_agent_turn(
        load_generation_context,
        make_agent,
        project_connector_tools,
        persist_generation,
        AgentCancelled,
        app_services,
        chat,
        chat_id,
        content,
        attachments,
        artifact_edit,
        cancel_event,
        full_history,
        events,
        research_web,
    )


def stream_chat(chat_id: str, content: str, attachments: list[dict], artifact_edit: ArtifactEditContext | None = None, cancel_event: Event | None = None, run_id: str | None = None, research_web: bool = False) -> Iterator[str]:
    return _stream_chat(
        StreamDependencies(
            services=services,
            sse=sse,
            chat_runs=chat_runs,
            run_image_turn=run_image_turn,
            message_json=message_json,
            small_talk_response=small_talk_response,
            persist_static_response=persist_static_response,
            run_agent_turn=run_agent_turn,
            model_error_message=model_error_message,
            agent_cancelled=AgentCancelled,
            image_generation_error=ImageGenerationError,
            current_user_id=current_user_id,
            current_workspace_id=current_workspace_id,
        ),
        chat_id, content, attachments, artifact_edit, cancel_event, run_id, research_web,
    )


# Swagger uses these responses consistently, while the route implementations
# remain focused on their actual application behavior.
ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    401: {
        "description": "Cần đăng nhập để thực hiện thao tác này.",
        "content": {JSON_MEDIA_TYPE: {"schema": {"$ref": API_ERROR_SCHEMA_REFERENCE}, "example": {"detail": AUTHENTICATION_REQUIRED_ERROR}}},
    },
    403: {
        "description": FORBIDDEN_ACTION_DESCRIPTION,
        "content": {JSON_MEDIA_TYPE: {"schema": {"$ref": API_ERROR_SCHEMA_REFERENCE}, "example": {"detail": FORBIDDEN_ACTION_DESCRIPTION}}},
    },
    404: {
        "description": "Không tìm thấy tài nguyên được yêu cầu.",
        "content": {
            JSON_MEDIA_TYPE: {
                "schema": {"$ref": API_ERROR_SCHEMA_REFERENCE},
                "example": {"detail": "Không tìm thấy chat."},
            }
        },
    },
    422: {
        "description": "Dữ liệu gửi lên không hợp lệ hoặc không thỏa điều kiện nghiệp vụ.",
        "content": {
            JSON_MEDIA_TYPE: {
                "schema": {"$ref": API_ERROR_SCHEMA_REFERENCE},
                "example": {"detail": "Model không được hỗ trợ."},
            }
        },
    },
    409: {
        "description": INVALID_STATE_DESCRIPTION,
        "content": {JSON_MEDIA_TYPE: {"schema": {"$ref": API_ERROR_SCHEMA_REFERENCE}, "example": {"detail": INVALID_STATE_DESCRIPTION}}},
    },
    500: {
        "description": "Lỗi máy chủ không mong đợi. Kiểm tra log FastAPI để biết chi tiết.",
        "content": {
            JSON_MEDIA_TYPE: {
                "schema": {"$ref": API_ERROR_SCHEMA_REFERENCE},
                "example": {"detail": "Lỗi máy chủ nội bộ."},
            }
        },
    },
}

# Only list errors the endpoint can actually return as an HTTP response.
# The streaming endpoint reports missing chats/model failures as SSE `error`
# events after its HTTP 200 connection has started.
ROUTE_ERROR_STATUSES: dict[tuple[str, str], tuple[int, ...]] = {
    ("post", "/api/chats"): (422, 500),
    ("get", CHAT_DETAIL_PATH): (404, 500),
    ("get", "/api/chats/{chat_id}/messages"): (404, 500),
    ("patch", CHAT_DETAIL_PATH): (404, 422, 500),
    ("delete", CHAT_DETAIL_PATH): (404, 500),
    ("post", "/api/chats/{chat_id}/share"): (404, 500),
    ("get", "/api/public/shares/{token}"): (404, 500),
    ("post", "/api/chats/{chat_id}/stream"): (422, 500),
    ("delete", "/api/memories/{memory_id}"): (404, 500),
    ("post", "/api/documents"): (422, 500),
    ("post", "/api/media"): (422, 500),
    ("post", "/api/projects"): (422, 500),
    ("patch", "/api/projects/{project_id}"): (404, 422, 500),
    ("delete", "/api/projects/{project_id}"): (404, 500),
    ("post", "/api/schedules"): (422, 500),
    ("patch", "/api/schedules/{schedule_id}"): (404, 422, 500),
    ("delete", "/api/schedules/{schedule_id}"): (404, 500),
    ("post", "/api/plugins"): (422, 500),
    ("get", "/api/plugin-catalog"): (500,),
    ("post", "/api/plugin-catalog/{slug}/install"): (404, 500),
    ("patch", "/api/plugins/{plugin_id}"): (404, 422, 500),
    ("delete", "/api/plugins/{plugin_id}"): (404, 500),
}


# New routes are registered from focused modules. Existing route functions stay
# in this compatibility module until their service/controller boundary is real.
from api.modules.chats.controller import ChatStreamController
from api.modules.chats.router import build_router as build_chat_stream_router
from api.modules.system.router import build_router as build_system_router
from api.modules.auth.router import AuthRouteDependencies, build_router as build_auth_router
from api.modules.settings.router import SettingsRouteDependencies, build_router as build_settings_router
from api.modules.admin.router import AdminRouteDependencies, build_router as build_admin_router
from api.modules.media.router import MediaRouteDependencies, build_router as build_media_router
from api.modules.chats.memory_router import MemoryRouteDependencies, build_router as build_memory_router
from api.modules.projects.router import ProjectRouteDependencies, build_router as build_project_router
from api.modules.workflows.router import build_router as build_workflow_router
from api.modules.integrations.router import IntegrationRouteDependencies, build_router as build_integration_router
from api.modules.schedules.router import ScheduleRouteDependencies, build_router as build_schedule_router
from api.modules.chats.crud_router import ChatCrudDependencies, build_router as build_chat_crud_router
from api.modules.chats.messages_router import MessageRouteDependencies, build_router as build_message_router
from api.modules.chats.actions_router import ChatActionDependencies, build_router as build_chat_actions_router
from api.modules.chats.sharing_router import ChatSharingDependencies, build_router as build_chat_sharing_router
from api.modules.chats.detail_router import ChatDetailDependencies, build_router as build_chat_detail_router
from api.modules.knowledge_router import KnowledgeDependencies, build_router as build_knowledge_router
from api.modules.media.library_router import LibraryDependencies, build_router as build_library_router
from api.modules.schedules.management_router import ScheduleManagementDependencies, build_router as build_schedule_management_router
from api.modules.schedules.proposal_router import ScheduleProposalDependencies, build_router as build_schedule_proposal_router
from api.modules.workspaces.router import WorkspaceDependencies, build_router as build_workspace_router
from api.modules.plugins.router import PluginDependencies, build_router as build_plugin_router
from api.modules.connectors.router import ConnectorDependencies, build_router as build_connector_router
from api.modules.connectors.oauth_router import ConnectorOAuthDependencies, build_router as build_connector_oauth_router


@dataclass(frozen=True)
class SystemRouteDependencies:
    services: Any
    ollama_status: Any
    available_provider_models: Any
    session_cookie: str
    error_responses: dict
    background_job_repository: Any
    now: Any


# Shared serializers live in the common module; these aliases preserve legacy imports.
chat_json = _chat_json
collection_json = _collection_json
document_json = _document_json
library_asset_json = _library_asset_json
plugin_json = _plugin_json
project_activity_json = _project_activity_json
project_json = _project_json
retrieval_trace_json = _retrieval_trace_json
schedule_json = _schedule_json
schedule_run_json = _schedule_run_json
share_json = _share_json
template_json = _template_json
created_artifact_ids = _created_artifact_ids
ollama_recent_history = _ollama_recent_history
persisted_history = _persisted_history
recent_chat_history = _recent_chat_history
ChatGenerationContext = _ChatGenerationContext
_context_dependencies = _ContextDependencies(Project, NO_DOCUMENTS_RESULT, OLLAMA_RAG_MAX_DISTANCE, _should_search_web, _web_context_from_result)


def load_generation_context(app_services, chat, content, chat_id, history, events, research_web=False):
    return _load_generation_context(_context_dependencies, app_services, chat, content, chat_id, history, events, research_web)


_persistence_dependencies = _PersistenceDependencies(
    detach_response_sources,
    sources_from_web_steps,
    _is_ollama_tool_echo,
    persisted_history,
    created_artifact_ids,
    library_asset_json,
    message_json,
    lambda database: BackgroundJobRepository(database),
)


def persist_generation(app_services, chat, chat_id, full_history, agent, initial_history_length, result, schedule_proposals, web_sources, retrieval_traces, events):
    return _persist_generation(_persistence_dependencies, app_services, chat, chat_id, full_history, agent, initial_history_length, result, schedule_proposals, web_sources, retrieval_traces, events)


def persist_static_response(app_services, chat_id, full_history, content, response, events):
    return _persist_static_response(_persistence_dependencies, app_services, chat_id, full_history, content, response, events)


model_error_message = _model_error_message
small_talk_response = _small_talk_response
is_ollama_tool_echo = _is_ollama_tool_echo
should_search_web = _should_search_web
web_context_from_result = _web_context_from_result
project_connector_tools = _project_connector_tools
agent_system_prompt = _agent_system_prompt
def make_agent(app_services, chat, memory_context="", knowledge_context="", personalization_context="", plugin_tools=None, history=None, schedule_proposals=None, allow_schedule_proposals=True, artifact_edit=None, web_context="", allow_web=True):
    try:
        return _make_agent(
            AgentDependencies(lambda provider, model, user_id: _selected_settings(app_services, provider, model, user_id), enqueue_artifact_index, library_asset_json, recent_chat_history, ollama_recent_history, ScheduleProposalPayload, VIETNAM_TIMEZONE, build_client, build_knowledge_tool, build_default_registry),
            app_services,
            chat,
            memory_context,
            knowledge_context,
            personalization_context,
            plugin_tools,
            history,
            schedule_proposals,
            allow_schedule_proposals,
            artifact_edit,
            web_context,
            allow_web,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


app.include_router(
    build_chat_stream_router(
        ChatStreamController(services, stream_chat, chat_runs, CHAT_NOT_FOUND_ERROR, NOT_FOUND_MARKER),
        API_ERROR_RESPONSES,
    )
)
app.include_router(build_system_router(SystemRouteDependencies(services, ollama_status, lambda *args: available_provider_models(*args), SESSION_COOKIE, API_ERROR_RESPONSES, BackgroundJobRepository, lambda: datetime.now(UTC))))
app.include_router(build_auth_router(AuthRouteDependencies(services, user_json, SESSION_COOKIE, API_ERROR_RESPONSES)))
app.include_router(build_settings_router(SettingsRouteDependencies(services, credential_json, AUTHENTICATION_REQUIRED_ERROR, API_ERROR_RESPONSES)))
app.include_router(build_admin_router(AdminRouteDependencies(services, require_system_admin, user_json, API_ERROR_RESPONSES)))
app.include_router(build_media_router(MediaRouteDependencies(services, media_json, API_ERROR_RESPONSES)))
app.include_router(build_memory_router(MemoryRouteDependencies(services, API_ERROR_RESPONSES)))
app.include_router(build_project_router(ProjectRouteDependencies(services, project_json, chat_json, document_json, library_asset_json, schedule_json, project_activity_json, record_project_activity, PROJECT_NOT_FOUND_ERROR, API_ERROR_RESPONSES, queue_file_cleanup)))
app.include_router(build_workflow_router(API_ERROR_RESPONSES, services))
app.include_router(build_integration_router(IntegrationRouteDependencies(services, record_project_activity, ARTIFACT_NOT_FOUND_ERROR, API_ERROR_RESPONSES)))
app.include_router(build_schedule_router(ScheduleRouteDependencies(services, schedule_json, resolve_schedule_selection, current_user_id, record_project_activity, SELECTED_PROJECT_NOT_FOUND_ERROR, API_ERROR_RESPONSES)))
app.include_router(build_chat_crud_router(ChatCrudDependencies(services, chat_json, lambda *args: available_provider_models(*args), selected_settings, current_user_id, SELECTED_PROJECT_NOT_FOUND_ERROR, API_ERROR_RESPONSES)))
app.include_router(build_message_router(MessageRouteDependencies(services, chat_json, message_json, library_asset_json, retrieval_trace_json, CHAT_NOT_FOUND_ERROR, API_ERROR_RESPONSES)))
app.include_router(build_chat_actions_router(ChatActionDependencies(services, chat_json, CHAT_NOT_FOUND_ERROR, API_ERROR_RESPONSES)))
app.include_router(build_chat_sharing_router(ChatSharingDependencies(
    services,
    PromptTemplate,
    Project,
    template_json,
    share_json,
    SELECTED_PROJECT_NOT_FOUND_ERROR,
    CHAT_NOT_FOUND_ERROR,
    API_ERROR_RESPONSES,
    record_project_activity,
)))
app.include_router(build_chat_detail_router(ChatDetailDependencies(
    services,
    chat_json,
    selected_settings,
    current_user_id.get,
    record_project_activity,
    CHAT_NOT_FOUND_ERROR,
    SELECTED_PROJECT_NOT_FOUND_ERROR,
    API_ERROR_RESPONSES,
    CHAT_DETAIL_PATH,
    Project,
)))
app.include_router(build_knowledge_router(KnowledgeDependencies(
    services,
    BackgroundJobRepository,
    Project,
    document_json,
    collection_json,
    record_project_activity,
    COLLECTION_NOT_FOUND_ERROR,
    DOCUMENT_NOT_FOUND_ERROR,
    API_ERROR_RESPONSES,
    Document,
    BackgroundJob,
    enqueue_document_index,
    queue_file_cleanup,
)))
app.include_router(build_library_router(LibraryDependencies(
    services,
    Project,
    LibraryAsset,
    library_asset_json,
    enqueue_artifact_index,
    queue_file_cleanup,
    record_project_activity,
    SELECTED_PROJECT_NOT_FOUND_ERROR,
    ARTIFACT_NOT_FOUND_ERROR,
    NOT_FOUND_MARKER,
    API_ERROR_RESPONSES,
)))
def _schedule_worker(services_instance: Any) -> Any:
    from agent_core.jobs.scheduler import ScheduleWorker
    return ScheduleWorker(services_instance)

app.include_router(build_schedule_management_router(ScheduleManagementDependencies(
    services,
    Schedule,
    Project,
    ScheduleRepository,
    schedule_json,
    schedule_run_json,
    resolve_schedule_selection,
    current_user_id.get,
    record_project_activity,
    schedule_run_email,
    public_chat_url,
    _schedule_worker,
    SCHEDULE_NOT_FOUND_ERROR,
    SELECTED_PROJECT_NOT_FOUND_ERROR,
    API_ERROR_RESPONSES,
)))
app.include_router(build_schedule_proposal_router(ScheduleProposalDependencies(
    services,
    Chat,
    ChatMessage,
    Schedule,
    ScheduleProposalPayload,
    schedule_json,
    CHAT_NOT_FOUND_ERROR,
    API_ERROR_RESPONSES,
)))
app.include_router(build_workspace_router(WorkspaceDependencies(
    services,
    current_workspace_id.get,
    workspace_json,
    invitation_json,
    record_workspace_activity,
    API_ERROR_RESPONSES,
    WorkspaceMember,
    WorkspaceInvitation,
    User,
)))
app.include_router(build_plugin_router(PluginDependencies(
    services,
    Plugin,
    CATALOG,
    find_catalog_plugin,
    catalog_json,
    plugin_json,
    GOOGLE_WORKSPACE_SLUG,
    API_ERROR_RESPONSES,
)))
app.include_router(build_connector_router(ConnectorDependencies(
    services,
    connector_audit_json,
    GOOGLE_WORKSPACE_SLUG,
    GITHUB_SLUG,
    API_ERROR_RESPONSES,
)))
app.include_router(build_connector_oauth_router(ConnectorOAuthDependencies(
    services,
    set_plugin_connection,
    GOOGLE_WORKSPACE_SLUG,
    GITHUB_SLUG,
    GoogleConnectorError,
    GitHubConnectorError,
    API_ERROR_RESPONSES,
)))


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema["tags"] = app.openapi_tags
    schema.setdefault("components", {}).setdefault("schemas", {})["ApiError"] = {
        "type": "object",
        "required": ["detail"],
        "properties": {"detail": {"type": "string", "description": "Thông báo lỗi cho client."}},
    }
    for (method, path), statuses in ROUTE_ERROR_STATUSES.items():
        operation = schema["paths"][path][method]
        operation.setdefault("responses", {}).update({str(status): ERROR_RESPONSES[status] for status in statuses})

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

