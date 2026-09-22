"""Crash boundaries and state transitions; PostgreSQL lock races live in integration tests."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from agent_core.ai.providers import NormalizedReply
from agent_core.content.library import LibraryService
from agent_core.integrations.notifications import EmailDeliveryError
from agent_core.persistence.store import (
    Base, Database, User, Workspace, Project, Workflow, WorkflowRun, WorkflowStepRun,
    LibraryAsset, Schedule, ScheduleRun, ScheduleRepository, current_user_id, current_workspace_id,
)
from agent_core.workflows.contracts import WorkflowConfig, RunInput
from agent_core.workflows.executor import WorkflowExecutor, WorkflowHeartbeat, transient_error, validate_config
from agent_core.workflows.repository import WorkflowRepository, WorkflowConflict, LeaseLost, aware


@pytest.fixture
def state(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'workflow.db'}")
    Base.metadata.create_all(db.engine, tables=[model.__table__ for model in (
        User, Workspace, Project, Workflow, LibraryAsset, WorkflowRun, WorkflowStepRun, Schedule, ScheduleRun,
    )])
    ut, wt = current_user_id.set("user"), current_workspace_id.set("workspace")
    with db.session() as session:
        session.add_all([User(id="user", email="test@example.com"), Workspace(id="workspace", name="Team"),
            Project(id="project", name="Project", workspace_id="workspace", user_id="user")])
        session.commit()
    repo = WorkflowRepository(db)
    workflow = repo.save("project", WorkflowConfig(name="Weekly", repository="org/repo", provider="openai", model="test", notifyEmail=True))
    now = datetime.now(UTC)
    period = RunInput(startsAt=now - timedelta(days=8), endsAt=now - timedelta(days=1))
    source = Mock(return_value=[{"id": "S1", "kind": "pr", "state": "closed", "url": "https://github.com/org/repo/pull/1"}])
    model = Mock(return_value=NormalizedReply(text="Report [S1]"))
    email = Mock()
    services = SimpleNamespace(chats=SimpleNamespace(database=db),
        workspace=SimpleNamespace(membership=lambda *_: SimpleNamespace(role="editor"),
            get=lambda *_: SimpleNamespace(workspace_id="workspace")),
        auth=SimpleNamespace(repository=SimpleNamespace(get_user=lambda _: SimpleNamespace(is_active=True, email="test@example.com"))),
        library=LibraryService(db, tmp_path / "library"), github=SimpleNamespace(list_updated_issues=source),
        email=SimpleNamespace(enabled=True, send=email), settings=SimpleNamespace(app_web_url="https://app.example"))
    monkeypatch.setattr("agent_core.workflows.executor.validate_config", lambda *_: SimpleNamespace(max_steps=1))
    monkeypatch.setattr("agent_core.workflows.executor.build_client", lambda _: SimpleNamespace(complete=model))
    run = repo.enqueue(workflow, period)
    yield SimpleNamespace(db=db, repo=repo, workflow=workflow, period=period, run=run,
        services=services, source=source, model=model, email=email, executor=WorkflowExecutor(services))
    current_workspace_id.reset(wt)
    current_user_id.reset(ut)
    db.engine.dispose()


def expire(s, run_id):
    with s.db.session() as session:
        session.get(WorkflowRun, run_id).lease_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()


def test_lease_fences_every_write_before_and_after_reclaim(state):
    s = state
    old = s.repo.claim()
    s.repo.step(old.id, "source", "running", lease_token=old.lease_token)
    expire(s, old.id)
    assert not s.repo.heartbeat(old.id, old.lease_token)
    for operation in (
        lambda: s.repo.step(old.id, "source", "succeeded", {}, lease_token=old.lease_token),
        lambda: s.repo.finish(old.id, lease_token=old.lease_token),
        lambda: s.repo.retry(old.id, "source", "error", old.lease_token),
    ):
        with pytest.raises(LeaseLost):
            operation()
    new = s.repo.claim()
    assert new.id == old.id and new.lease_token != old.lease_token
    # A late worker stops quietly without changing its successor's checkpoints.
    s.executor.execute(old)
    assert s.repo.detail("project", old.id)[0].lease_token == new.lease_token
    s.executor.execute(new)
    assert s.repo.detail("project", old.id)[0].status == "succeeded"


def test_heartbeat_is_active_during_blocking_call(state):
    s = state
    run = s.repo.claim()
    beat = Event()
    real = s.repo.heartbeat
    def heartbeat(*args):
        result = real(*args)
        beat.set()
        return result
    s.repo.heartbeat = heartbeat
    with WorkflowHeartbeat(s.repo, run, interval=0.01):
        assert beat.wait(2)
    assert aware(s.repo.detail("project", run.id)[0].lease_until) > aware(run.lease_until)


def test_idempotency_input_conflict_and_database_guard(state):
    s = state
    first = s.repo.enqueue(s.workflow, s.period, "one-request")
    assert s.repo.enqueue(s.workflow, s.period, "one-request").id == first.id
    other = RunInput(startsAt=s.period.startsAt - timedelta(days=1), endsAt=s.period.endsAt)
    with pytest.raises(WorkflowConflict):
        s.repo.enqueue(s.workflow, other, "one-request")
    with s.db.session() as session:
        session.add(WorkflowRun(workflow_id=s.workflow.id, project_id="project", snapshot={},
            starts_at=s.period.startsAt, ends_at=s.period.endsAt, idempotency_key="one-request"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_retry_source_failure_resets_unstarted_steps(state):
    s = state
    s.source.side_effect = ValueError("invalid source")
    s.executor.run_once()
    assert s.repo.detail("project", s.run.id)[0].status == "failed"
    s.repo.retry_run("project", s.run.id)
    s.source.side_effect = None
    s.executor.run_once()
    result, steps = s.repo.detail("project", s.run.id)
    assert result.status == "succeeded"
    assert [step.status for step in steps] == ["succeeded"] * 4
    assert s.model.call_count == 1 and s.email.call_count == 1
    assert '"kind": "pr"' in s.model.call_args.args[1][0]["content"]
    assert "merged" in s.model.call_args.args[0]


def test_retry_delays_and_exhaustion(state):
    s = state
    now = datetime.now(UTC)
    for index, minutes in enumerate((1, 5, 15), 1):
        run = s.repo.claim(now=now)
        s.repo.step(run.id, "source", "running", lease_token=run.lease_token)
        assert s.repo.retry(run.id, "source", "temporary", run.lease_token, now=now)
        step = s.repo.detail("project", run.id)[1][0]
        assert step.attempt == index
        assert aware(step.retry_at) == now + timedelta(minutes=minutes)
        assert s.repo.claim(now=now) is None
        now = aware(step.retry_at)
    run = s.repo.claim(now=now)
    s.repo.step(run.id, "source", "running", lease_token=run.lease_token)
    assert not s.repo.retry(run.id, "source", "temporary", run.lease_token, now=now)


@pytest.mark.parametrize("status, expected", [(400, False), (401, False), (403, False), (429, True), (503, True)])
def test_typed_provider_errors(status, expected):
    error = httpx.HTTPStatusError("secret", request=httpx.Request("GET", "https://example.com"), response=httpx.Response(status))
    # SDKs expose status_code; httpx exposes response.status_code.
    wrapped = RuntimeError("sanitized")
    wrapped.__cause__ = error
    assert transient_error(wrapped) is expected


def test_artifact_upload_crash_reuses_object_and_checkpoint(state, monkeypatch):
    s = state
    publish = s.executor.runs.publish_artifact
    def crash(*_):
        raise SystemExit("crash after upload")
    monkeypatch.setattr(s.executor.runs, "publish_artifact", crash)
    with pytest.raises(SystemExit):
        s.executor.run_once()
    files = list(s.services.library.directory.iterdir())
    assert len(files) == 1
    expire(s, s.run.id)
    monkeypatch.setattr(s.executor.runs, "publish_artifact", publish)
    s.executor.run_once()
    result, steps = s.repo.detail("project", s.run.id)
    assert result.status == "succeeded" and steps[2].output["artifactId"] == result.artifact_id
    assert list(s.services.library.directory.iterdir()) == files
    with s.db.session() as session:
        assert len(list(session.scalars(select(LibraryAsset)))) == 1
    assert s.source.call_count == s.model.call_count == 1


def test_email_crash_becomes_unknown_and_explicit_resend_only(state):
    s = state
    s.email.side_effect = SystemExit("SMTP accepted; process died")
    with pytest.raises(SystemExit):
        s.executor.run_once()
    expire(s, s.run.id)
    s.email.side_effect = None
    s.executor.run_once()
    result, steps = s.repo.detail("project", s.run.id)
    assert result.status == "succeeded" and steps[3].status == "unknown"
    assert s.email.call_count == 1
    with pytest.raises(WorkflowConflict):
        s.repo.retry_run("project", s.run.id, "notification")
    s.repo.retry_run("project", s.run.id, "notification", confirm_resend=True)
    s.executor.run_once()
    assert s.email.call_count == 2 and s.model.call_count == 1
    assert s.repo.detail("project", s.run.id)[0].artifact_id == result.artifact_id


def test_email_rejected_retry_never_repeats_ai(state):
    s = state
    s.email.side_effect = EmailDeliveryError("rejected")
    s.executor.run_once()
    result, steps = s.repo.detail("project", s.run.id)
    assert result.status == "succeeded" and steps[3].status == "failed"
    s.repo.retry_run("project", result.id, "notification")
    s.email.side_effect = None
    s.executor.run_once()
    assert s.model.call_count == 1 and s.source.call_count == 1 and s.email.call_count == 2


def test_resumed_side_effect_does_not_require_provider_credentials(state, monkeypatch):
    s = state
    s.email.side_effect = EmailDeliveryError("reject")
    s.executor.run_once()
    s.repo.retry_run("project", s.run.id, "notification")
    monkeypatch.setattr("agent_core.workflows.executor.validate_config", validate_config)
    monkeypatch.setattr("agent_core.workflows.executor.selected_settings", lambda *_: pytest.fail("model already completed"))
    s.services.workspace.connector_scopes = lambda _: [SimpleNamespace(connector_slug="github", config={"repositories": ["org/repo"]})]
    s.email.side_effect = None
    s.executor.run_once()
    assert s.repo.detail("project", s.run.id)[0].status == "succeeded"


def test_workflow_api_idempotency_and_viewer_actions(state, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.modules.workflows.router import build_router
    s = state
    monkeypatch.setattr("api.modules.workflows.router.validate_config", lambda *_: None)
    app = FastAPI()
    app.include_router(build_router({}, lambda: s.services))
    with TestClient(app) as client:
        base = f"/api/projects/project/workflows/{s.workflow.id}/runs"
        first = client.post(base, json=s.period.model_dump(mode="json"), headers={"Idempotency-Key": "request"})
        again = client.post(base, json=s.period.model_dump(mode="json"), headers={"Idempotency-Key": "request"})
        assert first.status_code == 202 and again.json()["id"] == first.json()["id"]
        changed = s.period.model_copy(update={"startsAt": s.period.startsAt - timedelta(days=1)})
        assert client.post(base, json=changed.model_dump(mode="json"), headers={"Idempotency-Key": "request"}).status_code == 409
        detail = f"/api/projects/project/workflow-runs/{s.run.id}"
        assert client.get(detail).json()["canWrite"] is True
        s.services.workspace.membership = lambda *_: SimpleNamespace(role="viewer")
        assert client.get(detail).json()["canWrite"] is False
        assert client.post(detail + "/cancel").status_code == 403
        assert client.post(detail + "/retry", json={}).status_code == 403


def test_schedule_api_dispatches_workflow_without_chat(state):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.modules.schedules.management_router import build_router
    s = state
    now = datetime.now(UTC)
    with s.db.session() as session:
        schedule = Schedule(title="Weekly", project_id="project", workflow_id=s.workflow.id,
            starts_at=now, next_run_at=now, recurrence="weekly", timezone="Asia/Ho_Chi_Minh")
        session.add(schedule)
        session.commit()
    def get(model, object_id):
        with s.db.session() as session:
            return session.get(model, object_id)
    s.services.workspace.get = get
    app = FastAPI()
    app.include_router(build_router(SimpleNamespace(services=lambda: s.services,
        schedule_model=Schedule, schedule_repository=ScheduleRepository,
        api_error_responses={}, schedule_not_found_error="missing",
        schedule_worker=lambda *_: pytest.fail("workflow must not prepare chat"))))
    with TestClient(app) as client:
        response = client.post(f"/api/schedules/{schedule.id}/run-now")
        assert response.status_code == 202
        assert response.json()["workflowRunId"] and "chatId" not in response.json()
        assert client.patch(f"/api/schedules/{schedule.id}", json={"prompt": "change"}).status_code == 409


def test_final_commit_failure_does_not_reopen_sent_email(state, monkeypatch):
    s = state
    finish = s.executor.runs.finish
    def fail(*_, **__):
        raise RuntimeError("database disconnected after notification checkpoint")
    monkeypatch.setattr(s.executor.runs, "finish", fail)
    with pytest.raises(RuntimeError):
        s.executor.run_once()
    assert s.repo.detail("project", s.run.id)[1][3].status == "succeeded"
    expire(s, s.run.id)
    monkeypatch.setattr(s.executor.runs, "finish", finish)
    s.executor.run_once()
    assert s.repo.detail("project", s.run.id)[0].status == "succeeded"
    assert s.email.call_count == 1


def test_cancel_queued_and_cancel_during_agent(state):
    s = state
    s.repo.cancel("project", s.run.id)
    assert s.repo.claim() is None
    s.repo.retry_run("project", s.run.id)
    def cancel(*_):
        s.repo.cancel("project", s.run.id)
        return NormalizedReply(text="Done [S1]")
    s.model.side_effect = cancel
    s.executor.run_once()
    result, _ = s.repo.detail("project", s.run.id)
    assert result.status == "cancelled" and result.artifact_id is None
    s.email.assert_not_called()


def test_schedule_enqueue_and_advance_are_atomic(state, monkeypatch):
    s = state
    due = datetime(2026, 9, 7, 1, tzinfo=UTC)
    now = datetime(2026, 9, 21, 2, tzinfo=UTC)
    with s.db.session() as session:
        schedule = Schedule(title="Weekly", project_id="project", workflow_id=s.workflow.id,
            starts_at=due, next_run_at=due, recurrence="weekly", timezone="Asia/Ho_Chi_Minh")
        session.add(schedule)
        session.commit()
    schedules = ScheduleRepository(s.db)
    original = WorkflowRepository.enqueue_schedule
    def crash(*_):
        raise RuntimeError("crash")
    monkeypatch.setattr(WorkflowRepository, "enqueue_schedule", crash)
    with pytest.raises(RuntimeError):
        schedules.claim_due(now)
    with s.db.session() as session:
        assert aware(session.get(Schedule, schedule.id).next_run_at) == due
        assert not list(session.scalars(select(ScheduleRun)))
    monkeypatch.setattr(WorkflowRepository, "enqueue_schedule", original)
    assert schedules.claim_due(now) == []  # workflow schedules never enter chat executor
    schedules.claim_due(now)
    with s.db.session() as session:
        runs = list(session.scalars(select(WorkflowRun).where(WorkflowRun.id != s.run.id)))
        assert len(runs) == 1 and runs[0].user_id == "user" and runs[0].workspace_id == "workspace"
        assert aware(runs[0].starts_at) == datetime(2026, 9, 13, 17, tzinfo=UTC)
        assert aware(runs[0].ends_at) == datetime(2026, 9, 20, 17, tzinfo=UTC)
        assert len(list(session.scalars(select(ScheduleRun)))) == 1
    with pytest.raises(ValueError, match="Project"):
        schedules.claim_manual(schedule.id, now)
    manual = schedules.enqueue_workflow_manual(schedule.id, now)
    assert manual.project_id == "project" and manual.status == "queued"
    with s.db.session() as session:
        assert aware(session.get(Schedule, schedule.id).next_run_at) == datetime(2026, 9, 28, 1, tzinfo=UTC)


def test_transient_provider_failure_keeps_source_checkpoint(state):
    s = state
    s.model.side_effect = httpx.ReadTimeout("secret")
    s.executor.run_once()
    run, steps = s.repo.detail("project", s.run.id)
    assert run.status == "retrying" and steps[0].status == "succeeded"
    assert steps[1].attempt == 1 and "secret" not in steps[1].error
    assert s.executor.run_once() is False
    s.repo.cancel("project", run.id)
    assert s.repo.detail("project", run.id)[0].status == "cancelled"
    s.repo.retry_run("project", run.id)
    s.model.side_effect = None
    s.executor.run_once()
    assert s.repo.detail("project", run.id)[0].status == "succeeded"
    assert s.source.call_count == 1


def test_cannot_retry_completed_step_with_stale_downstream_outputs(state):
    s = state
    s.email.side_effect = EmailDeliveryError("reject")
    s.executor.run_once()
    with pytest.raises(WorkflowConflict):
        s.repo.retry_run("project", s.run.id, "source")


@pytest.mark.parametrize("failure_at, uncertain", [("login", False), ("send", True), ("quit", False)])
def test_smtp_delivery_boundary(monkeypatch, failure_at, uncertain):
    from agent_core.integrations.notifications import EmailNotificationService
    class SMTP:
        def __enter__(self): return self
        def __exit__(self, *_):
            if failure_at == "quit": raise OSError("quit failed")
        def login(self, *_):
            if failure_at == "login": raise OSError("login failed")
        def send_message(self, *_):
            if failure_at == "send": raise OSError("response lost")
    monkeypatch.setattr("agent_core.integrations.notifications.smtplib.SMTP", lambda *_, **__: SMTP())
    service = EmailNotificationService(SimpleNamespace(smtp_host="smtp", smtp_from="from@example.com",
        smtp_port=25, smtp_use_tls=False, smtp_username="user", smtp_password="password"))
    if failure_at == "quit":
        service.send("to@example.com", "Subject", "Body")
    else:
        with pytest.raises(EmailDeliveryError) as error:
            service.send("to@example.com", "Subject", "Body")
        assert error.value.uncertain is uncertain
