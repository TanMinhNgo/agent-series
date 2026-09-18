"""Persistence of generated chat turns and evidence."""

from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Queue
from typing import Any, Callable


@dataclass(frozen=True)
class PersistenceDependencies:
    detach_response_sources: Callable[..., tuple[str, list[dict[str, str]]]]
    sources_from_web_steps: Callable[[Any], list[dict[str, str]]]
    is_ollama_tool_echo: Callable[[str], bool]
    persisted_history: Callable[..., list[dict[str, Any]]]
    created_artifact_ids: Callable[[list[Any]], list[str]]
    library_asset_json: Callable[[Any], dict[str, Any]]
    message_json: Callable[[dict[str, Any]], dict[str, Any]]
    background_job_repository: Any


def prepare_generation_history(deps: PersistenceDependencies, chat: Any, agent: Any, result: Any, schedule_proposals: list[dict[str, Any]], web_sources: list[dict[str, str]]) -> None:
    if schedule_proposals:
        result.content_blocks = [*result.content_blocks, *schedule_proposals]
    if result.content_blocks:
        agent.history[-1]["content_blocks"] = result.content_blocks
    if not agent.history or agent.history[-1].get("role") != "assistant":
        return
    visible_content, sources = deps.detach_response_sources(agent.history[-1].get("content", ""), [*deps.sources_from_web_steps(getattr(result, "steps", [])), *web_sources])
    if chat.provider == "ollama" and deps.is_ollama_tool_echo(visible_content):
        visible_content = "Mình chưa thể thực hiện thao tác đó trong chế độ Ollama local. Bạn hãy diễn đạt lại yêu cầu bằng một câu hỏi thông thường nhé."
    agent.history[-1]["content"] = visible_content
    if sources:
        agent.history[-1]["sources"] = sources


def attach_generation_evidence(deps: PersistenceDependencies, app_services: Any, chat: Any, chat_id: str, new_turn: list[dict[str, Any]], result: Any, retrieval_traces: list[dict[str, Any]]) -> None:
    user_message = next((item for item in new_turn if item["role"] == "user"), None)
    assistant_message = next((item for item in reversed(new_turn) if item["role"] == "assistant"), None)
    artifact_ids = deps.created_artifact_ids(getattr(result, "steps", []))
    if user_message and assistant_message and artifact_ids:
        assets = app_services.chats.link_artifacts_to_turn(chat_id, user_message["message_id"], assistant_message["message_id"], artifact_ids)
        if assets:
            assistant_message["artifacts"] = [deps.library_asset_json(asset) for asset in assets]
    if assistant_message and retrieval_traces:
        app_services.workspace.save_retrieval_traces(assistant_message["message_id"], chat.project_id, retrieval_traces)
        assistant_message["retrievalTrace"] = retrieval_traces


def persist_generation(deps: PersistenceDependencies, app_services: Any, chat: Any, chat_id: str, full_history: list[dict[str, Any]], agent: Any, initial_history_length: int, result: Any, schedule_proposals: list[dict[str, Any]], web_sources: list[dict[str, str]], retrieval_traces: list[dict[str, Any]], events: Queue) -> None:
    prepare_generation_history(deps, chat, agent, result, schedule_proposals, web_sources)
    saved_history = deps.persisted_history(full_history, agent.history, initial_history_length)
    turn_created_at = datetime.now(UTC).isoformat()
    for item in saved_history[len(full_history):]:
        item.setdefault("created_at", turn_created_at)
    app_services.chats.replace_history(chat_id, saved_history)
    attach_generation_evidence(deps, app_services, chat, chat_id, saved_history[len(full_history):], result, retrieval_traces)
    deps.background_job_repository(app_services.chats.database).enqueue("memory_index", {"chat_id": chat_id})
    completed_message = next((item for item in reversed(saved_history) if item["role"] == "assistant"), {"role": "assistant", "content": result.text, "content_blocks": result.content_blocks})
    events.put(("message", deps.message_json(completed_message)))
    events.put(("done", {}))


def persist_static_response(deps: PersistenceDependencies, app_services: Any, chat_id: str, full_history: list[dict[str, Any]], content: str, response: str, events: Queue) -> None:
    created_at = datetime.now(UTC).isoformat()
    saved_history = [*full_history, {"role": "user", "content": content, "created_at": created_at}, {"role": "assistant", "content": response, "created_at": created_at}]
    app_services.chats.replace_history(chat_id, saved_history)
    events.put(("message", deps.message_json(saved_history[-1])))
    events.put(("done", {}))
