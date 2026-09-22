"""Agent construction for chat turns."""

import json
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from agent_core.ai.agent import Agent
from agent_core.ai.history import recent_chat_history, ollama_recent_history
from agent_core.content.contracts import library_asset_json
from agent_core.content.indexing import enqueue_artifact_index
from agent_core.jobs.contracts import ScheduleProposalPayload, VIETNAM_TIMEZONE
from agent_core.ai.prompts import DEFAULT_SYSTEM_PROMPT, OLLAMA_SYSTEM_PROMPT
from agent_core.ai.providers import build_client
from agent_core.content.artifacts import PREVIEW_LIMIT, ArtifactEditContext, build_artifact_tool
from agent_core.integrations.web_search import build_web_search_tool
from agent_core.knowledge.rag import build_knowledge_tool
from agent_core.persistence.store import Chat, Project, current_user_id, current_workspace_id
from agent_core.runtime.services import Services
from agent_core.tools import ToolRegistry, ToolSpec, build_default_registry


@dataclass(frozen=True)
class AgentDependencies:
    selected_settings: Callable[..., Any]
    enqueue_artifact_index: Callable[[Any, Services], None]
    library_asset_json: Callable[[Any], dict[str, Any]]
    recent_chat_history: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    ollama_recent_history: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    schedule_payload: Any
    vietnam_timezone: str
    build_client: Callable[[Any], Any]
    build_knowledge_tool: Callable[..., Any]
    build_default_registry: Callable[..., Any]


def agent_system_prompt(chat: Chat, project: Project | None, web_tool: ToolSpec | None, schedule_tool: ToolSpec | None, source_context: str, artifact_edit_context: str, knowledge_context: str, web_context: str, personalization_context: str, memory_context: str) -> str:
    prompt = OLLAMA_SYSTEM_PROMPT if chat.provider == "ollama" else DEFAULT_SYSTEM_PROMPT
    prompt += {
        "plan": "\n\nChế độ Lập kế hoạch: chỉ lập kế hoạch, không thực thi hay tạo file/lịch. Luôn nêu mục tiêu, giả định, các bước, tiêu chí hoàn thành và rủi ro.",
        "deep": "\n\nChế độ Suy nghĩ sâu: phân tích kỹ, nêu phương án, trade-off, khuyến nghị và rủi ro. Không tiết lộ suy luận nội bộ từng bước.",
        "research": "\n\nChế độ Nghiên cứu: ưu tiên tài liệu đã chọn và nguồn có thể kiểm chứng. Kết luận phải nêu citation, mức độ tin cậy và dữ liệu còn thiếu.",
    }.get(getattr(chat, "mode", "standard"), "")
    if project and project.instructions:
        prompt += f"\n\nHướng dẫn dự án:\n{project.instructions}"
    if chat.collection_id or chat.project_id is None:
        prompt += "\n\nKhi dùng knowledge base, giữ nguyên Markdown link của nguồn và nêu vị trí nguồn để người dùng mở đúng tài liệu."
    if web_tool is not None:
        prompt += "\n\nKhi Thư viện không có hoặc chưa đủ dữ liệu, dùng `search_web`. Chỉ dùng URL do tool trả về; không tự tạo link hoặc nguồn. Không cần tạo mục Nguồn ở cuối câu trả lời vì hệ thống tự hiển thị trong menu trích nguồn."
    if schedule_tool is not None:
        prompt += "\n\nLịch trình: chỉ gọi `propose_schedule` khi người dùng yêu cầu rõ tạo lịch/nhắc việc VÀ đã có cả ngày lẫn giờ. Nếu thiếu một trong hai, hãy hỏi lại; không đoán."
    prompt += source_context + artifact_edit_context
    if knowledge_context:
        prompt += f"\n\nNgữ cảnh Thư viện RAG đã được truy xuất tự động trước câu hỏi này:\n{knowledge_context}"
    if web_context:
        prompt += f"\n\nNguồn web mới đã được tìm tự động cho câu hỏi này:\n{web_context}"
    if personalization_context:
        prompt += f"\n\n{personalization_context}"
    if memory_context:
        prompt += f"\n\n{memory_context}"
    return prompt


def build_agent(deps: AgentDependencies, app_services: Services, chat: Chat, memory_context: str = "", knowledge_context: str = "", personalization_context: str = "", plugin_tools: list[ToolSpec] | None = None, history: list[dict[str, Any]] | None = None, schedule_proposals: list[dict[str, Any]] | None = None, allow_schedule_proposals: bool = True, artifact_edit: ArtifactEditContext | None = None, web_context: str = "", allow_web: bool = True) -> Agent:
    project = validate_agent_context(app_services, chat)
    settings = deps.selected_settings(chat.provider, chat.model, chat.user_id)
    source_context = ""
    if chat.context_source_chat_id:
        turns = [item for item in deps.recent_chat_history(app_services.chats.history(chat.context_source_chat_id)) if item["role"] in {"user", "assistant"}]
        if turns:
            source_context = "\n\nNgữ cảnh kế thừa từ cuộc trò chuyện trước (ẩn với người dùng):\n" + "\n".join(f"{item['role']}: {item['content']}" for item in turns)
    def create_project_export(name: str, format: str, content: str) -> str:
        asset = app_services.library.create_export(name, format, content, project_id=chat.project_id)
        deps.enqueue_artifact_index(asset, app_services)
        return json.dumps(deps.library_asset_json(asset), ensure_ascii=False)
    export_tool = ToolSpec(name="create_file", description="Tạo file cho người dùng và lưu vào Thư viện.", parameters={"type": "object", "properties": {"name": {"type": "string"}, "format": {"type": "string"}, "content": {"type": "string"}}, "required": ["name", "format", "content"]}, func=create_project_export)
    def create_web_bundle(name: str, html: str, css: str, js: str, include_zip: bool = False) -> str:
        assets = app_services.library.create_web_bundle(name, html, css, js, include_zip, chat.project_id)
        for asset in assets:
            deps.enqueue_artifact_index(asset, app_services)
        return json.dumps({"items": [deps.library_asset_json(asset) for asset in assets]}, ensure_ascii=False)
    web_bundle_tool = ToolSpec(name="create_web_bundle", description="Tạo website gồm index.html, style.css và app.js.", parameters={"type": "object", "properties": {"name": {"type": "string"}, "html": {"type": "string"}, "css": {"type": "string"}, "js": {"type": "string"}, "include_zip": {"type": "boolean"}}, "required": ["name", "html", "css", "js"]}, func=create_web_bundle)
    version_tool = None
    artifact_edit_context = ""
    if artifact_edit is not None:
        created = False
        def create_artifact_version(content: str) -> str:
            nonlocal created
            if created:
                raise ValueError("Mỗi lần sửa chỉ được tạo một version mới.")
            if len(content) > PREVIEW_LIMIT:
                raise ValueError("Nội dung mới vượt quá 30.000 ký tự nên chưa thể lưu bằng AI.")
            asset = app_services.library.create_version(artifact_edit.asset_id, artifact_edit.name, artifact_edit.mime_type, content.encode("utf-8"))
            created = True
            deps.enqueue_artifact_index(asset, app_services)
            return json.dumps(deps.library_asset_json(asset), ensure_ascii=False)
        version_tool = ToolSpec(name="create_artifact_version", description="Lưu nội dung đã chỉnh sửa thành version mới.", parameters={"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}, func=create_artifact_version)
        artifact_edit_context = f"\n\nBạn đang sửa file `{artifact_edit.name}` version {artifact_edit.version}.\n<artifact-content>\n{artifact_edit.content}\n</artifact-content>"
    web_search = getattr(app_services, "web_search", None)
    web_tool = build_web_search_tool(web_search) if web_search is not None else None
    if getattr(chat, "mode", "standard") in {"plan", "research"} and not allow_web:
        web_tool = None
    knowledge_tool = deps.build_knowledge_tool(app_services.knowledge, chat.project_id, chat.collection_id)
    schedule_tool = None
    if chat.provider != "ollama" and allow_schedule_proposals and schedule_proposals is not None:
        def propose_schedule(title: str, prompt: str, startsAt: str, recurrence: str = "once", timezone: str = deps.vietnam_timezone) -> str:
            proposal = deps.schedule_payload.model_validate({"title": title, "prompt": prompt, "startsAt": startsAt, "recurrence": recurrence, "timezone": timezone})
            block = {"type": "schedule-proposal", "config": {"proposalId": str(uuid4()), "status": "pending", "title": proposal.title, "prompt": proposal.prompt, "startsAt": proposal.starts_at.isoformat(), "recurrence": proposal.recurrence, "timezone": proposal.timezone, "projectId": chat.project_id}}
            schedule_proposals.append(block)
            return json.dumps({"status": "pending", "message": "Đã tạo thẻ xác nhận lịch trình."}, ensure_ascii=False)
        schedule_tool = ToolSpec(name="propose_schedule", description="Tạo thẻ xác nhận lịch trình, không tự lưu lịch.", parameters={"type": "object", "properties": {"title": {"type": "string"}, "prompt": {"type": "string"}, "startsAt": {"type": "string"}}, "required": ["title", "prompt", "startsAt"]}, func=propose_schedule)
    if chat.provider == "ollama":
        registry = ToolRegistry([])
        web_tool = None
    elif getattr(chat, "mode", "standard") == "plan":
        read_tools = ([build_artifact_tool(app_services.artifacts, chat.project_id)] if chat.project_id else []) + [*(plugin_tools or [])]
        if web_tool is not None:
            read_tools.append(web_tool)
        registry = deps.build_default_registry(knowledge_tool, read_tools)
        schedule_tool = None
    else:
        file_tool = version_tool or export_tool
        extra_tools = ([build_artifact_tool(app_services.artifacts, chat.project_id)] if chat.project_id else []) + [file_tool] + ([] if version_tool is not None else [web_bundle_tool]) + [*(plugin_tools or [])]
        if schedule_tool is not None:
            extra_tools.append(schedule_tool)
        if web_tool is not None:
            extra_tools.append(web_tool)
        registry = deps.build_default_registry(knowledge_tool, extra_tools)
    agent = Agent(deps.build_client(settings), registry, system_prompt=agent_system_prompt(chat, project, web_tool, schedule_tool, source_context, artifact_edit_context, knowledge_context, web_context, personalization_context, memory_context), max_steps=settings.max_steps)
    stored_history = history if history is not None else app_services.chats.history(chat.id)
    prompt_history = deps.ollama_recent_history(stored_history) if chat.provider == "ollama" else deps.recent_chat_history(stored_history)
    agent.history = app_services.media.hydrate_history([dict(item) for item in prompt_history])
    return agent


def selected_settings(app_services: Services, provider: str, model: str, user_id: str | None):
    if provider == "ollama":
        app_services.ollama.require_model(model)
        return app_services.settings.with_provider_model(provider, model)
    if model not in app_services.model_registry.active().get(provider, ()):
        raise ValueError("Model đang tắt hoặc chưa được hệ thống cho phép.")
    return app_services.settings.with_provider_model(provider, model, app_services.credentials.api_key(user_id, provider))


def validate_agent_context(app_services: Services, chat: Chat) -> Project | None:
    actor = current_user_id.get()
    workspace_id = current_workspace_id.get()
    chat_workspace = getattr(chat, "workspace_id", None)
    if chat_workspace != workspace_id:
        raise ValueError("Workspace của chat không khớp ngữ cảnh thực thi.")
    if workspace_id:
        member = app_services.workspace.membership(workspace_id, actor) if actor else None
        if member is None or member.role not in {"owner", "editor"}:
            raise ValueError("Bạn không có quyền chạy agent trong workspace này.")
    elif actor != chat.user_id:
        raise ValueError("Chủ chat không khớp ngữ cảnh thực thi.")
    project = app_services.workspace.get(Project, chat.project_id) if chat.project_id else None
    if chat.project_id and (project is None or project.workspace_id != chat_workspace or (not chat_workspace and project.user_id != chat.user_id)):
        raise ValueError("Project không thuộc ngữ cảnh thực thi của chat.")
    return project


def make_agent(app_services: Services, chat: Chat, memory_context: str = "", knowledge_context: str = "", personalization_context: str = "", plugin_tools=None, history=None, schedule_proposals=None, allow_schedule_proposals: bool = True, artifact_edit=None, web_context: str = "", allow_web: bool = True) -> Agent:
    deps = AgentDependencies(
        lambda provider, model, user_id: selected_settings(app_services, provider, model, user_id),
        enqueue_artifact_index, library_asset_json, recent_chat_history, ollama_recent_history,
        ScheduleProposalPayload, VIETNAM_TIMEZONE, build_client, build_knowledge_tool, build_default_registry,
    )
    return build_agent(deps, app_services, chat, memory_context, knowledge_context, personalization_context, plugin_tools, history, schedule_proposals, allow_schedule_proposals, artifact_edit, web_context, allow_web)
