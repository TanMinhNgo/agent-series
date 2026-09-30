"""Schedules: request contracts, recurrence and the schedule worker."""

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from api.contracts.requests import ScheduleRequest, ScheduleProposalPayload, ScheduleUpdateRequest
from agent_core.persistence.store import Chat, Schedule, ScheduleRepository, current_user_id, utc_now
from agent_core.jobs.scheduler import RunHeartbeat, ScheduleWorker
from agent_core.integrations.notifications import public_chat_url
from agent_core.integrations.web_search import WebSearchService, WebSourceUnavailable
from api_support import HistoryChats, stub_scheduler


def test_schedule_proposal_requires_an_explicit_timezone() -> None:
    proposal = ScheduleProposalPayload.model_validate({
        "title": "Tổng kết kế hoạch", "prompt": "Tổng kết và nêu việc tiếp theo.",
        "startsAt": "2026-08-26T09:00:00+07:00", "recurrence": "weekly",
    })
    assert proposal.starts_at.tzinfo is not None
    with pytest.raises(ValidationError):
        ScheduleProposalPayload.model_validate({
            "title": "Thiếu múi giờ", "prompt": "Không được tự đoán thời điểm.",
            "startsAt": "2026-08-26T09:00:00",
        })


def test_utc_now_is_timezone_aware() -> None:
    assert utc_now().tzinfo is UTC


def test_schedule_worker_restores_owner_and_replaces_legacy_chat(monkeypatch) -> None:
    observed: list[str | None] = []
    created: list[Chat] = []
    stored_history: list[dict] = []

    class Chats:
        database = object()

        def get(self, chat_id):
            observed.append(current_user_id.get())
            # The prior bug left this ownerless chat linked to the schedule.
            return None if chat_id == "legacy-chat" else created[0] if created else None

        def create(self, provider, model):
            observed.append(current_user_id.get())
            chat = Chat(id="replacement-chat", user_id="user-1", provider=provider, model=model)
            created.append(chat)
            return chat

        def update(self, _chat_id, **_values):
            observed.append(current_user_id.get())
            return created[0]

        def history(self, _chat_id):
            observed.append(current_user_id.get())
            return [dict(item) for item in stored_history]

        def replace_history(self, _chat_id, history):
            observed.append(current_user_id.get())
            stored_history[:] = [dict(item) for item in history]

        def set_unread(self, chat_id, unread):
            observed.append(current_user_id.get())
            assert (chat_id, unread) == ("replacement-chat", True)
            return created[0]

    class Runs:
        def attach_chat(self, schedule_id, chat_id):
            observed.append(current_user_id.get())
            assert (schedule_id, chat_id) == ("schedule-1", "replacement-chat")

        def finish(self, _run_id, **_values):
            observed.append(current_user_id.get())

    class AgentStub:
        def __init__(self, history: list[dict]):
            self.history = [dict(item) for item in history]

        def run(self, prompt, *, append_user_message=True):
            assert prompt == "Dạy frontend"
            assert append_user_message is False
            self.history.append({"role": "assistant", "content": "Bài học đã sẵn sàng."})
            return SimpleNamespace(text="Bài học đã sẵn sàng.", content_blocks=[], status="completed")

    services = SimpleNamespace(
        chats=Chats(),
        settings=SimpleNamespace(provider="openai", active_model="gpt-test"),
        memory=SimpleNamespace(recall=lambda *_args: ""),
        workspace=SimpleNamespace(list_plugins=lambda: []),
    )
    worker = ScheduleWorker(services)
    worker.runs = Runs()
    stub_scheduler(monkeypatch, lambda *_args, **kwargs: AgentStub(kwargs["history"]))
    schedule = Schedule(
        id="schedule-1",
        user_id="user-1",
        title="Củng cố frontend",
        prompt="Dạy frontend",
        chat_id="legacy-chat",
    )

    worker.execute(schedule, "run-1")

    assert created
    assert all(user_id == "user-1" for user_id in observed)
    assert [item["role"] for item in stored_history] == ["user", "assistant"]
    assert current_user_id.get() is None


def test_schedule_worker_retries_transient_provider_errors_without_duplicate_prompt(monkeypatch) -> None:
    stored_history: list[dict] = []
    attempts = 0
    finished: list[dict] = []
    chat = Chat(id="schedule-chat", user_id="user-1", provider="openai", model="gpt-test")

    class Runs:
        def finish(self, _run_id, **values): finished.append(values)
        def schedule_retry(self, _run_id, error, delays):
            assert error == "Provider tạm thời không khả dụng; đang chờ tự thử lại."
            assert delays == (5, 15, 30)
            return datetime(2026, 8, 26, 5, tzinfo=UTC), 1

    class AgentStub:
        def __init__(self, history): self.history = [dict(item) for item in history]
        def run(self, _prompt, *, append_user_message=True):
            nonlocal attempts
            attempts += 1
            assert append_user_message is False
            if attempts == 1:
                raise ConnectionError("provider unavailable")
            self.history.append({"role": "assistant", "content": "Đã hoàn tất."})
            return SimpleNamespace(text="Đã hoàn tất.", content_blocks=[], status="completed")

    services = SimpleNamespace(
        chats=HistoryChats(chat, stored_history),
        memory=SimpleNamespace(recall=lambda *_args: ""),
        workspace=SimpleNamespace(list_plugins=lambda: []),
    )
    worker = ScheduleWorker(services)
    worker.runs = Runs()
    stub_scheduler(monkeypatch, lambda *_args, **kwargs: AgentStub(kwargs["history"]))
    worker.execute(Schedule(id="schedule-1", user_id="user-1", title="Báo cáo", prompt="Tạo báo cáo", chat_id=chat.id), "run-1")

    assert attempts == 1
    assert [item["role"] for item in stored_history] == ["user"]
    assert finished == []

    worker.execute(Schedule(id="schedule-1", user_id="user-1", title="Báo cáo", prompt="Tạo báo cáo", chat_id=chat.id), "run-1", prompt_persisted=True)

    assert attempts == 2
    assert [item["role"] for item in stored_history] == ["user", "assistant"]
    assert finished == [{"summary": "Đã hoàn tất."}]


def test_schedule_worker_creates_chat_with_saved_schedule_provider_model() -> None:
    created: list[tuple[str, str]] = []
    chat = Chat(id="schedule-chat", user_id="user-1", provider="openai", model="gpt-test")

    class Chats:
        database = object()
        def get(self, _chat_id): return None
        def create(self, provider, model):
            created.append((provider, model))
            return chat
        def update(self, _chat_id, **_values): return chat

    worker = ScheduleWorker(SimpleNamespace(
        chats=Chats(),
        settings=SimpleNamespace(provider="gemini", active_model="gemini-default"),
    ))
    worker.runs = SimpleNamespace(attach_chat=lambda *_args: None)

    token = current_user_id.set("user-1")
    try:
        result = worker.ensure_chat(Schedule(
            id="schedule-1", user_id="user-1", title="Báo cáo",
            provider="openai", model="gpt-test",
        ))
    finally:
        current_user_id.reset(token)

    assert result is chat
    assert created == [("openai", "gpt-test")]


def test_schedule_worker_reports_final_transient_failure_after_retry_budget(monkeypatch) -> None:
    stored_history: list[dict] = []
    finished: list[dict] = []
    chat = Chat(id="schedule-chat", user_id="user-1", provider="gemini", model="gemini-test")

    class Runs:
        def schedule_retry(self, *_args): return None
        def finish(self, _run_id, **values): finished.append(values)

    class AgentStub:
        def __init__(self, history): self.history = history
        def run(self, *_args, **_kwargs): raise ConnectionError("provider unavailable")

    services = SimpleNamespace(chats=HistoryChats(chat, stored_history), memory=SimpleNamespace(recall=lambda *_args: ""), workspace=SimpleNamespace(list_plugins=lambda: []))
    worker = ScheduleWorker(services)
    worker.runs = Runs()
    stub_scheduler(monkeypatch, lambda *_args, **kwargs: AgentStub(kwargs["history"]))

    worker.execute(Schedule(id="schedule-1", user_id="user-1", title="Báo cáo", prompt="Tạo báo cáo", chat_id=chat.id), "run-1")

    assert "sau 3 lần thử lại" in stored_history[-1]["content"]
    assert finished == [{"error": "Provider tạm thời không khả dụng; đã hết số lần tự thử lại."}]


def _grounded_worker(monkeypatch, *, search_result: str, notify_email: bool, send=None):
    """Build a worker whose collaborators are all stubs, for grounding/email tests."""
    state = SimpleNamespace(history=[], emails=[], finished=[], retries=0, agent_calls=0, sent=[])
    chat = Chat(id="schedule-chat", user_id="user-1", provider="openai", model="gpt-test")

    class Runs:
        def finish(self, _run_id, **values): state.finished.append(values)
        def schedule_retry(self, *_args):
            state.retries += 1
            return None
        def record_email(self, _run_id, *, status, error=None): state.emails.append((status, error))

    class AgentStub:
        def __init__(self, history):
            # Mirrors the real agent: with append_user_message=False the prompt
            # argument is ignored, so only this history reaches the model.
            self.history = [dict(item) for item in history]
            state.agent_history = [dict(item) for item in history]

        def run(self, _prompt, *, append_user_message=True):
            state.agent_calls += 1
            assert append_user_message is False
            self.history.append({"role": "assistant", "content": "Bản tin."})
            return SimpleNamespace(text="Bản tin.", content_blocks=[], status="completed")

    def default_send(_to, _subject, _body): state.sent.append(_to)

    services = SimpleNamespace(
        chats=HistoryChats(chat, state.history),
        memory=SimpleNamespace(recall=lambda *_args: ""),
        workspace=SimpleNamespace(list_plugins=lambda: []),
        web_search=SimpleNamespace(search=lambda *_args, **_kwargs: search_result, enabled=True),
        email=SimpleNamespace(enabled=True, send=send or default_send),
        auth=SimpleNamespace(repository=SimpleNamespace(get_user=lambda _id: SimpleNamespace(email="owner@example.com"))),
        settings=SimpleNamespace(app_web_url="https://agent.example.com"),
    )
    services.web_search.require_sources = WebSearchService.require_sources.__get__(services.web_search)
    worker = ScheduleWorker(services)
    worker.runs = Runs()
    stub_scheduler(monkeypatch, lambda *_args, **kwargs: AgentStub(kwargs["history"]))
    schedule = Schedule(
        id="schedule-1", user_id="user-1", title="Tin AI", prompt="Tổng hợp tin AI",
        chat_id=chat.id, require_web_source=True, notify_email=notify_email,
    )
    return worker, schedule, state


SEARCH_OK = json.dumps({
    "sources": [{"name": "VnExpress", "url": "https://vnexpress.net/ai", "kind": "external"}],
    "context": "[VnExpress](https://vnexpress.net/ai)\nTin mới.",
})


def test_grounded_schedule_run_attaches_sources_and_sends_one_email(monkeypatch) -> None:
    worker, schedule, state = _grounded_worker(monkeypatch, search_result=SEARCH_OK, notify_email=True)

    worker.execute(schedule, "run-1")

    assert state.agent_calls == 1
    # The sources must reach the model through history, not the ignored prompt arg.
    assert "https://vnexpress.net/ai" in state.agent_history[-1]["content"]
    assert state.agent_history[-1]["role"] == "user"
    # ...while the chat still persists the plain prompt the user wrote.
    assert state.history[0]["content"] == "Tổng hợp tin AI"
    assert state.history[-1]["sources"] == [{"name": "VnExpress", "url": "https://vnexpress.net/ai", "kind": "external"}]
    assert state.finished == [{"summary": "Bản tin."}]
    assert state.sent == ["owner@example.com"]
    assert state.emails == [("sent", None)]


def test_missing_web_sources_fail_the_run_before_any_provider_call(monkeypatch) -> None:
    worker, schedule, state = _grounded_worker(
        monkeypatch, search_result="[Lỗi] Không thể tìm web: timed out", notify_email=True
    )

    worker.execute(schedule, "run-1")

    assert state.agent_calls == 0
    assert state.retries == 0
    assert state.emails == []
    assert state.sent == []
    assert "Không lấy được nguồn web mới" in state.finished[0]["error"]
    assert "không lấy được nguồn web mới" in state.history[-1]["content"]


def test_email_failure_keeps_the_run_successful_and_reports_only_the_email(monkeypatch) -> None:
    def failing_send(*_args):
        raise RuntimeError("SMTP từ chối kết nối.")

    worker, schedule, state = _grounded_worker(
        monkeypatch, search_result=SEARCH_OK, notify_email=True, send=failing_send
    )

    worker.execute(schedule, "run-1")

    assert state.finished == [{"summary": "Bản tin."}]
    assert state.retries == 0
    assert state.emails == [("failed", "SMTP từ chối kết nối.")]
    assert [item["role"] for item in state.history] == ["user", "assistant"]


def test_schedule_without_email_notification_never_touches_smtp(monkeypatch) -> None:
    worker, schedule, state = _grounded_worker(monkeypatch, search_result=SEARCH_OK, notify_email=False)

    worker.execute(schedule, "run-1")

    assert state.finished == [{"summary": "Bản tin."}]
    assert state.emails == []
    assert state.sent == []


def test_absent_web_sources_are_never_treated_as_a_transient_provider_error() -> None:
    assert ScheduleWorker._is_transient_error(WebSourceUnavailable("Không thể tìm web: timed out")) is False
    assert ScheduleWorker._is_transient_error(RuntimeError("503 UNAVAILABLE")) is False
    assert ScheduleWorker._is_transient_error(ConnectionError("provider unavailable")) is True


def test_run_heartbeat_reports_while_running_and_stops_on_exit() -> None:
    beats: list[str] = []
    runs = SimpleNamespace(touch_run=lambda run_id: beats.append(run_id))

    with RunHeartbeat(runs, "run-1", interval=0.01):
        deadline = time.monotonic() + 2
        while not beats and time.monotonic() < deadline:
            time.sleep(0.01)

    assert beats
    assert beats[0] == "run-1"
    settled = len(beats)
    time.sleep(0.05)
    assert len(beats) == settled, "heartbeat must stop once the run leaves the context"


def test_a_failing_heartbeat_never_interrupts_the_run() -> None:
    def explode(_run_id):
        raise RuntimeError("mất kết nối DB")

    with RunHeartbeat(SimpleNamespace(touch_run=explode), "run-1", interval=0.01):
        time.sleep(0.05)


def test_chat_link_is_omitted_for_a_localhost_app_url() -> None:
    assert public_chat_url("http://localhost:5173", "chat-1") is None
    assert public_chat_url("https://agent.example.com", "chat-1") == "https://agent.example.com/chat/chat-1"


def test_schedule_request_accepts_frontend_camel_case_fields() -> None:
    payload = ScheduleRequest.model_validate({"title": "Demo", "startsAt": "2026-08-13T09:00:00+07:00", "endsAt": None, "projectId": None, "provider": "openai", "model": "gpt-test"})
    assert payload.starts_at.hour == 9
    assert (payload.provider, payload.model) == ("openai", "gpt-test")


def test_schedule_update_accepts_a_status_only_patch() -> None:
    assert ScheduleUpdateRequest.model_validate({"status": "paused"}).status == "paused"


def test_schedule_request_accepts_notification_flags_in_camel_case() -> None:
    payload = ScheduleRequest.model_validate({
        "title": "Tin AI",
        "startsAt": "2026-08-13T09:00:00+07:00",
        "requireWebSource": True,
        "notifyEmail": True,
    })
    assert (payload.require_web_source, payload.notify_email) == (True, True)
    assert ScheduleRequest.model_validate({"title": "X", "startsAt": "2026-08-13T09:00:00+07:00"}).notify_email is False


def test_next_recurring_run_skips_missed_intervals() -> None:
    schedule = Schedule(
        id="schedule-1",
        title="Daily digest",
        starts_at=datetime(2026, 8, 10, 9, tzinfo=UTC),
        recurrence="daily",
        next_run_at=datetime(2026, 8, 10, 9, tzinfo=UTC),
    )
    assert ScheduleRepository.next_run_after(schedule, datetime(2026, 8, 17, 10, tzinfo=UTC)) == datetime(2026, 8, 18, 9, tzinfo=UTC)


def test_editing_a_schedule_does_not_rewind_next_run_at_when_timing_is_unchanged() -> None:
    """The form resends startsAt every save; rewinding replays an executed slot."""
    current = Schedule(
        id="schedule-1",
        title="Tin AI",
        starts_at=datetime(2026, 8, 24, 11, tzinfo=UTC),
        recurrence="daily",
        next_run_at=datetime(2026, 8, 27, 11, tzinfo=UTC),
    )
    unchanged = ScheduleUpdateRequest.model_validate({
        "title": "Tin AI",
        "startsAt": "2026-08-24T11:00:00+00:00",
        "recurrence": "daily",
        "notifyEmail": True,
    }).model_dump(exclude_unset=True)
    assert not any(
        key in unchanged and unchanged[key] != getattr(current, key) for key in ("starts_at", "recurrence")
    )

    retimed = ScheduleUpdateRequest.model_validate({"startsAt": "2026-09-01T07:00:00+00:00"}).model_dump(exclude_unset=True)
    assert any(key in retimed and retimed[key] != getattr(current, key) for key in ("starts_at", "recurrence"))


def test_exhausted_schedule_does_not_retry_or_send_success_email(monkeypatch):
    from agent_core.ai.agent import Agent
    from agent_core.tools.registry import ToolRegistry

    worker, schedule, state = _grounded_worker(monkeypatch, search_result=SEARCH_OK, notify_email=True)
    def exhausted_agent(*_args, **kwargs):
        agent = Agent(object(), ToolRegistry([]), max_steps=0)
        agent.history = list(kwargs["history"])
        return agent
    monkeypatch.setattr("agent_core.jobs.scheduler.make_agent", exhausted_agent)
    worker.execute(schedule, "run-1")
    assert len(state.finished) == 1
    assert "giới hạn số bước" in state.finished[0]["error"]
    assert state.history[-1]["content"] == state.finished[0]["error"]
    assert state.retries == 0
    assert state.sent == state.emails == []
