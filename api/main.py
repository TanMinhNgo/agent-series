"""Expose the existing agent services through JSON and server-sent events."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from agent_core.agent import Agent
from agent_core.artifacts import ArtifactService, build_artifact_tool
from agent_core.config import Settings, load_settings
from agent_core.credentials import CredentialError, UserCredentialService
from agent_core.knowledge import NO_DOCUMENTS_RESULT, KnowledgeService, build_knowledge_tool
from agent_core.media import MediaService
from agent_core.library import LibraryService
from agent_core.memory import MemoryService
from agent_core.personalization import PersonalizationService
from agent_core.google_workspace import GOOGLE_WORKSPACE_SLUG, GoogleConnectorError, GoogleWorkspaceExecutor, GoogleWorkspaceService
from agent_core.plugin_catalog import CATALOG, catalog_json, find_catalog_plugin
from agent_core.plugin_execution import EXECUTORS, connected_read_tools
from agent_core.prompts import DEFAULT_SYSTEM_PROMPT
from agent_core.providers import build_client
from agent_core.storage import ArtifactChunk, AuthRepository, BackgroundJob, BackgroundJobRepository, Chat, ChatMessage, ChatRepository, ChatShare, ConnectorRepository, Database, Document, KnowledgeCollection, LibraryAsset, MediaAttachment, MediaRepository, ModelRegistryRepository, Plugin, Project, PromptTemplate, Schedule, ScheduleRepository, ScheduleRun, WorkspaceRepository, current_user_id
from agent_core.auth import AuthError, AuthService, SESSION_COOKIE
from agent_core.tools import ToolSpec, build_default_registry


@dataclass
class Services:
    settings: Settings
    chats: ChatRepository
    knowledge: KnowledgeService
    media: MediaService
    memory: MemoryService
    workspace: WorkspaceRepository
    library: LibraryService
    artifacts: ArtifactService
    google_workspace: GoogleWorkspaceService
    auth: AuthService
    model_registry: ModelRegistryRepository
    credentials: UserCredentialService
    personalization: PersonalizationService


class CreateChatRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    context_source_chat_id: str | None = Field(default=None, alias="contextSourceChatId")
    project_id: str | None = Field(default=None, alias="projectId")
    collection_id: str | None = Field(default=None, alias="collectionId")

    model_config = {"populate_by_name": True}


class UpdateChatRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    pinned: bool | None = None
    archived: bool | None = None
    project_id: str | None = Field(default=None, alias="projectId")
    collection_id: str | None = Field(default=None, alias="collectionId")

    model_config = {"populate_by_name": True}


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    attachment_ids: list[str] = Field(default_factory=list, alias="attachmentIds")

    model_config = {"populate_by_name": True}


class ShareRequest(BaseModel):
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    model_config = {"populate_by_name": True}


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    status: Literal["active", "paused", "completed"] = "active"
    instructions: str | None = Field(default=None, max_length=10_000)
    memory_mode: Literal["default", "project_only"] = Field(default="default", alias="memoryMode")

    model_config = {"populate_by_name": True}


class KnowledgeCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)


class CollectionDocumentsRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")

    model_config = {"populate_by_name": True}


class DeleteProjectRequest(BaseModel):
    confirm_name: str = Field(alias="confirmName", min_length=1, max_length=160)

    model_config = {"populate_by_name": True}


class UpdateArtifactRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    project_id: str | None = Field(default=None, alias="projectId")
    is_project_source: bool | None = Field(default=None, alias="isProjectSource")

    model_config = {"populate_by_name": True}


class PromptTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=20_000)
    project_id: str | None = Field(default=None, alias="projectId")

    model_config = {"populate_by_name": True}


class PinMessageRequest(BaseModel):
    pinned: bool


class FeedbackRequest(BaseModel):
    kind: Literal["helpful", "incorrect", "too_long", "too_short", "unclear", "wrong_style"]
    note: str | None = Field(default=None, max_length=2000)


class BranchChatRequest(BaseModel):
    assistant_message_id: str = Field(alias="assistantMessageId")

    model_config = {"populate_by_name": True}


class AdminUserStatusRequest(BaseModel):
    is_active: bool = Field(alias="isActive")

    model_config = {"populate_by_name": True}


class AdminModelStatusRequest(BaseModel):
    is_active: bool = Field(alias="isActive")

    model_config = {"populate_by_name": True}


class ApiKeyRequest(BaseModel):
    api_key: str = Field(alias="apiKey", min_length=8, max_length=1000)

    model_config = {"populate_by_name": True}


class ScheduleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    notes: str | None = Field(default=None, max_length=10_000)
    project_id: str | None = Field(default=None, alias="projectId")
    prompt: str | None = Field(default=None, max_length=10_000)
    recurrence: Literal["once", "daily", "weekly"] = "once"
    status: Literal["active", "paused", "completed"] = "active"
    next_run_at: datetime | None = Field(default=None, alias="nextRunAt")
    timezone: str = "Asia/Ho_Chi_Minh"

    model_config = {"populate_by_name": True}


class ScheduleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    starts_at: datetime | None = Field(default=None, alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    notes: str | None = Field(default=None, max_length=10_000)
    project_id: str | None = Field(default=None, alias="projectId")
    prompt: str | None = Field(default=None, max_length=10_000)
    recurrence: Literal["once", "daily", "weekly"] | None = None
    status: Literal["active", "paused", "completed"] | None = None
    next_run_at: datetime | None = Field(default=None, alias="nextRunAt")
    timezone: str | None = None

    model_config = {"populate_by_name": True}


class PluginRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    enabled: bool = False
    config: dict[str, Any] | None = None


class PluginUpdateRequest(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    enabled: bool | None = None
    config: dict[str, Any] | None = None


def chat_json(chat: Chat) -> dict[str, Any]:
    return {
        "id": chat.id,
        "title": chat.title,
        "provider": chat.provider,
        "model": chat.model,
        "createdAt": chat.created_at.isoformat(),
        "updatedAt": chat.updated_at.isoformat(),
        "pinned": chat.pinned,
        "archived": chat.archived,
        "contextSourceChatId": chat.context_source_chat_id,
        "projectId": getattr(chat, "project_id", None),
        "parentChatId": getattr(chat, "parent_chat_id", None),
        "branchFromPosition": getattr(chat, "branch_from_position", None),
        "collectionId": getattr(chat, "collection_id", None),
    }


def share_json(share: ChatShare) -> dict[str, Any]:
    return {"token": share.token, "title": share.title, "provider": share.provider, "model": share.model, "messages": share.messages, "createdAt": share.created_at.isoformat(), "updatedAt": share.updated_at.isoformat(), "expiresAt": share.expires_at.isoformat() if share.expires_at else None}


def document_json(document: Document, job: BackgroundJob | None = None) -> dict[str, Any]:
    return {
        "id": document.id,
        "name": document.original_name,
        "status": document.status,
        "pageCount": document.page_count,
        "error": document.error,
        "jobAttempts": job.attempts if job else 0,
        "jobMaxAttempts": job.max_attempts if job else 3,
        "jobError": job.last_error if job else None,
        "projectId": document.project_id,
        "url": f"/api/documents/{document.id}/file",
    }


def collection_json(item: KnowledgeCollection, documents: list[Document] | None = None) -> dict[str, Any]:
    return {
        "id": item.id, "projectId": item.project_id, "name": item.name, "description": item.description,
        "documentIds": [document.id for document in documents] if documents is not None else None,
        "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat(),
    }


def media_json(media: MediaAttachment) -> dict[str, Any]:
    return {"id": media.id, "name": media.original_name, "mimeType": media.mime_type, "url": f"/uploads/{media.stored_name}", "sizeBytes": media.size_bytes}


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
    return result


SOURCE_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((/api/documents/[^)#]+(?:#[^)]+)?)\)")
SOURCE_LABEL_ONLY_PATTERN = re.compile(
    r"^\s*(?:nguồn(?:\s+\d+)?|sources?|tham\s+khảo)\s*[:\-–—]?\s*$",
    re.IGNORECASE,
)


def detach_response_sources(content: str) -> tuple[str, list[dict[str, str]]]:
    """Move document links out of the visible answer into the message source menu."""
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for name, url in SOURCE_LINK_PATTERN.findall(content):
        if url not in seen:
            sources.append({"name": name, "url": url})
            seen.add(url)
    if not sources:
        return content, []
    # A citation may appear at the end of a useful sentence. Remove only the
    # link itself; dropping the complete line would silently discard answer text.
    lines = []
    for line in content.splitlines():
        cleaned_line = SOURCE_LINK_PATTERN.sub("", line).rstrip()
        cleaned_line = re.sub(r"\s+([,.;:!?])", r"\1", cleaned_line)
        if SOURCE_LABEL_ONLY_PATTERN.fullmatch(cleaned_line):
            continue
        lines.append(cleaned_line)
    cleaned = "\n".join(lines).strip()
    return cleaned or "Đã sử dụng tài liệu trong Thư viện để trả lời.", sources


def template_json(item: PromptTemplate) -> dict[str, Any]:
    return {"id": item.id, "name": item.name, "content": item.content, "projectId": item.project_id, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def project_json(item: Project) -> dict[str, Any]:
    return {"id": item.id, "name": item.name, "description": item.description, "status": item.status, "instructions": item.instructions, "memoryMode": item.memory_mode, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def schedule_json(item: Schedule) -> dict[str, Any]:
    return {"id": item.id, "title": item.title, "startsAt": item.starts_at.isoformat(), "endsAt": item.ends_at.isoformat() if item.ends_at else None, "notes": item.notes, "projectId": item.project_id, "chatId": item.chat_id, "prompt": item.prompt, "recurrence": item.recurrence, "status": item.status, "nextRunAt": item.next_run_at.isoformat() if item.next_run_at else None, "lastRunAt": item.last_run_at.isoformat() if item.last_run_at else None, "timezone": item.timezone, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def schedule_run_json(item: ScheduleRun) -> dict[str, Any]:
    return {"id": item.id, "scheduleId": item.schedule_id, "scheduledFor": item.scheduled_for.isoformat(), "status": item.status, "summary": item.summary, "error": item.error, "startedAt": item.started_at.isoformat(), "finishedAt": item.finished_at.isoformat() if item.finished_at else None}


def library_asset_json(item: LibraryAsset) -> dict[str, Any]:
    return {"id": item.id, "artifactId": item.artifact_id, "name": item.name, "version": item.version, "mimeType": item.mime_type, "sizeBytes": item.size_bytes, "source": item.source, "projectId": item.project_id, "isProjectSource": item.is_project_source, "indexStatus": item.index_status, "indexError": item.index_error, "createdAt": item.created_at.isoformat(), "url": f"/api/library/assets/{item.id}/file"}


def plugin_json(item: Plugin) -> dict[str, Any]:
    return {"id": item.id, "slug": item.slug, "name": item.name, "description": item.description, "enabled": item.enabled, "config": item.config, "catalogSlug": item.catalog_slug, "category": item.category, "capabilities": item.capabilities, "connectionStatus": item.connection_status, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def model_error_message(chat: Chat, error: Exception) -> str:
    """Give an actionable provider/model error without altering persisted chats."""
    raw = str(error)
    normalized = raw.lower()
    label = f"{chat.provider} / {chat.model}"
    if "reasoning_effort" in normalized and "function tools" in normalized:
        return f"Model {label} không hỗ trợ reasoning khi dùng công cụ ở chế độ hiện tại. Hãy thử gửi lại hoặc chọn model khác."
    if "model" in normalized and ("not found" in normalized or "does not exist" in normalized):
        return f"Model {label} không khả dụng với API key hiện tại. Hãy chọn model khác trong danh sách."
    return f"Không thể gọi model {label}: {raw}"


RECENT_USER_TURNS = 10


def recent_chat_history(history: list[dict[str, Any]], max_user_turns: int = RECENT_USER_TURNS) -> list[dict[str, Any]]:
    """Return whole turns from the oldest of the requested recent user prompts."""
    user_positions = [index for index, item in enumerate(history) if item.get("role") == "user"]
    if len(user_positions) <= max_user_turns:
        return history
    return history[user_positions[-max_user_turns]:]


def persisted_history(full_history: list[dict[str, Any]], agent_history: list[dict[str, Any]], initial_length: int) -> list[dict[str, Any]]:
    """Keep archived turns while appending only messages generated for this request."""
    return [*full_history, *agent_history[initial_length:]]


def make_agent(
    app_services: Services,
    chat: Chat,
    memory_context: str = "",
    knowledge_context: str = "",
    personalization_context: str = "",
    plugin_tools: list[ToolSpec] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> Agent:
    try:
        settings = selected_settings(chat.provider, chat.model, chat.user_id)
    except (ValueError, CredentialError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    project = app_services.workspace.get(Project, chat.project_id) if chat.project_id else None
    source_context = ""
    if chat.context_source_chat_id:
        source = app_services.chats.history(chat.context_source_chat_id)
        turns = [item for item in recent_chat_history(source) if item["role"] in {"user", "assistant"}]
        if turns:
            transcript = "\n".join(f"{item['role']}: {item['content']}" for item in turns)
            source_context = f"\n\nNgữ cảnh kế thừa từ cuộc trò chuyện trước (ẩn với người dùng):\n{transcript}"
    def create_project_export(name: str, format: str, content: str) -> str:
        asset = app_services.library.create_export(name, format, content, project_id=chat.project_id)
        enqueue_artifact_index(asset, app_services)
        return json.dumps(library_asset_json(asset), ensure_ascii=False)

    export_tool = ToolSpec(
        name="create_file",
        description="Tạo file cho người dùng và lưu vào Thư viện. Dùng khi người dùng yêu cầu xuất DOCX, XLSX, PPTX, Markdown, CSV, PDF hoặc JSON.",
        parameters={"type": "object", "properties": {"name": {"type": "string"}, "format": {"type": "string", "enum": ["docx", "xlsx", "pptx", "md", "csv", "pdf", "json"]}, "content": {"type": "string"}}, "required": ["name", "format", "content"]},
        func=create_project_export,
    )
    agent = Agent(
        build_client(settings),
        build_default_registry(
            build_knowledge_tool(app_services.knowledge, chat.project_id, chat.collection_id),
            ([build_artifact_tool(app_services.artifacts, chat.project_id)] if chat.project_id else []) + [export_tool, *(plugin_tools or [])],
        ),
        system_prompt=DEFAULT_SYSTEM_PROMPT + (f"\n\nHướng dẫn dự án:\n{project.instructions}" if project and project.instructions else "") + ("\n\nKhi dùng knowledge base, giữ nguyên Markdown link của nguồn và nêu vị trí nguồn để người dùng mở đúng tài liệu." if chat.collection_id or chat.project_id is None else "") + source_context + (f"\n\nNgữ cảnh Thư viện RAG đã được truy xuất tự động trước câu hỏi này:\n{knowledge_context}\n\nƯu tiên trả lời dựa trên ngữ cảnh này khi nó liên quan trực tiếp; giữ nguyên link nguồn. Nếu không liên quan, không được suy diễn hoặc viện dẫn nó." if knowledge_context else "") + (f"\n\n{personalization_context}" if personalization_context else "") + (f"\n\n{memory_context}" if memory_context else ""),
        max_steps=settings.max_steps,
    )
    stored_history = history if history is not None else app_services.chats.history(chat.id)
    # `persisted_history()` appends the agent's new turn to `stored_history`.
    # Never hand that same list to Agent: `Agent.run()` appends in place and
    # would make both references contain the new turn, which then persists it
    # twice. A new list also keeps the no-attachment hydration fast path safe.
    agent_history = [dict(item) for item in recent_chat_history(stored_history)]
    agent.history = app_services.media.hydrate_history(agent_history)
    return agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    database = Database(settings.database_url)
    media = MediaService(MediaRepository(database), settings.media_dir)
    google_workspace = GoogleWorkspaceService(ConnectorRepository(database), settings)
    model_registry = ModelRegistryRepository(database)
    model_registry.seed(settings.provider_models)
    EXECUTORS[GOOGLE_WORKSPACE_SLUG] = GoogleWorkspaceExecutor(google_workspace)
    auth_repository = AuthRepository(database)
    app.state.services = Services(
        settings=settings,
        chats=ChatRepository(database),
        knowledge=KnowledgeService(database, Path(settings.knowledge_dir), settings.embedding_model),
        media=media,
        library=LibraryService(database, settings.media_dir),
        artifacts=ArtifactService(database, settings.media_dir, settings.embedding_model),
        memory=MemoryService(database, settings.embedding_model),
        workspace=WorkspaceRepository(database),
        google_workspace=google_workspace,
        auth=AuthService(auth_repository, settings),
        model_registry=model_registry,
        credentials=UserCredentialService(auth_repository, settings),
        personalization=PersonalizationService(database),
    )
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
UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_authenticated_api_user(request: Request, call_next):
    path = request.url.path
    public_prefixes = ("/api/health", "/api/config", "/api/auth/", "/api/public/shares/", "/docs", "/openapi.json")
    if not path.startswith("/api/") or path.startswith(public_prefixes) or request.method == "OPTIONS":
        return await call_next(request)
    user = services().auth.session_user(request.cookies.get(SESSION_COOKIE))
    if user is None:
        return Response(content=json.dumps({"detail": "Cần đăng nhập để truy cập workspace."}, ensure_ascii=False), status_code=401, media_type="application/json")
    token = current_user_id.set(user.id)
    request.state.user = user
    try:
        return await call_next(request)
    finally:
        current_user_id.reset(token)


def services() -> Services:
    return app.state.services


def user_json(user) -> dict[str, Any]:
    role = "system_admin" if services().auth.is_system_admin(user) else user.role
    return {"id": user.id, "email": user.email, "displayName": user.display_name, "role": role, "isActive": user.is_active}


def require_system_admin(request: Request):
    user = getattr(request.state, "user", None)
    if user is None or not services().auth.is_system_admin(user):
        raise HTTPException(status_code=403, detail="Chỉ system admin mới được truy cập.")
    return user


def selected_settings(provider: str, model: str, user_id: str | None) -> Settings:
    app_services = services()
    if model not in app_services.model_registry.active().get(provider, ()):
        raise ValueError("Model đang tắt hoặc chưa được hệ thống cho phép.")
    return app_services.settings.with_provider_model(provider, model, app_services.credentials.api_key(user_id, provider))


def available_provider_models(user_id: str | None) -> dict[str, list[str]]:
    app_services = services()
    configured = app_services.settings.configured_provider_models()
    personal_providers = {item.provider for item in app_services.credentials.list_metadata(user_id)} if user_id else set()
    active = app_services.model_registry.active()
    return {
        provider: [model for model in models if model in active.get(provider, ())]
        for provider, models in app_services.settings.provider_models.items()
        if (provider in configured or provider in personal_providers) and any(model in active.get(provider, ()) for model in models)
    }


def credential_json(item) -> dict[str, Any]:
    return {
        "provider": item.provider,
        "keyHint": item.key_hint,
        "validatedAt": item.validated_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
    }


@app.get("/api/auth/me", tags=["Authentication"])
def auth_me(request: Request) -> dict[str, Any]:
    user = services().auth.session_user(request.cookies.get(SESSION_COOKIE))
    return {"user": user_json(user) if user else None}


@app.get("/api/auth/google/authorize", tags=["Authentication"])
def start_google_sign_in(email: str | None = Query(default=None, max_length=320)) -> RedirectResponse:
    try:
        return RedirectResponse(services().auth.google_authorization_url(email), status_code=302)
    except AuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/auth/google/callback", tags=["Authentication"])
def complete_google_sign_in(code: str | None = Query(default=None), state: str | None = Query(default=None), error: str | None = Query(default=None)) -> RedirectResponse:
    base_url = services().settings.app_web_url
    if error or not code or not state:
        return RedirectResponse(f"{base_url}/login?{urlencode({'authError': 'Google sign-in đã bị hủy hoặc không hoàn tất.'})}", status_code=303)
    try:
        _user, session_token = services().auth.complete_google_sign_in(code, state)
    except AuthError as exc:
        return RedirectResponse(f"{base_url}/login?{urlencode({'authError': str(exc)})}", status_code=303)
    response = RedirectResponse(f"{base_url}/?auth=google", status_code=303)
    response.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="lax", secure=base_url.startswith("https://"), max_age=services().settings.auth_session_days * 86400, path="/")
    return response


@app.post("/api/auth/logout", status_code=204, tags=["Authentication"])
def auth_logout(request: Request, response: Response) -> None:
    services().auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")


@app.get("/api/admin/overview", tags=["System admin"])
def admin_overview(request: Request) -> dict[str, Any]:
    require_system_admin(request)
    configured = services().settings.configured_provider_models()
    providers: dict[str, dict[str, Any]] = {
        name: {"models": [], "configured": bool(configured.get(name))}
        for name in services().settings.provider_models
    }
    for model in services().model_registry.list():
        providers.setdefault(model.provider, {"models": [], "configured": bool(configured.get(model.provider))})
        providers[model.provider]["models"].append({"id": model.model_id, "displayName": model.display_name, "isActive": model.is_active})
    return {
        "counts": services().auth.repository.system_counts(),
        "worker": BackgroundJobRepository(services().chats.database).worker_status(datetime.now(UTC)),
        "providers": providers,
    }


@app.get("/api/settings/api-keys", tags=["Settings"])
def list_api_keys(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    return {"items": [credential_json(item) for item in services().credentials.list_metadata(user.id)]}


@app.put("/api/settings/api-keys/{provider}", tags=["Settings"])
def save_api_key(provider: str, payload: ApiKeyRequest, request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    try:
        item = services().credentials.save(user.id, provider, payload.api_key)
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    services().auth.repository.add_system_audit("user_api_key_saved", actor_user_id=user.id, summary=f"Cập nhật API key {provider}.")
    return credential_json(item)


@app.delete("/api/settings/api-keys/{provider}", status_code=204, tags=["Settings"])
def delete_api_key(provider: str, request: Request) -> None:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Cần đăng nhập.")
    try:
        deleted = services().credentials.delete(user.id, provider)
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Chưa có API key cho provider này.")
    services().auth.repository.add_system_audit("user_api_key_deleted", actor_user_id=user.id, summary=f"Xóa API key {provider}.")


@app.get("/api/admin/users", tags=["System admin"])
def admin_users(request: Request, q: str | None = Query(default=None, max_length=160), offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100)) -> dict[str, Any]:
    require_system_admin(request)
    rows, total = services().auth.repository.list_users(q, offset, limit)
    return {
        "items": [
            {**user_json(user), "createdAt": user.created_at.isoformat(), "lastSignInAt": last_sign_in.isoformat() if last_sign_in else None}
            for user, last_sign_in in rows
        ],
        "total": total,
    }


@app.patch("/api/admin/users/{user_id}/active", tags=["System admin"])
def admin_set_user_active(user_id: str, payload: AdminUserStatusRequest, request: Request) -> dict[str, Any]:
    admin = require_system_admin(request)
    active = payload.is_active
    if user_id == admin.id and not active:
        raise HTTPException(status_code=422, detail="Không thể tự vô hiệu hóa system admin.")
    user = services().auth.repository.set_user_active(user_id, active)
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy user.")
    services().auth.repository.add_system_audit(
        "user_activated" if active else "user_deactivated",
        actor_user_id=admin.id,
        subject_user_id=user.id,
        summary=f"{'Kích hoạt' if active else 'Vô hiệu hóa'} user.",
    )
    return user_json(user)


@app.patch("/api/admin/models/{provider}/{model_id}/active", tags=["System admin"])
def admin_set_model_active(provider: str, model_id: str, payload: AdminModelStatusRequest, request: Request) -> dict[str, Any]:
    admin = require_system_admin(request)
    model = services().model_registry.set_active(provider, model_id, payload.is_active)
    if model is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy model.")
    services().auth.repository.add_system_audit(
        "model_activated" if model.is_active else "model_deactivated",
        actor_user_id=admin.id,
        summary=f"{'Kích hoạt' if model.is_active else 'Vô hiệu hóa'} {model.provider}/{model.model_id}.",
    )
    return {"id": model.model_id, "displayName": model.display_name, "isActive": model.is_active}


@app.get("/api/admin/credentials", tags=["System admin"])
def admin_credentials(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
    require_system_admin(request)
    rows, total = services().auth.repository.provider_credential_metadata(offset, limit)
    return {
        "items": [
            {"id": credential.id, "userId": user.id, "userEmail": user.email, "provider": credential.provider, "keyHint": credential.key_hint, "validatedAt": credential.validated_at.isoformat(), "updatedAt": credential.updated_at.isoformat()}
            for credential, user in rows
        ],
        "total": total,
    }


@app.get("/api/admin/audit", tags=["System admin"])
def admin_audit(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
    require_system_admin(request)
    rows, total = services().auth.repository.list_system_audit(offset, limit)
    def audit_json(item) -> dict[str, Any]:
        actor = services().auth.repository.get_user(item.actor_user_id) if item.actor_user_id else None
        subject = services().auth.repository.get_user(item.subject_user_id) if item.subject_user_id else None
        return {"id": item.id, "eventType": item.event_type, "actorUserId": item.actor_user_id, "actorEmail": actor.email if actor else None, "subjectUserId": item.subject_user_id, "subjectEmail": subject.email if subject else None, "summary": item.summary, "createdAt": item.created_at.isoformat()}
    return {"items": [audit_json(item) for item in rows], "total": total}


@app.get("/api/admin/plugin-connections", tags=["System admin"])
def admin_plugin_connections(
    request: Request,
    q: str | None = Query(default=None, max_length=160),
    connector_slug: str | None = Query(default=None, max_length=80),
    status: str | None = Query(default=None, max_length=32),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    require_system_admin(request)
    rows, total = ConnectorRepository(services().chats.database).list_connection_metadata(
        offset, limit, q, connector_slug, status
    )
    return {
        "items": [
            {
                "id": connection["id"],
                "userId": connection["user_id"],
                "userEmail": connection["user_email"],
                "connectorSlug": connection["connector_slug"],
                "status": connection["status"],
                "scopeCount": len(connection["scopes"] or []),
                "expiresAt": connection["expires_at"].isoformat() if connection["expires_at"] else None,
                "createdAt": connection["created_at"].isoformat(),
                "updatedAt": connection["updated_at"].isoformat(),
            }
            for connection in rows
        ],
        "total": total,
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
    if not asset.is_project_source:
        return None
    selected = app_services or services()
    jobs = BackgroundJobRepository(selected.chats.database)
    job, created = jobs.enqueue_unique("artifact_index", {"asset_id": asset.id}, dedupe_key=f"artifact:{asset.id}")
    if created:
        asset.index_status, asset.index_error = "queued", None
    return job


def queue_pending_artifacts(app_services: Services) -> int:
    """Backfill Project Sources created before the artifact index existed."""
    with app_services.chats.database.session() as session:
        assets = list(session.scalars(select(LibraryAsset).where(
            LibraryAsset.is_project_source.is_(True),
            LibraryAsset.index_status.in_(("pending", "queued")),
        )))
    for asset in assets:
        enqueue_artifact_index(asset, app_services)
    if assets:
        with app_services.chats.database.session() as session:
            for asset_id in [item.id for item in assets]:
                item = session.get(LibraryAsset, asset_id)
                if item and item.index_status == "pending":
                    item.index_status = "queued"
            session.commit()
    return len(assets)


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


@app.get("/api/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", tags=["System"])
def config(request: Request) -> dict[str, Any]:
    settings = services().settings
    user = services().auth.session_user(request.cookies.get(SESSION_COOKIE))
    providers = available_provider_models(user.id if user else None)
    default_provider = settings.provider if settings.active_model in providers.get(settings.provider, []) else next(iter(providers), settings.provider)
    default_model = settings.active_model if settings.active_model in providers.get(default_provider, []) else (providers.get(default_provider) or [settings.active_model])[0]
    return {
        "providers": providers,
        "defaultProvider": default_provider,
        "defaultModel": default_model,
    }


@app.get("/api/chats", tags=["Chats"])
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


@app.post("/api/chats", status_code=201, tags=["Chats"])
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
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
    if payload.collection_id:
        collection = services().knowledge.get_collection(payload.collection_id)
        if collection is None or collection.project_id != payload.project_id:
            raise HTTPException(status_code=422, detail="Collection phải thuộc Project đã chọn.")
    return chat_json(services().chats.create(selected.provider, selected.active_model, source_id, payload.project_id, payload.collection_id))


@app.get("/api/memories", tags=["Memory library"])
def memories(query: str = "") -> list[dict[str, Any]]:
    return services().memory.list(query)


@app.delete("/api/memories/{memory_id}", status_code=204, tags=["Memory library"])
def forget_memory(memory_id: str) -> None:
    if not services().memory.forget(memory_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy memory.")


@app.delete("/api/memories", status_code=204, tags=["Memory library"])
def forget_all_memories() -> None:
    services().memory.forget_all()


@app.get("/api/library/assets", tags=["Personal library"])
def list_library_assets(
    query: str = "",
    scope: Literal["all", "global", "project"] = "all",
    project_id: str | None = Query(default=None, alias="projectId"),
) -> list[dict[str, Any]]:
    if scope == "project" and not project_id:
        raise HTTPException(status_code=422, detail="Cần chọn Project để lọc file.")
    return [library_asset_json(item) for item in services().library.list(query, project_id, scope)]


@app.post("/api/library/assets", status_code=201, tags=["Personal library"])
async def upload_library_assets(
    files: list[UploadFile] = File(...),
    project_id: str | None = Form(default=None, alias="projectId"),
) -> dict[str, list[dict[str, Any]]]:
    """Accept a batch without discarding valid files because one entry is invalid."""
    uploaded: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if project_id and services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
    for file in files:
        name = file.filename or "file"
        try:
            asset = services().library.upload(name, file.content_type or "", await file.read(), project_id=project_id)
            enqueue_artifact_index(asset)
            uploaded.append(library_asset_json(asset))
        except ValueError as exc:
            errors.append({"name": name, "message": str(exc)})
    return {"items": uploaded, "errors": errors}


@app.patch("/api/library/assets/{asset_id}", tags=["Personal library"])
def update_library_asset(asset_id: str, payload: UpdateArtifactRequest) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    project_id = values.get("project_id")
    if project_id and services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
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
        raise HTTPException(status_code=404, detail="Không tìm thấy artifact.")
    enqueue_artifact_index(item)
    return library_asset_json(item)


@app.post("/api/library/assets/{asset_id}/versions", status_code=201, tags=["Personal library"])
async def create_library_asset_version(asset_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        item = services().library.create_version(asset_id, file.filename or "artifact", file.content_type or "", await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    enqueue_artifact_index(item)
    return library_asset_json(item)


@app.get("/api/library/assets/{asset_id}/versions", tags=["Personal library"])
def list_library_asset_versions(asset_id: str) -> list[dict[str, Any]]:
    items = services().library.versions(asset_id)
    if not items:
        raise HTTPException(status_code=404, detail="Không tìm thấy artifact.")
    return [library_asset_json(item) for item in items]


@app.get("/api/library/assets/{asset_id}/preview", tags=["Personal library"])
def preview_library_asset(asset_id: str) -> dict[str, Any]:
    try:
        return services().artifacts.preview(asset_id)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(status_code=404 if "Không tìm thấy" in message else 422, detail=message) from exc


@app.get("/api/library/assets/{asset_id}/file", tags=["Personal library"])
def library_asset_file(asset_id: str) -> FileResponse:
    with services().chats.database.session() as session:
        asset = session.get(LibraryAsset, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy artifact.")
        path = Path(services().settings.media_dir) / asset.stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file artifact.")
    return FileResponse(path, media_type=asset.mime_type, filename=asset.name, content_disposition_type="inline")


@app.post("/api/library/assets/{asset_id}/reindex", status_code=202, tags=["Personal library"])
def reindex_library_asset(asset_id: str) -> dict[str, Any]:
    with services().chats.database.session() as session:
        asset = session.get(LibraryAsset, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy artifact.")
        if not asset.is_project_source:
            raise HTTPException(status_code=422, detail="Chỉ Project Source mới cần index.")
        asset.index_status, asset.index_error = "queued", None
        session.commit()
    enqueue_artifact_index(asset)
    return library_asset_json(asset)


@app.delete("/api/library/assets/{asset_id}", status_code=204, tags=["Personal library"])
def delete_library_asset(asset_id: str) -> None:
    with services().chats.database.session() as session:
        asset = session.get(LibraryAsset, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy file trong Thư viện.")
        versions = session.scalars(select(LibraryAsset).where(LibraryAsset.artifact_id == asset.artifact_id)).all()
        queue_file_cleanup(
            session,
            [{"storage": "media", "stored_name": item.stored_name} for item in versions],
            f"artifact-cleanup:{asset.artifact_id}",
        )
        for item in versions:
            session.delete(item)
        session.commit()


@app.get("/api/chats/{chat_id}", tags=["Chats"])
def get_chat(chat_id: str) -> dict[str, Any]:
    chat = services().chats.get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return chat_json(chat)


@app.get("/api/chats/{chat_id}/messages", tags=["Chats"])
def messages(chat_id: str) -> list[dict[str, Any]]:
    if services().chats.get(chat_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    history = [item for item in services().chats.history(chat_id) if item["role"] in {"user", "assistant"}]
    feedback = services().personalization.feedback_by_message_ids(
        [item["message_id"] for item in history if item["role"] == "assistant" and item.get("message_id")]
    )
    return [
        message_json({**item, "feedback_kind": feedback.get(item.get("message_id"))} if item["role"] == "assistant" else item)
        for item in history
    ]


@app.patch("/api/messages/{message_id}/pin", tags=["Chats"])
def pin_message(message_id: str, payload: PinMessageRequest) -> dict[str, Any]:
    message = services().chats.set_message_pin(message_id, payload.pinned)
    if message is None:
        raise HTTPException(status_code=404, detail="Chỉ có thể ghim message của bạn.")
    return {"messageId": message.id, "pinned": message.pinned}


@app.post("/api/messages/{message_id}/feedback", status_code=201, tags=["Chats"])
def create_response_feedback(message_id: str, payload: FeedbackRequest) -> dict[str, Any]:
    try:
        item = services().personalization.record_feedback(message_id, payload.kind, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": item.id, "messageId": item.message_id, "kind": item.kind, "note": item.note}


@app.post("/api/chats/{chat_id}/branches", status_code=201, tags=["Chats"])
def create_chat_branch(chat_id: str, payload: BranchChatRequest) -> dict[str, Any]:
    try:
        return chat_json(services().chats.create_branch(chat_id, payload.assistant_message_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/chats/{chat_id}/regenerate", tags=["Chats"])
def prepare_chat_regeneration(chat_id: str, payload: BranchChatRequest) -> dict[str, str]:
    try:
        return {"content": services().chats.prepare_regeneration(chat_id, payload.assistant_message_id)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/chats/{chat_id}/pins", tags=["Chats"])
def list_chat_pins(chat_id: str) -> list[dict[str, Any]]:
    if services().chats.get(chat_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return [{"messageId": message.id, "position": message.position, "content": message.content} for message in services().chats.chat_pins(chat_id)]


@app.get("/api/templates", tags=["Workspace"])
def list_templates(project_id: str | None = Query(default=None, alias="projectId")) -> list[dict[str, Any]]:
    with services().chats.database.session() as session:
        statement = select(PromptTemplate).order_by(PromptTemplate.updated_at.desc())
        if project_id:
            statement = statement.where(PromptTemplate.project_id.in_((None, project_id)))
        else:
            statement = statement.where(PromptTemplate.project_id.is_(None))
        return [template_json(item) for item in session.scalars(statement)]


@app.post("/api/templates", status_code=201, tags=["Workspace"])
def create_template(payload: PromptTemplateRequest) -> dict[str, Any]:
    if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
    return template_json(services().workspace.create(PromptTemplate, **payload.model_dump()))


@app.patch("/api/templates/{template_id}", tags=["Workspace"])
def update_template(template_id: str, payload: PromptTemplateRequest) -> dict[str, Any]:
    if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
    item = services().workspace.update(PromptTemplate, template_id, **payload.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy template.")
    return template_json(item)


@app.delete("/api/templates/{template_id}", status_code=204, tags=["Workspace"])
def delete_template(template_id: str) -> None:
    if not services().workspace.delete(PromptTemplate, template_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy template.")


@app.patch("/api/chats/{chat_id}", tags=["Chats"])
def update_chat(chat_id: str, payload: UpdateChatRequest) -> dict[str, Any]:
    try:
        chat = services().chats.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
        provider, model = payload.provider or chat.provider, payload.model or chat.model
        selected_settings(provider, model, current_user_id.get())
        if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
            raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
        values = {"provider": provider, "model": model}
        if "collection_id" in payload.model_fields_set and payload.collection_id:
            collection = services().knowledge.get_collection(payload.collection_id)
            target_project = payload.project_id if "project_id" in payload.model_fields_set else chat.project_id
            if collection is None or collection.project_id != target_project:
                raise HTTPException(status_code=422, detail="Collection phải thuộc Project của chat.")
        for field in ("title", "pinned", "archived", "project_id", "collection_id"):
            if field in payload.model_fields_set:
                values[field] = getattr(payload, field)
        if "project_id" in payload.model_fields_set and "collection_id" not in payload.model_fields_set:
            values["collection_id"] = None
        chat = services().chats.update(chat_id, **values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return chat_json(chat)


@app.delete("/api/chats/{chat_id}", status_code=204, tags=["Chats"])
def delete_chat(chat_id: str) -> None:
    if not services().chats.delete(chat_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")


@app.post("/api/chats/{chat_id}/share", tags=["Shared chats"])
def share_chat(chat_id: str, payload: ShareRequest | None = None) -> dict[str, Any]:
    expires_at = payload.expires_at if payload else None
    if expires_at and expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Thời hạn chia sẻ phải ở tương lai.")
    share = services().chats.create_or_update_share(chat_id, expires_at)
    if share is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return share_json(share)


@app.delete("/api/chats/{chat_id}/share", status_code=204, tags=["Shared chats"])
def revoke_share(chat_id: str) -> None:
    if not services().chats.revoke_share(chat_id):
        raise HTTPException(status_code=404, detail="Chat chưa có liên kết chia sẻ.")


@app.get("/api/public/shares/{token}", tags=["Shared chats"])
def public_share(token: str) -> dict[str, Any]:
    share = services().chats.get_share(token)
    if share is None or (share.expires_at and share.expires_at <= datetime.now(UTC)):
        raise HTTPException(status_code=404, detail="Liên kết chia sẻ không tồn tại hoặc đã bị thu hồi.")
    return share_json(share)


@app.get("/api/documents", tags=["Knowledge base"])
def documents() -> list[dict[str, Any]]:
    jobs = BackgroundJobRepository(services().chats.database)
    return [document_json(item, jobs.latest_for_document(item.id)) for item in services().knowledge.list_documents()]


@app.get("/api/projects/{project_id}/collections", tags=["Knowledge base"])
def list_collections(project_id: str) -> list[dict[str, Any]]:
    if services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy Project.")
    return [collection_json(item, services().knowledge.collection_documents(item.id)) for item in services().knowledge.list_collections(project_id)]


@app.post("/api/projects/{project_id}/collections", status_code=201, tags=["Knowledge base"])
def create_collection(project_id: str, payload: KnowledgeCollectionRequest) -> dict[str, Any]:
    if services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy Project.")
    try:
        return collection_json(services().knowledge.create_collection(project_id, payload.name, payload.description), [])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/collections/{collection_id}", tags=["Knowledge base"])
def update_collection(collection_id: str, payload: KnowledgeCollectionRequest) -> dict[str, Any]:
    try:
        item = services().knowledge.update_collection(collection_id, payload.name, payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy collection.")
    return collection_json(item, services().knowledge.collection_documents(item.id))


@app.put("/api/collections/{collection_id}/documents", tags=["Knowledge base"])
def set_collection_documents(collection_id: str, payload: CollectionDocumentsRequest) -> dict[str, Any]:
    try:
        item = services().knowledge.get_collection(collection_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy collection.")
        return collection_json(item, services().knowledge.set_collection_documents(collection_id, payload.document_ids))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/collections/{collection_id}", status_code=204, tags=["Knowledge base"])
def delete_collection(collection_id: str) -> None:
    if not services().knowledge.delete_collection(collection_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy collection.")


@app.get("/api/documents/{document_id}/file", tags=["Knowledge base"])
def document_file(document_id: str) -> FileResponse:
    with services().chats.database.session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
        path = Path(services().settings.knowledge_dir) / document.stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file tài liệu.")
    return FileResponse(path, media_type="application/pdf", filename=document.original_name, content_disposition_type="inline")


@app.get("/api/worker/status", tags=["System"])
def worker_status() -> dict[str, Any]:
    return BackgroundJobRepository(services().chats.database).worker_status(datetime.now(UTC))


@app.post("/api/documents", status_code=201, tags=["Knowledge base"])
async def upload_documents(files: list[UploadFile] = File(...), project_id: str | None = Form(default=None)) -> list[dict[str, Any]]:
    if project_id and services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
    uploaded: list[Document] = []
    try:
        for file in files:
            document, created = services().knowledge.upload(file.filename or "document.pdf", await file.read(), project_id)
            if created or document.status != "ready":
                enqueue_document_index(document)
            uploaded.append(document)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    jobs = BackgroundJobRepository(services().chats.database)
    return [document_json(item, jobs.latest_for_document(item.id)) for item in uploaded]


@app.post("/api/documents/{document_id}/reindex", status_code=202, tags=["Knowledge base"])
def reindex_document(document_id: str) -> dict[str, Any]:
    document = next((item for item in services().knowledge.list_documents() if item.id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    job = enqueue_document_index(document)
    return document_json(document, job)


@app.delete("/api/documents/{document_id}", status_code=204, tags=["Knowledge base"])
def delete_document(document_id: str) -> None:
    with services().chats.database.session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
        jobs = session.scalars(
            select(BackgroundJob).where(
                BackgroundJob.type == "document_index",
                BackgroundJob.dedupe_key == f"document:{document.id}",
                BackgroundJob.status.in_(("queued", "running")),
            )
        ).all()
        for job in jobs:
            job.status, job.locked_at, job.last_error = "cancelled", None, "Tài liệu đã bị xóa."
        queue_file_cleanup(session, [{"storage": "knowledge", "stored_name": document.stored_name}], f"document-cleanup:{document.id}")
        session.delete(document)
        session.commit()


@app.post("/api/media", status_code=201, tags=["Media"])
async def upload_media(files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    try:
        uploaded = [services().media.upload(file.filename or "image", file.content_type or "", await file.read()) for file in files]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [media_json(item) for item in uploaded]


@app.get("/api/projects", tags=["Projects"])
def list_projects() -> list[dict[str, Any]]:
    return [project_json(item) for item in services().workspace.list(Project)]


@app.post("/api/projects", status_code=201, tags=["Projects"])
def create_project(payload: ProjectRequest) -> dict[str, Any]:
    return project_json(services().workspace.create(Project, **payload.model_dump()))


@app.get("/api/projects/{project_id}", tags=["Projects"])
def get_project(project_id: str) -> dict[str, Any]:
    project = services().workspace.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    with services().chats.database.session() as session:
        project_chats = list(session.scalars(select(Chat).where(Chat.project_id == project_id).order_by(Chat.updated_at.desc())))
        project_documents = list(session.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())))
        project_assets = list(session.scalars(select(LibraryAsset).where(LibraryAsset.project_id == project_id).order_by(LibraryAsset.created_at.desc())))
        project_schedules = list(session.scalars(select(Schedule).where(Schedule.project_id == project_id).order_by(Schedule.starts_at.desc())))
    jobs = BackgroundJobRepository(services().chats.database)
    return {"project": project_json(project), "chats": [chat_json(item) for item in project_chats], "documents": [document_json(item, jobs.latest_for_document(item.id)) for item in project_documents], "assets": [library_asset_json(item) for item in project_assets], "schedules": [schedule_json(item) for item in project_schedules]}


@app.patch("/api/projects/{project_id}", tags=["Projects"])
def update_project(project_id: str, payload: ProjectRequest) -> dict[str, Any]:
    item = services().workspace.update(Project, project_id, **payload.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    return project_json(item)


@app.delete("/api/projects/{project_id}", tags=["Projects"])
def delete_project(project_id: str, payload: DeleteProjectRequest) -> dict[str, Any]:
    with services().chats.database.session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
        if payload.confirm_name != project.name:
            raise HTTPException(status_code=422, detail="Tên xác nhận chưa khớp với tên dự án.")
        documents = list(session.scalars(select(Document).where(Document.project_id == project_id)))
        assets = list(session.scalars(select(LibraryAsset).where(LibraryAsset.project_id == project_id)))
        chats_count = session.scalar(select(func.count()).select_from(Chat).where(Chat.project_id == project_id)) or 0
        schedules_count = session.scalar(select(func.count()).select_from(Schedule).where(Schedule.project_id == project_id)) or 0
        document_ids = [item.id for item in documents]
        if document_ids:
            jobs = session.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.type == "document_index",
                    BackgroundJob.dedupe_key.in_([f"document:{item_id}" for item_id in document_ids]),
                    BackgroundJob.status.in_(("queued", "running")),
                )
            ).all()
            for job in jobs:
                job.status, job.locked_at, job.last_error = "cancelled", None, "Dự án đã bị xóa."
        queue_file_cleanup(
            session,
            [
                *[{"storage": "knowledge", "stored_name": item.stored_name} for item in documents],
                *[{"storage": "media", "stored_name": item.stored_name} for item in assets],
            ],
            f"project-cleanup:{project_id}",
        )
        session.delete(project)
        session.commit()
        return {
            "deleted": {"chats": chats_count, "documents": len(documents), "assets": len(assets), "schedules": schedules_count},
            "fileCleanupQueued": bool(documents or assets),
        }


@app.get("/api/schedules", tags=["Schedules"])
def list_schedules() -> list[dict[str, Any]]:
    return [schedule_json(item) for item in services().workspace.list(Schedule)]


@app.post("/api/schedules", status_code=201, tags=["Schedules"])
def create_schedule(payload: ScheduleRequest) -> dict[str, Any]:
    if payload.ends_at and payload.ends_at < payload.starts_at:
        raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
    if payload.project_id and services().workspace.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
    values = payload.model_dump()
    values["next_run_at"] = values["next_run_at"] or values["starts_at"]
    return schedule_json(services().workspace.create(Schedule, **values))


@app.patch("/api/schedules/{schedule_id}", tags=["Schedules"])
def update_schedule(schedule_id: str, payload: ScheduleUpdateRequest) -> dict[str, Any]:
    current = services().workspace.get(Schedule, schedule_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình.")
    values = payload.model_dump(exclude_unset=True)
    starts_at = values.get("starts_at", current.starts_at)
    ends_at = values.get("ends_at", current.ends_at)
    if ends_at and ends_at < starts_at:
        raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
    project_id = values.get("project_id", current.project_id)
    if project_id and services().workspace.get(Project, project_id) is None:
        raise HTTPException(status_code=422, detail="Dự án được chọn không tồn tại.")
    if {"starts_at", "recurrence"}.intersection(values) and "next_run_at" not in values:
        values["next_run_at"] = values.get("starts_at", current.starts_at)
    if values.get("status") == "active" and current.status == "completed" and current.recurrence == "once":
        raise HTTPException(status_code=422, detail="Lịch một lần đã hoàn tất; hãy tạo lịch mới để chạy lại.")
    item = services().workspace.update(Schedule, schedule_id, **values)
    return schedule_json(item)


@app.delete("/api/schedules/{schedule_id}", status_code=204, tags=["Schedules"])
def delete_schedule(schedule_id: str) -> None:
    if not services().workspace.delete(Schedule, schedule_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình.")


@app.get("/api/schedules/{schedule_id}/runs", tags=["Schedules"])
def list_schedule_runs(schedule_id: str, limit: int = Query(default=30, ge=1, le=100)) -> list[dict[str, Any]]:
    if services().workspace.get(Schedule, schedule_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình.")
    return [schedule_run_json(item) for item in ScheduleRepository(services().chats.database).list_runs(schedule_id, limit)]


@app.post("/api/schedules/{schedule_id}/run-now", status_code=202, tags=["Schedules"])
def run_schedule_now(schedule_id: str) -> dict[str, str]:
    if services().workspace.get(Schedule, schedule_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình.")
    from agent_core.scheduler import ScheduleWorker

    Thread(target=ScheduleWorker(services()).run_now, args=(schedule_id,), daemon=True).start()
    return {"status": "queued"}


@app.get("/api/plugins", tags=["Plugins"])
def list_plugins() -> list[dict[str, Any]]:
    return [plugin_json(item) for item in services().workspace.list(Plugin)]


def google_audit_json(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "eventType": item.event_type,
        "toolName": item.tool_name,
        "summary": item.summary,
        "createdAt": item.created_at.isoformat(),
    }


def set_google_plugin_connection(status: str, enabled: bool | None = None) -> None:
    plugin = services().workspace.get_plugin_by_catalog_slug(GOOGLE_WORKSPACE_SLUG)
    if plugin is None:
        return
    values: dict[str, Any] = {"connection_status": status}
    if enabled is not None:
        values["enabled"] = enabled
    services().workspace.update(Plugin, plugin.id, **values)


@app.get("/api/connectors/google", tags=["Connectors"])
def google_connector_status() -> dict[str, Any]:
    return services().google_workspace.status()


@app.get("/api/connectors/google/audit", tags=["Connectors"])
def google_connector_audit(limit: int = Query(default=12, ge=1, le=50)) -> list[dict[str, Any]]:
    return [google_audit_json(item) for item in services().google_workspace.repository.list_audit(GOOGLE_WORKSPACE_SLUG, limit)]


@app.post("/api/connectors/google/authorize", tags=["Connectors"])
def google_authorize() -> dict[str, str]:
    if services().workspace.get_plugin_by_catalog_slug(GOOGLE_WORKSPACE_SLUG) is None:
        raise HTTPException(status_code=422, detail="Hãy thêm Google Workspace từ catalog trước khi kết nối.")
    try:
        return {"authorizationUrl": services().google_workspace.authorization_url()}
    except GoogleConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/connectors/google/callback", include_in_schema=False)
def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    base_url = services().settings.app_web_url
    if error or not code or not state:
        return RedirectResponse(f"{base_url}/plugins?{urlencode({'google': 'cancelled'})}", status_code=303)
    try:
        services().google_workspace.complete_authorization(code, state)
        set_google_plugin_connection("connected")
        user = request.state.user
        services().auth.repository.add_system_audit(
            "plugin_connected",
            actor_user_id=user.id,
            subject_user_id=user.id,
            summary="Đã kết nối Google Workspace (chỉ đọc).",
        )
        result = "connected"
    except GoogleConnectorError:
        result = "failed"
    return RedirectResponse(f"{base_url}/plugins?{urlencode({'google': result})}", status_code=303)


@app.delete("/api/connectors/google", status_code=204, tags=["Connectors"])
def google_disconnect(request: Request) -> None:
    services().google_workspace.disconnect()
    set_google_plugin_connection("not_connected", enabled=False)
    user = request.state.user
    services().auth.repository.add_system_audit(
        "plugin_disconnected",
        actor_user_id=user.id,
        subject_user_id=user.id,
        summary="Đã ngắt Google Workspace.",
    )


@app.get("/api/plugin-catalog", tags=["Plugin catalog"])
def plugin_catalog() -> list[dict[str, Any]]:
    installed = services().workspace.catalog_plugin_ids()
    return [catalog_json(item, installed.get(item.slug)) for item in CATALOG]


@app.post("/api/plugin-catalog/{slug}/install", status_code=201, tags=["Plugin catalog"])
def install_catalog_plugin(slug: str) -> dict[str, Any]:
    item = find_catalog_plugin(slug)
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy plugin trong catalog.")
    existing = services().workspace.get_plugin_by_catalog_slug(slug)
    if existing is not None:
        return plugin_json(existing)
    try:
        plugin = services().workspace.create(
            Plugin,
            slug=item.slug,
            name=item.name,
            description=item.description,
            enabled=False,
            config={},
            catalog_slug=item.slug,
            category=item.category,
            capabilities=list(item.capabilities),
            connection_status="not_connected",
        )
    except IntegrityError:
        plugin = services().workspace.get_plugin_by_catalog_slug(slug)
        if plugin is None:
            raise
    return plugin_json(plugin)


@app.post("/api/plugins", status_code=201, tags=["Plugins"])
def create_plugin(payload: PluginRequest) -> dict[str, Any]:
    try:
        return plugin_json(services().workspace.create(Plugin, **payload.model_dump()))
    except IntegrityError as exc:
        raise HTTPException(status_code=422, detail="Slug plugin đã tồn tại.") from exc


@app.patch("/api/plugins/{plugin_id}", tags=["Plugins"])
def update_plugin(plugin_id: str, payload: PluginUpdateRequest) -> dict[str, Any]:
    current = services().workspace.get(Plugin, plugin_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy plugin.")
    google_connected = services().google_workspace.status()["status"] == "connected" if current.catalog_slug == GOOGLE_WORKSPACE_SLUG else current.connection_status == "connected"
    if payload.enabled and current.catalog_slug and not google_connected:
        raise HTTPException(status_code=422, detail="Plugin catalog chưa được kết nối nên chưa thể bật.")
    try:
        item = services().workspace.update(Plugin, plugin_id, **payload.model_dump(exclude_unset=True))
    except IntegrityError as exc:
        raise HTTPException(status_code=422, detail="Slug plugin đã tồn tại.") from exc
    return plugin_json(item)


@app.delete("/api/plugins/{plugin_id}", status_code=204, tags=["Plugins"])
def delete_plugin(plugin_id: str) -> None:
    if not services().workspace.delete(Plugin, plugin_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy plugin.")


def stream_chat(chat_id: str, content: str, attachments: list[dict]) -> Iterator[str]:
    app_services = services()
    chat = app_services.chats.get(chat_id)
    if chat is None:
        yield sse("error", {"message": "Không tìm thấy chat."})
        return

    events: Queue[tuple[str, dict[str, Any]]] = Queue()

    def run() -> None:
        # ContextVar values are local to a thread.  The SSE generator hands the
        # actual agent work to a new thread, so restore the chat owner there;
        # otherwise user-scoped repositories see no user and return no chat,
        # history or credentials.
        user_token = current_user_id.set(chat.user_id)
        try:
            events.put(("status", {"message": "Agent đang suy nghĩ..."}))
            full_history = app_services.chats.history(chat_id)
            try:
                project = app_services.workspace.get(Project, chat.project_id) if chat.project_id else None
                memory_context = app_services.memory.recall(
                    content,
                    chat_id,
                    chat.context_source_chat_id,
                    project_id=chat.project_id,
                    project_only=bool(project and project.memory_mode == "project_only"),
                )
            except Exception:  # noqa: BLE001
                # Long-term memory is an enhancement: an unavailable embedding
                # model must never prevent the current conversation from working.
                memory_context = ""
                events.put(("status", {"message": "Không thể đọc Memory, vẫn tiếp tục trả lời..."}))
            knowledge_context = ""
            if chat.project_id is None or chat.collection_id:
                try:
                    events.put(("status", {"message": "Đang tìm trong Thư viện..."}))
                    retrieved = app_services.knowledge.search(content, project_id=chat.project_id, collection_id=chat.collection_id)
                    knowledge_context = "" if retrieved == NO_DOCUMENTS_RESULT else retrieved
                except Exception:  # noqa: BLE001
                    # Retrieval is a priority, not a single point of failure for chat.
                    events.put(("status", {"message": "Không thể tìm Thư viện RAG, vẫn tiếp tục trả lời..."}))
            try:
                app_services.personalization.observe_user_message(content)
                personalization_context = app_services.personalization.context()
            except Exception:  # noqa: BLE001
                personalization_context = ""
            plugin_tools = connected_read_tools(app_services.workspace.list_plugins())
            agent = make_agent(
                app_services,
                chat,
                memory_context,
                knowledge_context,
                personalization_context=personalization_context,
                plugin_tools=plugin_tools,
                history=full_history,
            )
            initial_history_length = len(agent.history)
            result = agent.run(content, attachments, on_step=lambda item: events.put((item["type"], item)))
            if result.content_blocks:
                agent.history[-1]["content_blocks"] = result.content_blocks
            if agent.history and agent.history[-1].get("role") == "assistant":
                visible_content, sources = detach_response_sources(agent.history[-1].get("content", ""))
                agent.history[-1]["content"] = visible_content
                if sources:
                    agent.history[-1]["sources"] = sources
            saved_history = persisted_history(full_history, agent.history, initial_history_length)
            turn_created_at = datetime.now(UTC).isoformat()
            for item in saved_history[len(full_history):]:
                item.setdefault("created_at", turn_created_at)
            app_services.chats.replace_history(chat_id, saved_history)
            BackgroundJobRepository(app_services.chats.database).enqueue("memory_index", {"chat_id": chat_id})
            # Agent providers currently expose a completed normalized response.
            # SSE still keeps the UI responsive by streaming tool progress, then the final content.
            completed_message = next(
                (item for item in reversed(saved_history) if item["role"] == "assistant"),
                {"role": "assistant", "content": result.text, "content_blocks": result.content_blocks},
            )
            events.put(("message", message_json(completed_message)))
            events.put(("done", {}))
        except Exception as exc:  # noqa: BLE001
            events.put(("error", {"message": model_error_message(chat, exc)}))
        finally:
            current_user_id.reset(user_token)
            events.put(("close", {}))

    Thread(target=run, daemon=True).start()
    while True:
        try:
            event, payload = events.get(timeout=15)
        except Empty:
            yield ": keepalive\n\n"
            continue
        if event == "close":
            return
        yield sse(event, payload)


@app.post("/api/chats/{chat_id}/stream", tags=["Chat streaming"])
def chat_stream(chat_id: str, payload: ChatRequest) -> StreamingResponse:
    try:
        attachments = services().media.for_prompt(payload.attachment_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StreamingResponse(
        stream_chat(chat_id, payload.content, attachments),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Swagger uses these responses consistently, while the route implementations
# remain focused on their actual application behavior.
ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    404: {
        "description": "Không tìm thấy tài nguyên được yêu cầu.",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiError"},
                "example": {"detail": "Không tìm thấy chat."},
            }
        },
    },
    422: {
        "description": "Dữ liệu gửi lên không hợp lệ hoặc không thỏa điều kiện nghiệp vụ.",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiError"},
                "example": {"detail": "Model không được hỗ trợ."},
            }
        },
    },
    500: {
        "description": "Lỗi máy chủ không mong đợi. Kiểm tra log FastAPI để biết chi tiết.",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiError"},
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
    ("get", "/api/chats/{chat_id}"): (404, 500),
    ("get", "/api/chats/{chat_id}/messages"): (404, 500),
    ("patch", "/api/chats/{chat_id}"): (404, 422, 500),
    ("delete", "/api/chats/{chat_id}"): (404, 500),
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
