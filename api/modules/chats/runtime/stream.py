"""SSE orchestration for chat turns."""

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any, Callable, Iterator


@dataclass(frozen=True)
class StreamDependencies:
    services: Callable[[], Any]
    sse: Callable[[str, dict[str, Any]], str]
    chat_runs: Any
    run_image_turn: Callable[..., Any]
    message_json: Callable[[dict[str, Any]], dict[str, Any]]
    small_talk_response: Callable[[str], str | None]
    persist_static_response: Callable[..., Any]
    run_agent_turn: Callable[..., Any]
    model_error_message: Callable[[Any, Exception], str]
    agent_cancelled: type[BaseException]
    image_generation_error: type[BaseException]
    current_user_id: Any
    current_workspace_id: Any


def _dispatch_turn(deps: StreamDependencies, app_services: Any, chat: Any, chat_id: str, content: str, attachments: list[dict], artifact_edit: Any, cancel_event: Event, events: Queue, research_web: bool) -> None:
    if cancel_event.is_set():
        raise deps.agent_cancelled()
    events.put(("status", {"message": "Agent đang suy nghĩ..."}))
    full_history = app_services.chats.history(chat_id)
    if getattr(chat, "mode", "standard") == "image":
        deps.run_image_turn(app_services, chat_id, content, attachments, full_history, events, deps.message_json)
        return
    static_response = None if attachments or artifact_edit is not None else deps.small_talk_response(content)
    if static_response is not None:
        if cancel_event.is_set():
            raise deps.agent_cancelled()
        deps.persist_static_response(app_services, chat_id, full_history, content, static_response, events)
        return
    deps.run_agent_turn(app_services, chat, chat_id, content, attachments, artifact_edit, cancel_event, full_history, events, research_web)


def stream_chat(
    deps: StreamDependencies,
    chat_id: str,
    content: str,
    attachments: list[dict],
    artifact_edit: Any = None,
    cancel_event: Event | None = None,
    run_id: str | None = None,
    research_web: bool = False,
) -> Iterator[str]:
    app_services = deps.services()
    chat = app_services.chats.get(chat_id)
    if chat is None:
        yield deps.sse("error", {"message": "Không tìm thấy chat."})
        return

    events: Queue[tuple[str, dict[str, Any]]] = Queue()
    cancel_event = cancel_event or Event()

    def run() -> None:
        user_token = deps.current_user_id.set(chat.user_id)
        workspace_token = deps.current_workspace_id.set(chat.workspace_id)
        try:
            _dispatch_turn(deps, app_services, chat, chat_id, content, attachments, artifact_edit, cancel_event, events, research_web)
        except deps.agent_cancelled:
            events.put(("cancelled", {"message": "Đã dừng tạo phản hồi."}))
        except (deps.image_generation_error, ValueError) as exc:
            events.put(("error", {"message": str(exc)}))
        except Exception as exc:  # noqa: BLE001
            events.put(("error", {"message": deps.model_error_message(chat, exc)}))
        finally:
            deps.chat_runs.finish(chat_id, run_id)
            deps.current_workspace_id.reset(workspace_token)
            deps.current_user_id.reset(user_token)
            events.put(("close", {}))

    Thread(target=run, daemon=True).start()
    try:
        while True:
            try:
                event, payload = events.get(timeout=15)
            except Empty:
                yield ": keepalive\n\n"
                continue
            if event == "close":
                return
            yield deps.sse(event, payload)
    finally:
        cancel_event.set()
