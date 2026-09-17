"""Context assembly for chat generation."""

from dataclasses import dataclass, field
from queue import Queue
from typing import Any, Callable


@dataclass
class ChatGenerationContext:
    history: list[dict[str, Any]]
    memory: str = ""
    knowledge: str = ""
    personalization: str = ""
    web: str = ""
    web_sources: list[dict[str, str]] = field(default_factory=list)
    retrieval_traces: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ContextDependencies:
    project_model: Any
    no_documents_result: str
    ollama_rag_max_distance: float
    should_search_web: Callable[[str], bool]
    web_context_from_result: Callable[[str], tuple[str, list[dict[str, str]]]]


def load_generation_context(deps: ContextDependencies, app_services: Any, chat: Any, content: str, chat_id: str, history: list[dict[str, Any]], events: Queue, research_web: bool = False) -> ChatGenerationContext:
    context = ChatGenerationContext(history=history)
    context.memory = load_memory_context(deps, app_services, chat, content, chat_id, events)
    context.knowledge, context.retrieval_traces = load_knowledge_context(deps, app_services, chat, content, events)
    context.web, context.web_sources = load_web_context(deps, app_services, chat, content, events, research_web)
    context.personalization = load_personalization_context(app_services, chat, content)
    return context


def load_memory_context(deps: ContextDependencies, app_services: Any, chat: Any, content: str, chat_id: str, events: Queue) -> str:
    if chat.provider == "ollama":
        return ""
    try:
        project = app_services.workspace.get(deps.project_model, chat.project_id) if chat.project_id else None
        return app_services.memory.recall(content, chat_id, chat.context_source_chat_id, project_id=chat.project_id, project_only=bool(project and project.memory_mode == "project_only"))
    except Exception:
        events.put(("status", {"message": "Không thể đọc Memory, vẫn tiếp tục trả lời..."}))
        return ""


def load_knowledge_context(deps: ContextDependencies, app_services: Any, chat: Any, content: str, events: Queue) -> tuple[str, list[dict[str, Any]]]:
    if chat.project_id is not None and not chat.collection_id:
        return "", []
    try:
        events.put(("status", {"message": "Đang tìm trong Thư viện..."}))
        options = {"max_distance": deps.ollama_rag_max_distance} if chat.provider == "ollama" else {}
        traced_search = getattr(app_services.knowledge, "search_with_trace", None)
        if traced_search is None:
            result, traces = app_services.knowledge.search(content, project_id=chat.project_id, collection_id=chat.collection_id, **options), []
        else:
            result, traces = traced_search(content, project_id=chat.project_id, collection_id=chat.collection_id, **options)
        return ("", []) if result == deps.no_documents_result else (result, traces)
    except Exception:
        events.put(("status", {"message": "Không thể tìm Thư viện RAG, vẫn tiếp tục trả lời..."}))
        return "", []


def load_web_context(deps: ContextDependencies, app_services: Any, chat: Any, content: str, events: Queue, research_web: bool = False) -> tuple[str, list[dict[str, str]]]:
    mode = getattr(chat, "mode", "standard")
    if chat.provider == "ollama" or mode == "image" or (mode in {"plan", "research"} and not research_web):
        return "", []
    if mode not in {"plan", "research"} and not deps.should_search_web(content):
        return "", []
    try:
        events.put(("status", {"message": "Đang tìm nguồn web mới..."}))
        context, sources = deps.web_context_from_result(app_services.web_search.search(content))
        if not context:
            events.put(("status", {"message": "Không thể tìm web, đang trả lời theo kiến thức sẵn có..."}))
        return context, sources
    except Exception:
        events.put(("status", {"message": "Không thể tìm web, đang trả lời theo kiến thức sẵn có..."}))
        return "", []


def load_personalization_context(app_services: Any, chat: Any, content: str) -> str:
    if chat.provider == "ollama":
        return ""
    try:
        app_services.personalization.observe_user_message(content)
        return app_services.personalization.context()
    except Exception:
        return ""
