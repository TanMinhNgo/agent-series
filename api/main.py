"""Expose the existing agent services through JSON and server-sent events."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_core.agent import Agent
from agent_core.config import Settings, load_settings
from agent_core.knowledge import KnowledgeService, build_knowledge_tool
from agent_core.media import MediaService
from agent_core.memory import MemoryService
from agent_core.prompts import DEFAULT_SYSTEM_PROMPT
from agent_core.providers import build_client
from agent_core.storage import Chat, ChatRepository, ChatShare, Database, Document, MediaAttachment, MediaRepository, Plugin, Project, Schedule, WorkspaceRepository
from agent_core.tools import build_default_registry


@dataclass
class Services:
    settings: Settings
    chats: ChatRepository
    knowledge: KnowledgeService
    media: MediaService
    memory: MemoryService
    workspace: WorkspaceRepository


class CreateChatRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    context_source_chat_id: str | None = Field(default=None, alias="contextSourceChatId")

    model_config = {"populate_by_name": True}


class UpdateChatRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    pinned: bool | None = None
    archived: bool | None = None


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    attachment_ids: list[str] = Field(default_factory=list, alias="attachmentIds")

    model_config = {"populate_by_name": True}


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    status: str = Field(default="active", max_length=24)


class ScheduleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime
    ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    project_id: str | None = None


class PluginRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10_000)
    enabled: bool = False
    config: dict[str, Any] | None = None


class PluginUpdateRequest(BaseModel):
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
    }


def share_json(share: ChatShare) -> dict[str, Any]:
    return {"token": share.token, "title": share.title, "provider": share.provider, "model": share.model, "messages": share.messages, "createdAt": share.created_at.isoformat(), "updatedAt": share.updated_at.isoformat()}


def document_json(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "name": document.original_name,
        "status": document.status,
        "pageCount": document.page_count,
        "error": document.error,
    }


def media_json(media: MediaAttachment) -> dict[str, Any]:
    return {"id": media.id, "name": media.original_name, "mimeType": media.mime_type, "url": f"/uploads/{media.stored_name}", "sizeBytes": media.size_bytes}


def message_json(message: dict[str, Any]) -> dict[str, Any]:
    result = dict(message)
    if "content_blocks" in result:
        result["contentBlocks"] = result.pop("content_blocks") or []
    return result


def project_json(item: Project) -> dict[str, Any]:
    return {"id": item.id, "name": item.name, "description": item.description, "status": item.status, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def schedule_json(item: Schedule) -> dict[str, Any]:
    return {"id": item.id, "title": item.title, "startsAt": item.starts_at.isoformat(), "endsAt": item.ends_at.isoformat() if item.ends_at else None, "notes": item.notes, "projectId": item.project_id, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


def plugin_json(item: Plugin) -> dict[str, Any]:
    return {"id": item.id, "slug": item.slug, "name": item.name, "description": item.description, "enabled": item.enabled, "config": item.config, "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}


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


def make_agent(app_services: Services, chat: Chat, memory_context: str = "") -> Agent:
    settings = app_services.settings.with_provider_model(chat.provider, chat.model)
    source_context = ""
    if chat.context_source_chat_id:
        source = app_services.chats.history(chat.context_source_chat_id)
        turns = [item for item in source if item["role"] in {"user", "assistant"}][-10:]
        if turns:
            transcript = "\n".join(f"{item['role']}: {item['content']}" for item in turns)
            source_context = f"\n\nNgữ cảnh kế thừa từ cuộc trò chuyện trước (ẩn với người dùng):\n{transcript}"
    agent = Agent(
        build_client(settings),
        build_default_registry(build_knowledge_tool(app_services.knowledge)),
        system_prompt=DEFAULT_SYSTEM_PROMPT + source_context + (f"\n\n{memory_context}" if memory_context else ""),
        max_steps=settings.max_steps,
    )
    agent.history = app_services.media.hydrate_history(app_services.chats.history(chat.id))
    return agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    database = Database(settings.database_url)
    media = MediaService(MediaRepository(database), settings.media_dir)
    app.state.services = Services(
        settings=settings,
        chats=ChatRepository(database),
        knowledge=KnowledgeService(database, Path(settings.knowledge_dir), settings.embedding_model),
        media=media,
        memory=MemoryService(database, settings.embedding_model),
        workspace=WorkspaceRepository(database),
    )
    yield


app = FastAPI(title="Agent Series API", version="1.0.0", lifespan=lifespan)
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


def services() -> Services:
    return app.state.services


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict[str, Any]:
    settings = services().settings
    return {
        "providers": {key: list(value) for key, value in settings.configured_provider_models().items()},
        "defaultProvider": settings.provider,
        "defaultModel": settings.active_model,
    }


@app.get("/api/chats")
def list_chats() -> list[dict[str, Any]]:
    return [chat_json(chat) for chat in services().chats.list()]


@app.post("/api/chats", status_code=201)
def create_chat(payload: CreateChatRequest) -> dict[str, Any]:
    settings = services().settings
    provider, model = payload.provider or settings.provider, payload.model or settings.active_model
    try:
        selected = settings.with_provider_model(provider, model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    source_id = payload.context_source_chat_id
    if source_id and services().chats.get(source_id) is None:
        raise HTTPException(status_code=422, detail="Không tìm thấy chat nguồn để kế thừa context.")
    return chat_json(services().chats.create(selected.provider, selected.active_model, source_id))


@app.get("/api/memories")
def memories(query: str = "") -> list[dict[str, Any]]:
    return services().memory.list(query)


@app.delete("/api/memories/{memory_id}", status_code=204)
def forget_memory(memory_id: str) -> None:
    if not services().memory.forget(memory_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy memory.")


@app.delete("/api/memories", status_code=204)
def forget_all_memories() -> None:
    services().memory.forget_all()


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str) -> dict[str, Any]:
    chat = services().chats.get(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return chat_json(chat)


@app.get("/api/chats/{chat_id}/messages")
def messages(chat_id: str) -> list[dict[str, Any]]:
    if services().chats.get(chat_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return [message_json(item) for item in services().chats.history(chat_id) if item["role"] in {"user", "assistant"}]


@app.patch("/api/chats/{chat_id}")
def update_chat(chat_id: str, payload: UpdateChatRequest) -> dict[str, Any]:
    try:
        chat = services().chats.get(chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
        provider, model = payload.provider or chat.provider, payload.model or chat.model
        services().settings.with_provider_model(provider, model)
        chat = services().chats.update(chat_id, provider=provider, model=model, title=payload.title, pinned=payload.pinned, archived=payload.archived)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return chat_json(chat)


@app.delete("/api/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: str) -> None:
    if not services().chats.delete(chat_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")


@app.post("/api/chats/{chat_id}/share")
def share_chat(chat_id: str) -> dict[str, Any]:
    share = services().chats.create_or_update_share(chat_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chat.")
    return share_json(share)


@app.get("/api/public/shares/{token}")
def public_share(token: str) -> dict[str, Any]:
    share = services().chats.get_share(token)
    if share is None:
        raise HTTPException(status_code=404, detail="Liên kết chia sẻ không tồn tại hoặc đã bị thu hồi.")
    return share_json(share)


@app.get("/api/documents")
def documents() -> list[dict[str, Any]]:
    return [document_json(item) for item in services().knowledge.list_documents()]


@app.post("/api/documents", status_code=201)
async def upload_documents(files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    uploaded: list[Document] = []
    try:
        for file in files:
            document, created = services().knowledge.upload(file.filename or "document.pdf", await file.read())
            uploaded.append(services().knowledge.index(document.id) if created or document.status != "ready" else document)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [document_json(item) for item in uploaded]


@app.post("/api/media", status_code=201)
async def upload_media(files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    try:
        uploaded = [services().media.upload(file.filename or "image", file.content_type or "", await file.read()) for file in files]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [media_json(item) for item in uploaded]


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    return [project_json(item) for item in services().workspace.list(Project)]


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectRequest) -> dict[str, Any]:
    return project_json(services().workspace.create(Project, **payload.model_dump()))


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectRequest) -> dict[str, Any]:
    item = services().workspace.update(Project, project_id, **payload.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
    return project_json(item)


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    if not services().workspace.delete(Project, project_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")


@app.get("/api/schedules")
def list_schedules() -> list[dict[str, Any]]:
    return [schedule_json(item) for item in services().workspace.list(Schedule)]


@app.post("/api/schedules", status_code=201)
def create_schedule(payload: ScheduleRequest) -> dict[str, Any]:
    if payload.ends_at and payload.ends_at < payload.starts_at:
        raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
    return schedule_json(services().workspace.create(Schedule, **payload.model_dump()))


@app.patch("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: str, payload: ScheduleRequest) -> dict[str, Any]:
    if payload.ends_at and payload.ends_at < payload.starts_at:
        raise HTTPException(status_code=422, detail="Thời điểm kết thúc phải sau thời điểm bắt đầu.")
    item = services().workspace.update(Schedule, schedule_id, **payload.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình.")
    return schedule_json(item)


@app.delete("/api/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str) -> None:
    if not services().workspace.delete(Schedule, schedule_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch trình.")


@app.get("/api/plugins")
def list_plugins() -> list[dict[str, Any]]:
    return [plugin_json(item) for item in services().workspace.list(Plugin)]


@app.post("/api/plugins", status_code=201)
def create_plugin(payload: PluginRequest) -> dict[str, Any]:
    return plugin_json(services().workspace.create(Plugin, **payload.model_dump()))


@app.patch("/api/plugins/{plugin_id}")
def update_plugin(plugin_id: str, payload: PluginUpdateRequest) -> dict[str, Any]:
    item = services().workspace.update(Plugin, plugin_id, **payload.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy plugin.")
    return plugin_json(item)


@app.delete("/api/plugins/{plugin_id}", status_code=204)
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
        try:
            events.put(("status", {"message": "Agent đang suy nghĩ..."}))
            try:
                memory_context = app_services.memory.recall(content)
            except Exception:  # noqa: BLE001
                # Long-term memory is an enhancement: an unavailable embedding
                # model must never prevent the current conversation from working.
                memory_context = ""
                events.put(("status", {"message": "Không thể đọc Thư viện, vẫn tiếp tục trả lời..."}))
            agent = make_agent(app_services, chat, memory_context)
            result = agent.run(content, attachments, on_step=lambda item: events.put((item["type"], item)))
            if result.content_blocks:
                agent.history[-1]["content_blocks"] = result.content_blocks
            app_services.chats.replace_history(chat_id, agent.history)
            try:
                app_services.memory.index_history(chat_id, agent.history)
            except Exception:  # noqa: BLE001
                # The message was already saved. Report the non-blocking memory
                # issue to the UI, rather than turning a successful answer into an error.
                events.put(("status", {"message": "Chưa thể cập nhật Thư viện cho tin nhắn này."}))
            # Agent providers currently expose a completed normalized response.
            # SSE still keeps the UI responsive by streaming tool progress, then the final content.
            events.put(("message", {"role": "assistant", "content": result.text, "contentBlocks": result.content_blocks}))
            events.put(("done", {}))
        except Exception as exc:  # noqa: BLE001
            events.put(("error", {"message": model_error_message(chat, exc)}))
        finally:
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


@app.post("/api/chats/{chat_id}/stream")
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
