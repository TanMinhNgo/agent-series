"""Execution of one non-image chat generation turn."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TurnDependencies:
    load_generation_context: Callable[..., Any]
    make_agent: Callable[..., Any]
    project_connector_tools: Callable[..., Any]
    persist_generation: Callable[..., Any]
    agent_cancelled: type[BaseException]


def run_agent_turn(
    deps: TurnDependencies,
    app_services: Any,
    chat: Any,
    chat_id: str,
    content: str,
    attachments: list[dict],
    artifact_edit: Any,
    cancel_event: Any,
    full_history: list[dict[str, Any]],
    events: Any,
    research_web: bool = False,
) -> None:
    context = deps.load_generation_context(app_services, chat, content, chat_id, full_history, events, research_web)
    if cancel_event.is_set():
        raise deps.agent_cancelled()
    schedule_proposals: list[dict[str, Any]] = []
    agent = deps.make_agent(
        app_services,
        chat,
        context.memory,
        context.knowledge,
        personalization_context=context.personalization,
        plugin_tools=deps.project_connector_tools(app_services, chat),
        history=full_history,
        schedule_proposals=schedule_proposals,
        artifact_edit=artifact_edit,
        web_context=context.web,
        allow_web=research_web,
    )
    initial_history_length = len(agent.history)
    result = agent.run(content, attachments, on_step=lambda item: events.put((item["type"], item)), cancel_event=cancel_event)
    if cancel_event.is_set():
        raise deps.agent_cancelled()
    deps.persist_generation(app_services, chat, chat_id, full_history, agent, initial_history_length, result, schedule_proposals, context.web_sources, context.retrieval_traces, events)
