"""M0 runtime boundaries: scope, provider selection and HTTP independence."""

import subprocess
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agent_core.persistence.store import Chat, Project, current_user_id, current_workspace_id
from agent_core.runtime import agent as runtime
from agent_core.jobs.contracts import ScheduleProposalPayload


@contextmanager
def execution_scope(user, workspace):
    user_token = current_user_id.set(user)
    workspace_token = current_workspace_id.set(workspace)
    try:
        yield
    finally:
        current_workspace_id.reset(workspace_token)
        current_user_id.reset(user_token)


def test_scheduler_import_is_independent_of_http():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import agent_core.jobs.scheduler; assert not any(n == 'api' or n.startswith('api.') or n == 'fastapi' or n.startswith('fastapi.') for n in sys.modules)"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_shared_runtime_uses_passed_services_and_preserves_plan_tools(monkeypatch):
    credentials = []
    selected = SimpleNamespace(max_steps=2)
    services = SimpleNamespace(
        workspace=SimpleNamespace(membership=lambda *_: SimpleNamespace(role="editor")),
        model_registry=SimpleNamespace(active=lambda: {"openai": ["chosen-model"]}),
        credentials=SimpleNamespace(api_key=lambda user, provider: credentials.append((user, provider)) or "secret"),
        settings=SimpleNamespace(with_provider_model=lambda provider, model, key: selected),
        knowledge=object(), media=SimpleNamespace(hydrate_history=lambda history: history),
    )
    monkeypatch.setattr(runtime, "build_client", lambda settings: object() if settings is selected else pytest.fail("wrong settings"))
    monkeypatch.setattr(runtime, "build_knowledge_tool", lambda *_: None)
    tools = []
    monkeypatch.setattr(runtime, "build_default_registry", lambda knowledge, extra: tools.extend(extra) or object())
    chat = Chat(user_id="creator", workspace_id="team", provider="openai", model="chosen-model", mode="plan")
    history = [{"role": "user", "content": "plan"}]
    with execution_scope("editor", "team"):
        agent = runtime.make_agent(services, chat, history=history, schedule_proposals=[])
    assert credentials == [("creator", "openai")]
    assert not {tool.name for tool in tools} & {"create_file", "create_web_bundle", "create_artifact_version", "propose_schedule"}
    agent.history.append({"role": "assistant", "content": "plan"})
    assert len(history) == 1
    with pytest.raises(ValueError, match="Model"):
        runtime.selected_settings(services, "openai", "other-model", "creator")
    assert len(credentials) == 1


@pytest.mark.parametrize("actor,workspace,owner,chat_workspace,role,project_workspace", [
    ("other", None, "owner", None, "owner", None),
    ("owner", "other-team", "owner", "team", "owner", "team"),
    ("owner", "team", "owner", "team", "viewer", "team"),
    ("owner", "team", "owner", "team", None, "team"),
    ("owner", "team", "owner", "team", "owner", "other-team"),
])
def test_invalid_context_is_rejected_before_provider(monkeypatch, actor, workspace, owner, chat_workspace, role, project_workspace):
    services = SimpleNamespace(workspace=SimpleNamespace(
        membership=lambda *_: SimpleNamespace(role=role) if role else None,
        get=lambda *_: Project(id="project", user_id=owner, workspace_id=project_workspace),
    ))
    chat = Chat(user_id=owner, workspace_id=chat_workspace, project_id="project", provider="openai", model="chosen")
    monkeypatch.setattr(runtime, "selected_settings", lambda *_: pytest.fail("provider selection must not happen"))
    with execution_scope(actor, workspace), pytest.raises(ValueError):
        runtime.make_agent(services, chat, history=[])


def test_schedule_proposal_contract_still_requires_timezone():
    values = {"title": "Report", "prompt": "Summarize", "startsAt": "2026-09-21T09:00:00+07:00"}
    assert ScheduleProposalPayload.model_validate(values).starts_at.utcoffset().total_seconds() == 7 * 3600
    with pytest.raises(ValueError, match="múi giờ"):
        ScheduleProposalPayload.model_validate({**values, "startsAt": "2026-09-21T09:00:00"})


@pytest.mark.parametrize("field,value", [("user_id", "another"), ("workspace_id", "another"), ("project_id", "another")])
def test_schedule_rejects_mismatched_chat_before_writing(field, value):
    from agent_core.jobs.scheduler import ScheduleWorker
    from agent_core.persistence.store import Schedule
    chat = Chat(id="chat", user_id="owner", workspace_id="team", project_id="project")
    setattr(chat, field, value)
    services = SimpleNamespace(chats=SimpleNamespace(database=object(), get=lambda _: chat))
    worker = ScheduleWorker(services)
    schedule = Schedule(chat_id="chat", user_id="owner", workspace_id="team", project_id="project")
    with execution_scope("owner", "team"), pytest.raises(ValueError, match="Chat"):
        worker.ensure_chat(schedule)


def test_schedule_creates_chat_in_its_project():
    from agent_core.jobs.scheduler import ScheduleWorker
    from agent_core.persistence.store import Schedule
    created = []
    chat = Chat(id="new", user_id="owner", workspace_id="team", project_id="project")
    services = SimpleNamespace(
        chats=SimpleNamespace(database=object(), create=lambda provider, model, **kwargs: created.append((provider, model, kwargs)) or chat, update=lambda *_args, **_kwargs: chat),
        workspace=SimpleNamespace(membership=lambda *_: SimpleNamespace(role="editor"), get=lambda *_: Project(id="project", user_id="owner", workspace_id="team")),
    )
    worker = ScheduleWorker(services)
    worker.runs = SimpleNamespace(attach_chat=lambda *_: None)
    schedule = Schedule(id="schedule", user_id="owner", workspace_id="team", project_id="project", provider="openai", model="chosen", title="Report")
    with execution_scope("owner", "team"):
        assert worker.ensure_chat(schedule) is chat
    assert created == [("openai", "chosen", {"project_id": "project"})]
