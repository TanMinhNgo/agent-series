"""Application composition and compatibility handlers during the API split."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
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
from api.modules.projects.service import delete_project as _delete_project_service
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, select

from agent_core.ai.agent import Agent, AgentCancelled
from agent_core.content.artifacts import PREVIEW_LIMIT, ArtifactEditContext, ArtifactService, build_artifact_tool
from agent_core.runtime.config import Settings, load_settings
from agent_core.runtime.credentials import CredentialError, UserCredentialService
from agent_core.knowledge.rag import NO_DOCUMENTS_RESULT, KnowledgeService, build_knowledge_tool
from agent_core.content.media import MediaService
from agent_core.content.file_storage import FileStorageService
from agent_core.content.library import LibraryService
from agent_core.knowledge.memory import MemoryService
from agent_core.ai.ollama import OllamaCatalog, OllamaError
from agent_core.knowledge.personalization import PersonalizationService
from agent_core.integrations.google_workspace import GOOGLE_WORKSPACE_SLUG, GoogleConnectorError, GoogleWorkspaceExecutor, GoogleWorkspaceService
from agent_core.integrations.github_app import GITHUB_SLUG, GitHubAppExecutor, GitHubAppService, GitHubConnectorError
from agent_core.integrations.plugin_catalog import CATALOG, catalog_json, find_catalog_plugin
from agent_core.integrations.plugin_execution import EXECUTORS
from agent_core.ai.prompts import DEFAULT_SYSTEM_PROMPT, OLLAMA_SYSTEM_PROMPT
from agent_core.ai.providers import build_client
from agent_core.ai.images import ImageGenerationError
from agent_core.persistence.store import ArtifactChunk, AuthRepository, BackgroundJob, BackgroundJobRepository, Chat, ChatMessage, ChatRepository, ChatShare, ConnectorRepository, Database, Document, KnowledgeCollection, LibraryAsset, MediaAttachment, MediaRepository, ModelRegistryRepository, Plugin, Project, PromptTemplate, Schedule, ScheduleRepository, ScheduleRun, User, Workspace, WorkspaceInvitation, WorkspaceMember, WorkspaceRepository, current_user_id, current_workspace_id
from agent_core.runtime.auth import AuthError, AuthService, SESSION_COOKIE
from agent_core.runtime.services import Services, build_services
from agent_core.tools import ToolRegistry, ToolSpec, build_default_registry
from agent_core.integrations.notifications import EmailNotificationService, public_chat_url, schedule_run_email
from agent_core.integrations.web_search import WebSearchService, build_web_search_tool, sources_from_web_steps

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
    AdminModelStatusRequest, AdminUserStatusRequest, ApiKeyRequest, BranchChatRequest,
    ChatRequest, CollectionDocumentsRequest, CreateChatRequest, DeleteProjectRequest,
    FeedbackRequest, KnowledgeCollectionRequest, PinMessageRequest, PluginRequest,
    ExternalActionProposalRequest, PluginUpdateRequest, ProjectConnectorScopeRequest, ProjectRequest, PromptTemplateRequest, ScheduleProposalPayload,
    ScheduleRequest, ScheduleUpdateRequest, ShareRequest, UpdateArtifactRequest,
    UpdateChatRequest, WorkspaceInvitationRequest, WorkspaceMemberRoleRequest, WorkspaceRequest,
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


def require_workspace_owner(request: Request) -> WorkspaceMember:
    membership = getattr(request.state, "workspace_membership", None)
    if membership is None or membership.role != "owner":
        raise HTTPException(status_code=403, detail="Chỉ owner workspace mới được thực hiện thao tác này.")  # NOSONAR - protected routes declare API_ERROR_RESPONSES
    return membership


def require_system_admin(request: Request):
    user = getattr(request.state, "user", None)
    if user is None or not services().auth.is_system_admin(user):
        raise HTTPException(status_code=403, detail="Chỉ system admin mới được truy cập.")  # NOSONAR - protected routes declare API_ERROR_RESPONSES
    return user


def create_workspace_invitation(payload: WorkspaceInvitationRequest, request: Request) -> dict[str, Any]:
    require_workspace_owner(request)
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Email lời mời không hợp lệ.")
    item = services().workspace.invite(current_workspace_id.get(), email, payload.role, request.state.user.id, datetime.now(UTC) + timedelta(days=7))
    record_workspace_activity("workspace.invitation_created", "workspace_invitation", item.id, f"Đã mời {email} vào workspace với quyền {payload.role}.")
    result = invitation_json(item)
    invite_url = f"{services().settings.app_web_url}/?invite={item.id}"
    if services().email.enabled:
        try:
            services().email.send(email, "Lời mời vào Agent Series workspace", f"Bạn được mời vào workspace Agent Series với quyền {payload.role}.\n\nĐăng nhập Google bằng đúng email này rồi mở lời mời:\n{invite_url}\n\nLời mời hết hạn sau 7 ngày.")
            result["emailStatus"] = "sent"
        except Exception:  # Invitation remains valid; owner can share the URL manually.
            result["emailStatus"] = "pending"
    else:
        result["emailStatus"] = "pending"
    result["inviteUrl"] = invite_url
    return result


def cancel_workspace_invitation(invitation_id: str, request: Request) -> None:
    require_workspace_owner(request)
    if not services().workspace.cancel_invitation(current_workspace_id.get(), invitation_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy lời mời.")
    record_workspace_activity("workspace.invitation_revoked", "workspace_invitation", invitation_id, "Đã thu hồi lời mời vào workspace.")


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


def list_chats(
    offset: int = Query(default=0, ge=0, description="Vị trí bắt đầu của trang lịch sử."),
    limit: int = Query(default=40, ge=1, le=100, description="Số chat tối đa mỗi lần tải."),
) -> dict[str, Any]:
    items, total = services().chats.list(offset=offset, limit=limit)
    next_offset = offset + len(items)
    return {
        "items": [chat_json(chat) for chat in items],
        "total": total,
        "nextOffset": next_offset if next_offset < total else None,
    }


def create_chat(payload: CreateChatRequest) -> dict[str, Any]:
    settings = services().settings
    available = available_provider_models(current_user_id.get())
    provider = payload.provider or (settings.provider if settings.provider in available else next(iter(available), settings.provider))
    model = payload.model or (settings.active_model if settings.active_model in available.get(provider, []) else (available.get(provider) or [settings.active_model])[0])
    try:
        selected = selected_settings(provider, model, current_user_id.get())
    except (ValueError, CredentialError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    source_id = payload.context_source_chat_id
    if source_id and services().chats.get(source_id) is None:
        raise HTTPException(status_code=422, detail="Không tìm thấy chat nguồn để kế thừa context.")
    if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
    if payload.collection_id:
        collection = services().knowledge.get_collection(payload.collection_id)
        if collection is None or collection.project_id != payload.project_id:
            raise HTTPException(status_code=422, detail="Collection phải thuộc Project đã chọn.")
    return chat_json(services().chats.create(selected.provider, selected.active_model, source_id, payload.project_id, payload.collection_id, payload.mode))


def update_library_asset(asset_id: str, payload: UpdateArtifactRequest) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    project_id = values.get("project_id")
    if project_id and services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
    try:
        item = services().library.update(
            asset_id,
            name=values.get("name"),
            project_id=project_id,
            is_project_source=values.get("is_project_source"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=ARTIFACT_NOT_FOUND_ERROR)
    enqueue_artifact_index(item)
    if getattr(item, "project_id", None):
        if "is_project_source" in values:
            event = "project_source.pinned" if item.is_project_source else "project_source.unpinned"
            summary = f"Đã {'ghim' if item.is_project_source else 'bỏ ghim'} file {item.name} làm nguồn Project."
        else:
            event, summary = "artifact.updated", f"Đã cập nhật file {item.name}."
        record_project_activity(item.project_id, event, "artifact", item.id, summary)
    return library_asset_json(item)


def restore_library_asset_version(asset_id: str) -> dict[str, Any]:
    """Restore a chosen version by copying it into a new latest version."""
    try:
        item = services().library.restore_version(asset_id)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(status_code=404 if NOT_FOUND_MARKER in message else 422, detail=message) from exc
    enqueue_artifact_index(item)
    if getattr(item, "project_id", None):
        record_project_activity(item.project_id, "artifact.restored", "artifact", item.id, f"Đã khôi phục {item.name} thành version {item.version}.")
    return library_asset_json(item)


def get_chat(chat_id: str) -> dict[str, Any]:
    chat = services().chats.get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
    return chat_json(chat)


def messages(chat_id: str) -> list[dict[str, Any]]:
    if services().chats.get(chat_id) is None:
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
    backfill_links = getattr(services().chats, "backfill_artifact_links", None)
    if backfill_links is not None:
        backfill_links(chat_id)
    history = [item for item in services().chats.history(chat_id) if item["role"] in {"user", "assistant"}]
    artifact_lookup = getattr(services().chats, "artifacts_by_assistant_message", None)
    artifacts_by_message = artifact_lookup(
        chat_id,
        [item["message_id"] for item in history if item["role"] == "assistant" and item.get("message_id")],
    ) if artifact_lookup is not None else {}
    feedback = services().personalization.feedback_by_message_ids(
        [item["message_id"] for item in history if item["role"] == "assistant" and item.get("message_id")]
    )
    trace_lookup = getattr(getattr(services(), "workspace", None), "retrieval_traces", None)
    traces_by_message = trace_lookup(
        [item["message_id"] for item in history if item["role"] == "assistant" and item.get("message_id")]
    ) if trace_lookup is not None else {}
    return [
        message_json({
            **item,
            "feedback_kind": feedback.get(item.get("message_id")),
            "artifacts": [library_asset_json(asset) for asset in artifacts_by_message.get(item.get("message_id", ""), [])],
            "retrievalTrace": [retrieval_trace_json(trace) for trace in traces_by_message.get(item.get("message_id", ""), [])],
        } if item["role"] == "assistant" else item)
        for item in history
    ]


def mark_chat_read(chat_id: str) -> dict[str, Any]:
    chat = services().chats.set_unread(chat_id, False)
    if chat is None:
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
    return chat_json(chat)


def pin_message(message_id: str, payload: PinMessageRequest) -> dict[str, Any]:
    message = services().chats.set_message_pin(message_id, payload.pinned)
    if message is None:
        raise HTTPException(status_code=404, detail="Chỉ có thể ghim message của bạn.")
    return {"messageId": message.id, "pinned": message.pinned}


def create_response_feedback(message_id: str, payload: FeedbackRequest) -> dict[str, Any]:
    try:
        item = services().personalization.record_feedback(message_id, payload.kind, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": item.id, "messageId": item.message_id, "kind": item.kind, "note": item.note}


def create_chat_branch(chat_id: str, payload: BranchChatRequest) -> dict[str, Any]:
    try:
        return chat_json(services().chats.create_branch(chat_id, payload.assistant_message_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def prepare_chat_regeneration(chat_id: str, payload: BranchChatRequest) -> dict[str, str]:
    try:
        return {"content": services().chats.prepare_regeneration(chat_id, payload.assistant_message_id)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def list_chat_pins(chat_id: str) -> list[dict[str, Any]]:
    if services().chats.get(chat_id) is None:
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
    return [{"messageId": message.id, "position": message.position, "content": message.content} for message in services().chats.chat_pins(chat_id)]


def list_templates(project_id: str | None = Query(default=None, alias="projectId")) -> list[dict[str, Any]]:
    with services().chats.database.session() as session:
        statement = select(PromptTemplate).order_by(PromptTemplate.updated_at.desc())
        if project_id:
            statement = statement.where(PromptTemplate.project_id.in_((None, project_id)))
        else:
            statement = statement.where(PromptTemplate.project_id.is_(None))
        return [template_json(item) for item in session.scalars(statement)]


def create_template(payload: PromptTemplateRequest) -> dict[str, Any]:
    if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
    return template_json(services().workspace.create(PromptTemplate, **payload.model_dump()))


def update_template(template_id: str, payload: PromptTemplateRequest) -> dict[str, Any]:
    if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
    item = services().workspace.update(PromptTemplate, template_id, **payload.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy template.")
    return template_json(item)


def delete_template(template_id: str) -> None:
    if not services().workspace.delete(PromptTemplate, template_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy template.")


def _record_chat_project_move(chat: Chat, previous_project_id: str | None) -> None:
    if previous_project_id == chat.project_id:
        return
    if previous_project_id:
        record_project_activity(previous_project_id, "chat.removed", "chat", chat.id, f"Đã chuyển chat {chat.title} ra khỏi Project.")
    if chat.project_id:
        record_project_activity(chat.project_id, "chat.added", "chat", chat.id, f"Đã thêm chat {chat.title} vào Project.")


def update_chat(chat_id: str, payload: UpdateChatRequest) -> dict[str, Any]:
    try:
        chat = services().chats.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
        provider, model = payload.provider or chat.provider, payload.model or chat.model
        previous_project_id = chat.project_id
        selected_settings(provider, model, current_user_id.get())
        if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
            raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
        values = {"provider": provider, "model": model}
        if "collection_id" in payload.model_fields_set and payload.collection_id:
            collection = services().knowledge.get_collection(payload.collection_id)
            target_project = payload.project_id if "project_id" in payload.model_fields_set else chat.project_id
            if collection is None or collection.project_id != target_project:
                raise HTTPException(status_code=422, detail="Collection phải thuộc Project của chat.")
        for field in ("title", "pinned", "archived", "project_id", "collection_id", "mode"):
            if field in payload.model_fields_set:
                values[field] = getattr(payload, field)
        if "project_id" in payload.model_fields_set and "collection_id" not in payload.model_fields_set:
            values["collection_id"] = None
        chat = services().chats.update(chat_id, **values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
    if "project_id" in payload.model_fields_set:
        _record_chat_project_move(chat, previous_project_id)
    return chat_json(chat)


def delete_chat(chat_id: str) -> None:
    if not services().chats.delete(chat_id):
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)


def share_chat(chat_id: str, payload: ShareRequest | None = None) -> dict[str, Any]:
    expires_at = payload.expires_at if payload else None
    if expires_at and expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Thời hạn chia sẻ phải ở tương lai.")
    share = services().chats.create_or_update_share(chat_id, expires_at)
    if share is None:
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
    chat = services().chats.get(chat_id)
    if chat and chat.project_id:
        record_project_activity(chat.project_id, "chat.shared", "chat", chat.id, f"Đã tạo hoặc cập nhật liên kết chia sẻ cho chat {chat.title}.")
    return share_json(share)


def revoke_share(chat_id: str) -> None:
    chat = services().chats.get(chat_id)
    if not services().chats.revoke_share(chat_id):
        raise HTTPException(status_code=404, detail="Chat chưa có liên kết chia sẻ.")
    if chat and chat.project_id:
        record_project_activity(chat.project_id, "chat.share_revoked", "chat", chat.id, f"Đã thu hồi liên kết chia sẻ của chat {chat.title}.")


def public_share(token: str) -> dict[str, Any]:
    share = services().chats.get_share(token)
    if share is None or (share.expires_at and share.expires_at <= datetime.now(UTC)):
        raise HTTPException(status_code=404, detail="Liên kết chia sẻ không tồn tại hoặc đã bị thu hồi.")
    return share_json(share)


def documents() -> list[dict[str, Any]]:
    jobs = BackgroundJobRepository(services().chats.database)
    return [document_json(item, jobs.latest_for_document(item.id)) for item in services().knowledge.list_documents()]


def list_collections(project_id: str) -> list[dict[str, Any]]:
    if services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy Project.")
    return [collection_json(item, services().knowledge.collection_documents(item.id)) for item in services().knowledge.list_collections(project_id)]


def create_collection(project_id: str, payload: KnowledgeCollectionRequest) -> dict[str, Any]:
    if services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy Project.")
    try:
        item = services().knowledge.create_collection(project_id, payload.name, payload.description)
        record_project_activity(project_id, "collection.created", "collection", item.id, f"Đã tạo collection {item.name}.")
        return collection_json(item, [])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def update_collection(collection_id: str, payload: KnowledgeCollectionRequest) -> dict[str, Any]:
    try:
        item = services().knowledge.update_collection(collection_id, payload.name, payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=COLLECTION_NOT_FOUND_ERROR)
    record_project_activity(item.project_id, "collection.updated", "collection", item.id, f"Đã cập nhật collection {item.name}.")
    return collection_json(item, services().knowledge.collection_documents(item.id))


def set_collection_documents(collection_id: str, payload: CollectionDocumentsRequest) -> dict[str, Any]:
    try:
        item = services().knowledge.get_collection(collection_id)
        if item is None:
            raise HTTPException(status_code=404, detail=COLLECTION_NOT_FOUND_ERROR)
        documents = services().knowledge.set_collection_documents(collection_id, payload.document_ids)
        record_project_activity(item.project_id, "collection.documents_updated", "collection", item.id, f"Đã cập nhật tài liệu cho collection {item.name}.")
        return collection_json(item, documents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def delete_collection(collection_id: str) -> None:
    item = services().knowledge.get_collection(collection_id)
    if item is None or not services().knowledge.delete_collection(collection_id):
        raise HTTPException(status_code=404, detail=COLLECTION_NOT_FOUND_ERROR)
    record_project_activity(item.project_id, "collection.deleted", "collection", collection_id, f"Đã xóa collection {item.name}.")


def document_file(document_id: str) -> Response:
    document = services().knowledge.ensure_remote(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND_ERROR)
    if document.storage_provider == "imagekit":
        return RedirectResponse(services().knowledge.storage.signed_url(document.storage_provider, document.stored_name, document.storage_file_id), status_code=307)
    path = Path(services().settings.knowledge_dir) / document.stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file tài liệu.")
    return FileResponse(path, media_type="application/pdf", filename=document.original_name, content_disposition_type="inline")


def worker_status() -> dict[str, Any]:
    return BackgroundJobRepository(services().chats.database).worker_status(datetime.now(UTC))


async def upload_documents(files: list[UploadFile] = File(...), project_id: str | None = Form(default=None)) -> list[dict[str, Any]]:
    if project_id and services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
    uploaded: list[Document] = []
    try:
        for file in files:
            document, created = services().knowledge.upload(file.filename or "document.pdf", await file.read(), project_id)
            if created or document.status != "ready":
                enqueue_document_index(document)
            uploaded.append(document)
            if project_id:
                record_project_activity(project_id, "document.uploaded", "document", document.id, f"Đã thêm tài liệu {document.original_name}.")
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    jobs = BackgroundJobRepository(services().chats.database)
    return [document_json(item, jobs.latest_for_document(item.id)) for item in uploaded]


def reindex_document(document_id: str) -> dict[str, Any]:
    document = next((item for item in services().knowledge.list_documents() if item.id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND_ERROR)
    job = enqueue_document_index(document)
    return document_json(document, job)


def delete_document(document_id: str) -> None:
    with services().chats.database.session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND_ERROR)
        project_id, document_name = document.project_id, document.original_name
        jobs = session.scalars(
            select(BackgroundJob).where(
                BackgroundJob.type == "document_index",
                BackgroundJob.dedupe_key == f"document:{document.id}",
                BackgroundJob.status.in_(("queued", "running")),
            )
        ).all()
        for job in jobs:
            job.status, job.locked_at, job.last_error = "cancelled", None, "Tài liệu đã bị xóa."
        queue_file_cleanup(session, [{"storage": "knowledge", "stored_name": document.stored_name, "storage_provider": document.storage_provider, "storage_file_id": document.storage_file_id}], f"document-cleanup:{document.id}")
        session.delete(document)
        session.commit()
    if project_id:
        record_project_activity(project_id, "document.deleted", "document", document_id, f"Đã xóa tài liệu {document_name}.")


def list_projects() -> list[dict[str, Any]]:
    return [project_json(item) for item in services().workspace.list(Project)]


def create_project(payload: ProjectRequest) -> dict[str, Any]:
    project = services().workspace.create(Project, **payload.model_dump())
    record_project_activity(project.id, "project.created", "project", project.id, f"Đã tạo Project {project.name}.")
    return project_json(project)


def get_project(project_id: str) -> dict[str, Any]:
    project = services().workspace.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_ERROR)
    with services().chats.database.session() as session:
        project_chats = list(session.scalars(select(Chat).where(Chat.project_id == project_id).order_by(Chat.updated_at.desc())))
        project_documents = list(session.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())))
        project_assets = list(session.scalars(select(LibraryAsset).where(LibraryAsset.project_id == project_id).order_by(LibraryAsset.created_at.desc())))
        project_schedules = list(session.scalars(select(Schedule).where(Schedule.project_id == project_id).order_by(Schedule.starts_at.desc())))
    jobs = BackgroundJobRepository(services().chats.database)
    scopes = services().workspace.connector_scopes(project_id)
    activity = services().workspace.project_activity(project_id)
    actor_ids = [item.actor_user_id for item in activity if item.actor_user_id]
    with services().chats.database.session() as session:
        actors = {item.id: item for item in session.scalars(select(User).where(User.id.in_(actor_ids))).all()} if actor_ids else {}
    return {"project": project_json(project), "chats": [chat_json(item) for item in project_chats[:8]], "documents": [document_json(item, jobs.latest_for_document(item.id)) for item in project_documents], "assets": [library_asset_json(item) for item in project_assets[:12]], "projectSources": [library_asset_json(item) for item in project_assets if item.is_project_source], "schedules": [schedule_json(item) for item in project_schedules[:8]], "activity": [project_activity_json(item, actors.get(item.actor_user_id)) for item in activity], "connectorScopes": [{"connectorSlug": item.connector_slug, "config": item.config} for item in scopes]}


def save_project_connector_scope(project_id: str, payload: ProjectConnectorScopeRequest) -> dict[str, Any]:
    if services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_ERROR)
    scope = services().workspace.save_connector_scope(project_id, payload.connector_slug, payload.config)
    record_project_activity(project_id, "connector.scope_updated", "connector", scope.id, f"Đã cập nhật nguồn {payload.connector_slug} cho Project.")
    return {"connectorSlug": scope.connector_slug, "config": scope.config}


def create_external_action_proposal(payload: ExternalActionProposalRequest) -> dict[str, Any]:
    asset = services().library.ensure_remote(payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=ARTIFACT_NOT_FOUND_ERROR)
    proposal = services().workspace.create_external_proposal(payload.action_type, {"assetId": asset.id, "name": asset.name, "folderId": payload.folder_id}, asset.project_id)
    record_project_activity(asset.project_id, "external_action.proposed", "artifact", asset.id, f"Đang chờ xác nhận upload {asset.name} lên Google Drive.")
    return {"proposalId": proposal.id, "status": proposal.status, "actionType": proposal.action_type, "assetId": asset.id, "name": asset.name, "folderId": payload.folder_id, "expiresAt": proposal.expires_at.isoformat()}


def confirm_external_action_proposal(proposal_id: str) -> dict[str, Any]:
    proposal = services().workspace.claim_external_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=409, detail="Đề xuất đã hết hạn hoặc đã được xử lý.")
    if proposal.action_type != "google_drive_upload":
        raise HTTPException(status_code=422, detail="Loại action chưa hỗ trợ.")
    asset_id = str(proposal.config.get("assetId") or "")
    asset = services().library.ensure_remote(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=ARTIFACT_NOT_FOUND_ERROR)
    try:
        data = services().library.storage.read(asset.storage_provider, asset.stored_name, asset.storage_file_id)
        result = services().google_workspace.upload_drive_file(asset.name, data, asset.mime_type, proposal.config.get("folderId"))
    except GoogleConnectorError as exc:
        services().workspace.finish_external_proposal(proposal.id, str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        services().workspace.finish_external_proposal(proposal.id, str(exc))
        raise HTTPException(status_code=502, detail="Không thể upload lên Google Drive.") from exc
    services().workspace.finish_external_proposal(proposal.id)
    record_project_activity(asset.project_id, "external_action.completed", "artifact", asset.id, f"Đã upload {asset.name} lên Google Drive sau xác nhận.")
    return {"proposalId": proposal.id, "status": "completed", "result": result}


def update_project(project_id: str, payload: ProjectRequest) -> dict[str, Any]:
    item = services().workspace.update(Project, project_id, **payload.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail=PROJECT_NOT_FOUND_ERROR)
    record_project_activity(project_id, "project.updated", "project", project_id, f"Đã cập nhật Project {item.name}.")
    return project_json(item)


def delete_project(project_id: str, payload: DeleteProjectRequest) -> dict[str, Any]:
    try:
        return _delete_project_service(services().chats.database, project_id, payload.confirm_name, queue_file_cleanup, PROJECT_NOT_FOUND_ERROR)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def list_schedules() -> list[dict[str, Any]]:
    return [schedule_json(item) for item in services().workspace.list(Schedule)]


def create_schedule(payload: ScheduleRequest) -> dict[str, Any]:
    if payload.ends_at and payload.ends_at < payload.starts_at:
        raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
    if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
    values = payload.model_dump()
    try:
        values["provider"], values["model"] = resolve_schedule_selection(payload.provider, payload.model, current_user_id.get())
    except (ValueError, CredentialError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    values["next_run_at"] = values["next_run_at"] or values["starts_at"]
    schedule = services().workspace.create(Schedule, **values)
    if schedule.project_id:
        record_project_activity(schedule.project_id, "schedule.created", "schedule", schedule.id, f"Đã tạo lịch {schedule.title}.")
    return schedule_json(schedule)


def _schedule_proposal_block(session, chat_id: str, proposal_id: str):
    messages = session.scalars(
        select(ChatMessage).where(ChatMessage.chat_id == chat_id, ChatMessage.role == "assistant").order_by(ChatMessage.position).with_for_update()
    ).all()
    for message in messages:
        blocks = deepcopy(message.content_blocks or [])
        for block in blocks:
            config = block.get("config") if isinstance(block, dict) else None
            if isinstance(config, dict) and block.get("type") == "schedule-proposal" and config.get("proposalId") == proposal_id:
                return message, blocks, config
    raise HTTPException(status_code=404, detail="Không tìm thấy đề xuất lịch trình.")


def _confirm_schedule_proposal(session, source_chat: Chat, message: ChatMessage, blocks: list[dict], config: dict, proposal_id: str) -> dict[str, Any]:
    status = config.get("status")
    if status == "confirmed":
        return {"status": "confirmed", "proposalId": proposal_id, "scheduleId": config.get("scheduleId")}
    if status != "pending":
        raise HTTPException(status_code=409, detail="Đề xuất này đã bị hủy.")
    try:
        proposal = ScheduleProposalPayload.model_validate(config)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Đề xuất lịch trình không hợp lệ.") from exc
    schedule = Schedule(title=proposal.title, prompt=proposal.prompt, starts_at=proposal.starts_at, recurrence=proposal.recurrence, timezone=proposal.timezone, project_id=config.get("projectId"), provider=source_chat.provider, model=source_chat.model, status="active", next_run_at=proposal.starts_at)
    session.add(schedule)
    session.flush()
    config.update(status="confirmed", scheduleId=schedule.id)
    message.content_blocks = blocks
    session.commit()
    return {"status": "confirmed", "proposalId": proposal_id, "scheduleId": schedule.id, "schedule": schedule_json(schedule)}


def mutate_schedule_proposal(chat_id: str, proposal_id: str, action: Literal["confirm", "dismiss"]) -> dict[str, Any]:
    """Confirm/dismiss exactly one content block, atomically with Schedule creation."""
    source_chat = services().chats.get(chat_id)
    if source_chat is None:
        raise HTTPException(status_code=404, detail=CHAT_NOT_FOUND_ERROR)
    with services().chats.database.session() as session:
        message, blocks, config = _schedule_proposal_block(session, chat_id, proposal_id)
        if action == "confirm":
            return _confirm_schedule_proposal(session, source_chat, message, blocks, config, proposal_id)
        if config.get("status") == "pending":
            config["status"] = "dismissed"
            message.content_blocks = blocks
            session.commit()
        return {"status": config.get("status"), "proposalId": proposal_id}


def confirm_chat_schedule_proposal(chat_id: str, proposal_id: str) -> dict[str, Any]:
    return mutate_schedule_proposal(chat_id, proposal_id, "confirm")


def dismiss_chat_schedule_proposal(chat_id: str, proposal_id: str) -> dict[str, Any]:
    return mutate_schedule_proposal(chat_id, proposal_id, "dismiss")


def _validate_schedule_update(current: Schedule, values: dict[str, Any]) -> None:
    starts_at = values.get("starts_at", current.starts_at)
    ends_at = values.get("ends_at", current.ends_at)
    if ends_at and ends_at < starts_at:
        raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
    project_id = values.get("project_id", current.project_id)
    if project_id and services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=422, detail=SELECTED_PROJECT_NOT_FOUND_ERROR)
    if values.get("status") == "active" and current.status == "completed" and current.recurrence == "once":
        raise HTTPException(status_code=422, detail="Lịch một lần đã hoàn tất; hãy tạo lịch mới để chạy lại.")


def _resolve_schedule_update_model(current: Schedule, values: dict[str, Any]) -> None:
    if not {"provider", "model"}.intersection(values):
        return
    provider = values.get("provider", current.provider)
    model = values.get("model")
    if "model" not in values:
        model = current.model if "provider" not in values else None
    try:
        values["provider"], values["model"] = resolve_schedule_selection(provider, model, current_user_id.get())
    except (ValueError, CredentialError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _reset_next_run_if_timing_changed(current: Schedule, values: dict[str, Any]) -> None:
    timing_changed = any(key in values and values[key] != getattr(current, key) for key in ("starts_at", "recurrence"))
    if timing_changed and "next_run_at" not in values:
        values["next_run_at"] = values.get("starts_at", current.starts_at)


def update_schedule(schedule_id: str, payload: ScheduleUpdateRequest) -> dict[str, Any]:
    current = services().workspace.get(Schedule, schedule_id)
    if current is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND_ERROR)
    values = payload.model_dump(exclude_unset=True)
    _validate_schedule_update(current, values)
    _resolve_schedule_update_model(current, values)
    _reset_next_run_if_timing_changed(current, values)
    item = services().workspace.update(Schedule, schedule_id, **values)
    if item and {"provider", "model"}.intersection(values) and item.chat_id:
        services().chats.update(item.chat_id, provider=item.provider, model=item.model)
    if item and item.project_id:
        record_project_activity(item.project_id, "schedule.updated", "schedule", item.id, f"Đã cập nhật lịch {item.title}.")
    return schedule_json(item)


def delete_schedule(schedule_id: str) -> None:
    current = services().workspace.get(Schedule, schedule_id)
    if current is None or not services().workspace.delete(Schedule, schedule_id):
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND_ERROR)
    if current.project_id:
        record_project_activity(current.project_id, "schedule.deleted", "schedule", schedule_id, f"Đã xóa lịch {current.title}.")


def list_schedule_runs(schedule_id: str, limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    if services().workspace.get(Schedule, schedule_id) is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND_ERROR)
    return [schedule_run_json(item) for item in ScheduleRepository(services().chats.database).list_runs(schedule_id, limit)]


def resend_schedule_run_email(schedule_id: str, run_id: str) -> dict[str, Any]:
    """Retry only the notification of a finished run, never the AI work itself."""
    schedule = services().workspace.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND_ERROR)
    runs = ScheduleRepository(services().chats.database)
    run = runs.get_run(schedule_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần chạy.")
    if run.status != "succeeded":
        raise HTTPException(status_code=409, detail="Chỉ gửi lại email cho lần chạy đã hoàn tất.")
    if run.email_status == "sent":
        raise HTTPException(status_code=409, detail="Email của lần chạy này đã được gửi.")
    user = services().auth.repository.get_user(current_user_id.get())
    email = services().email
    if not email.enabled or user is None or not user.email:
        raise HTTPException(status_code=422, detail="Chưa cấu hình SMTP hoặc tài khoản không có email.")
    subject, body = schedule_run_email(
        schedule.title,
        run.finished_at or run.started_at,
        run.summary,
        public_chat_url(services().settings.app_web_url, schedule.chat_id) if schedule.chat_id else None,
    )
    try:
        email.send(user.email, subject, body)
    except Exception as exc:  # noqa: BLE001
        runs.record_email(run_id, status="failed", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return schedule_run_json(runs.record_email(run_id, status="sent"))


def run_schedule_now(schedule_id: str) -> dict[str, str]:
    schedule = services().workspace.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND_ERROR)
    from agent_core.jobs.scheduler import ScheduleWorker

    worker = ScheduleWorker(services())
    try:
        prepared = worker.start_manual(schedule_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if prepared is None:
        raise HTTPException(status_code=404, detail=SCHEDULE_NOT_FOUND_ERROR)
    scheduled, chat, run_id = prepared
    Thread(target=worker.execute, args=(scheduled, run_id, True), daemon=True).start()
    return {"status": "running", "chatId": chat.id, "runId": run_id}


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

