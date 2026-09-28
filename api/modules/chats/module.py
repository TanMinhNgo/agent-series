"""Chat module: wires the chat runtime (context, agent, persistence, SSE stream) to app services."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from queue import Queue
from threading import Event, Lock
from typing import Any, Callable

from fastapi import HTTPException

from agent_core.ai.agent import AgentCancelled
from agent_core.ai.history import created_artifact_ids, ollama_recent_history, persisted_history, recent_chat_history
from agent_core.ai.images import ImageGenerationError
from agent_core.ai.providers import build_client
from agent_core.content.artifacts import ArtifactEditContext
from agent_core.content.indexing import enqueue_artifact_index
from agent_core.integrations.web_search import sources_from_web_steps
from agent_core.jobs.contracts import VIETNAM_TIMEZONE
from agent_core.knowledge.rag import NO_DOCUMENTS_RESULT, build_knowledge_tool
from agent_core.persistence.store import BackgroundJobRepository, Chat, Project, current_user_id, current_workspace_id
from agent_core.runtime.agent import AgentDependencies, build_agent, selected_settings
from agent_core.tools import build_default_registry
from api.contracts.requests import ScheduleProposalPayload
from api.modules.chats.controller import ChatStreamController
from api.modules.chats.image_service import run_image_turn
from api.modules.chats.runtime.context import ContextDependencies, load_generation_context
from api.modules.chats.runtime.generation import is_ollama_tool_echo, model_error_message, small_talk_response, should_search_web, web_context_from_result
from api.modules.chats.runtime.persistence import PersistenceDependencies, persist_generation, persist_static_response
from api.modules.chats.runtime.stream import StreamDependencies, stream_chat
from api.modules.chats.runtime.tools import project_connector_tools
from api.modules.chats.runtime.turn import run_agent_turn
from api.modules.common.serializers import library_asset_json

OLLAMA_RAG_MAX_DISTANCE = 0.45
SOURCE_LINK_PATTERN = re.compile(r"\[([^\[\]\n]+)\]\((/api/documents/[^)#]+(?:#[^)]+)?)\)")


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


def sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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


class ChatModule:
    """Chat runtime bound to the app's service container.

    Methods look each other up through ``self`` so tests can replace one step
    (``services``, ``make_agent``) on the instance without rebuilding the rest.
    """

    def __init__(self, services: Callable[[], Any], chat_not_found_error: str, not_found_marker: str):
        self.services = services
        self.runs = ChatRunRegistry()
        self.controller = ChatStreamController(lambda: self.services(), lambda *args: self.stream_chat(*args), self.runs, chat_not_found_error, not_found_marker)

    def message_json(self, message: dict[str, Any]) -> dict[str, Any]:
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
            assets = [self.services().library.get(asset_id) for asset_id in result.pop("generated_asset_ids")]
            result["generatedAssets"] = [library_asset_json(asset) for asset in assets if asset is not None]
        return result

    def make_agent(self, app_services, chat, memory_context="", knowledge_context="", personalization_context="", plugin_tools=None, history=None, schedule_proposals=None, allow_schedule_proposals=True, artifact_edit=None, web_context="", allow_web=True):
        deps = AgentDependencies(
            lambda provider, model, user_id: selected_settings(app_services, provider, model, user_id),
            lambda asset, services: enqueue_artifact_index(asset, services),
            library_asset_json, recent_chat_history, ollama_recent_history, ScheduleProposalPayload,
            VIETNAM_TIMEZONE, build_client, build_knowledge_tool, build_default_registry,
        )
        try:
            return build_agent(deps, app_services, chat, memory_context, knowledge_context, personalization_context, plugin_tools, history, schedule_proposals, allow_schedule_proposals, artifact_edit, web_context, allow_web)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def load_generation_context(self, app_services, chat, content, chat_id, history, events, research_web=False):
        deps = ContextDependencies(Project, NO_DOCUMENTS_RESULT, OLLAMA_RAG_MAX_DISTANCE, should_search_web, web_context_from_result)
        return load_generation_context(deps, app_services, chat, content, chat_id, history, events, research_web)

    def _persistence_dependencies(self) -> PersistenceDependencies:
        return PersistenceDependencies(
            detach_response_sources, sources_from_web_steps, is_ollama_tool_echo, persisted_history,
            created_artifact_ids, library_asset_json, self.message_json, BackgroundJobRepository,
        )

    def persist_generation(self, app_services, chat, chat_id, full_history, agent, initial_history_length, result, schedule_proposals, web_sources, retrieval_traces, events):
        return persist_generation(self._persistence_dependencies(), app_services, chat, chat_id, full_history, agent, initial_history_length, result, schedule_proposals, web_sources, retrieval_traces, events)

    def persist_static_response(self, app_services, chat_id, full_history, content, response, events):
        return persist_static_response(self._persistence_dependencies(), app_services, chat_id, full_history, content, response, events)

    def run_agent_turn(self, app_services, chat: Chat, chat_id: str, content: str, attachments: list[dict], artifact_edit: ArtifactEditContext | None, cancel_event: Event, full_history: list[dict[str, Any]], events: Queue, research_web: bool = False) -> None:
        return run_agent_turn(
            self.load_generation_context, self.make_agent, project_connector_tools, self.persist_generation, AgentCancelled,
            app_services, chat, chat_id, content, attachments, artifact_edit, cancel_event, full_history, events, research_web,
        )

    def stream_chat(self, chat_id: str, content: str, attachments: list[dict], artifact_edit: ArtifactEditContext | None = None, cancel_event: Event | None = None, run_id: str | None = None, research_web: bool = False) -> Iterator[str]:
        deps = StreamDependencies(
            services=self.services, sse=sse, chat_runs=self.runs, run_image_turn=run_image_turn,
            message_json=self.message_json, small_talk_response=small_talk_response,
            persist_static_response=self.persist_static_response, run_agent_turn=self.run_agent_turn,
            model_error_message=model_error_message, agent_cancelled=AgentCancelled,
            image_generation_error=ImageGenerationError, current_user_id=current_user_id,
            current_workspace_id=current_workspace_id,
        )
        return stream_chat(deps, chat_id, content, attachments, artifact_edit, cancel_event, run_id, research_web)
