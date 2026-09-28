"""Shared fakes and helpers for the API test modules."""

from types import SimpleNamespace

import api.main as main_module
from api.main import app


chat_module = main_module.chat_module


make_agent = chat_module.make_agent


message_json = chat_module.message_json


def route(name: str):
    """Return the endpoint mounted on the app, so tests exercise the live router code."""
    def walk(routes):
        for item in routes:
            nested = getattr(item, "original_router", None)
            yield from walk(nested.routes) if nested is not None else (item,)

    found = [item.endpoint for item in walk(app.routes) if getattr(item, "name", None) == name]
    assert len(found) == 1, name
    return found[0]


def use_services(monkeypatch, fake) -> None:
    monkeypatch.setattr(app.state, "services", fake, raising=False)


class RecordingJobs:
    """Hands out one job and records what BackgroundWorker does with it."""

    def __init__(self, job, calls: list, record_heartbeats: bool = False):
        self.job, self.calls, self.record_heartbeats = job, calls, record_heartbeats

    def claim(self, _now): return self.job

    def heartbeat(self, _now, current_job_type=None, last_error=None):
        if self.record_heartbeats and (current_job_type or last_error):
            self.calls.append(("heartbeat", current_job_type or last_error))

    def succeed(self, job_id): self.calls.append(("succeed", job_id))
    def fail(self, job_id, error, _now): self.calls.append(("fail", (job_id, error)))


class HistoryChats:
    """One chat whose history lives in a caller-owned list."""
    database = object()

    def __init__(self, chat, history: list[dict]):
        self.chat, self.stored = chat, history

    def get(self, _chat_id): return self.chat
    def history(self, _chat_id): return [dict(item) for item in self.stored]
    def replace_history(self, _chat_id, history): self.stored[:] = [dict(item) for item in history]
    def set_unread(self, _chat_id, _unread): return self.chat


def stub_scheduler(monkeypatch, make_agent) -> None:
    monkeypatch.setattr("agent_core.jobs.scheduler.make_agent", make_agent)
    monkeypatch.setattr("agent_core.jobs.scheduler.connected_read_tools", lambda _plugins: [])
    monkeypatch.setattr("agent_core.jobs.scheduler.BackgroundJobRepository", lambda _database: SimpleNamespace(enqueue=lambda *_args, **_kwargs: None))


class SavingChats:
    """An empty chat that assigns message ids and keeps what stream_chat persists."""

    def __init__(self, chat, saved: list[dict]):
        self.chat, self.saved = chat, saved

    def get(self, _chat_id): return self.chat
    def history(self, _chat_id): return []

    def replace_history(self, _chat_id, history):
        for index, item in enumerate(history):
            item["message_id"] = f"message-{index}"
        self.saved.extend(history)


class StubJobs:
    def __init__(self, _database): pass
    def enqueue(self, _kind, _payload): pass


class FixedReplyAgent:
    def __init__(self, question: str, answer: str):
        self.question, self.answer, self.history = question, answer, []

    def run(self, _content, _attachments, on_step, **_kwargs):
        self.history = [{"role": "user", "content": self.question}, {"role": "assistant", "content": self.answer}]
        return SimpleNamespace(text=self.answer, content_blocks=[], status="completed")


def agent_services(chats, **extra) -> SimpleNamespace:
    return SimpleNamespace(
        chats=chats,
        memory=SimpleNamespace(recall=lambda *_args, **_kwargs: ""),
        workspace=SimpleNamespace(get=lambda *_args, **_kwargs: None, list_plugins=lambda: []),
        **extra,
    )
