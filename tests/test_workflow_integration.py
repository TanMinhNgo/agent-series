"""Isolated PostgreSQL M1 checks. RUN_WORKFLOW_INTEGRATION=1 enables them."""
import os
from datetime import UTC, datetime
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, select, delete
from sqlalchemy.engine import make_url
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_core.persistence.store import Database, User, Workspace, WorkspaceMember, Project, Workflow, WorkflowRun, LibraryAsset, ArtifactChunk, ConnectorConnection, ConnectorRepository, WorkspaceRepository, AuthRepository, current_user_id, current_workspace_id
from agent_core.content.library import LibraryService
from agent_core.workflows.contracts import WorkflowConfig, RunInput
from agent_core.workflows.repository import WorkflowRepository
from agent_core.workflows.repository import LeaseLost
from agent_core.workflows.executor import WorkflowExecutor
from agent_core.ai.providers import NormalizedReply
from api.modules.workflows.router import build_router

pytestmark = pytest.mark.integration
if os.getenv("RUN_WORKFLOW_INTEGRATION") != "1":
    pytest.skip("Set RUN_WORKFLOW_INTEGRATION=1", allow_module_level=True)


@pytest.fixture(scope="module")
def database():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    source = make_url(os.environ["DATABASE_URL"])
    name = "agent_workflow_test_" + uuid4().hex[:12]
    target = source.set(database=name)
    admin = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5})
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    old = os.environ.get("DATABASE_URL")
    db = None
    try:
        os.environ["DATABASE_URL"] = target.render_as_string(hide_password=False)
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        db = Database(target)
        assert "workflow_runs" in inspect(db.engine).get_table_names()
        command.downgrade(cfg, "0036_chat_modes")
        assert "workflow_runs" not in inspect(db.engine).get_table_names()
        command.upgrade(cfg, "head")
        yield db
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old
        if db:
            db.engine.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()


@pytest.fixture
def setup(database, tmp_path, monkeypatch):
    uid, wid, pid = (str(uuid4()) for _ in range(3))
    with database.session() as session:
        session.add(User(id=uid, email=f"{uid}@example.com"))
        session.flush()
        session.add(Workspace(id=wid, name="Workflow test", created_by_user_id=uid))
        session.flush()
        session.add_all([WorkspaceMember(workspace_id=wid, user_id=uid, role="editor"), Project(id=pid, name="Report", user_id=uid, workspace_id=wid)])
        session.commit()
    ut, wt = current_user_id.set(uid), current_workspace_id.set(wid)
    workspace = WorkspaceRepository(database)
    monkeypatch.setattr(workspace, "connector_scopes", lambda _: [SimpleNamespace(connector_slug="github", config={"repositories": ["org/repo"]})])
    calls = []
    services = SimpleNamespace(chats=SimpleNamespace(database=database), workspace=workspace,
        model_registry=SimpleNamespace(active=lambda: {"openai": ["test-model"]}),
        credentials=SimpleNamespace(api_key=lambda user, provider: calls.append((user, provider)) or "test-key"),
        settings=SimpleNamespace(with_provider_model=lambda *_: SimpleNamespace(max_steps=1), app_web_url="https://app.example"),
        auth=SimpleNamespace(repository=AuthRepository(database)),
        github=SimpleNamespace(list_updated_issues=lambda *_: [{"id": "S1", "url": "https://github.com/org/repo/issues/1", "title": "Fix"}]),
        library=LibraryService(database, tmp_path), email=SimpleNamespace(enabled=True, send=lambda *_: None))
    monkeypatch.setattr("agent_core.workflows.executor.build_client", lambda _: SimpleNamespace(complete=lambda *_: NormalizedReply(text="Issue fixed [S1]")))
    config = WorkflowConfig(name="Weekly", repository="org/repo", provider="openai", model="test-model")
    repo = WorkflowRepository(database)
    workflow = repo.save(pid, config)
    period = RunInput(startsAt=datetime(2026, 9, 1, tzinfo=UTC), endsAt=datetime(2026, 9, 8, tzinfo=UTC))
    yield SimpleNamespace(services=services, repo=repo, workflow=workflow, period=period, user=uid, workspace=wid, project=pid, calls=calls, database=database)
    with database.session() as session:
        session.execute(delete(Workflow).where(Workflow.project_id == pid))
        session.commit()
    current_workspace_id.reset(wt)
    current_user_id.reset(ut)


def test_snapshot_claim_lock_and_library_pipeline(setup):
    s = setup
    run = s.repo.enqueue(s.workflow, s.period)
    s.repo.save(s.project, WorkflowConfig(**{**s.workflow.config, "prompt": "changed"}), s.workflow.id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: s.repo.claim(), range(2)))
    actual = [item for item in claimed if item is not None]
    assert len(actual) == 1 and actual[0].id == run.id
    assert actual[0].snapshot["revision"] == 1 and actual[0].snapshot["prompt"] != "changed"
    WorkflowExecutor(s.services).execute(actual[0])
    result, steps = s.repo.detail(s.project, run.id)
    assert result.status == "succeeded" and result.artifact_id
    assert [step.status for step in steps] == ["succeeded", "succeeded", "succeeded", "skipped"]
    with s.database.session() as session:
        asset = session.get(LibraryAsset, result.artifact_id)
        assert (asset.user_id, asset.workspace_id, asset.project_id) == (s.user, s.workspace, s.project)
        text = s.services.library.storage.read(asset.storage_provider, asset.stored_name, asset.storage_file_id).decode()
        assert "https://github.com/org/repo/issues/1" in text and "Trạng thái tại lúc" in text
    assert s.calls == [(s.user, "openai")]


def test_concurrent_idempotent_enqueue_and_lease_takeover(setup):
    s = setup
    def enqueue(_):
        ut, wt = current_user_id.set(s.user), current_workspace_id.set(s.workspace)
        try:
            return s.repo.enqueue(s.workflow, s.period, "same-request").id
        finally:
            current_workspace_id.reset(wt)
            current_user_id.reset(ut)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(enqueue, range(2)))
    assert ids[0] == ids[1]
    old = s.repo.claim()
    s.repo.step(old.id, "source", "running", lease_token=old.lease_token)
    with s.database.session() as session:
        session.get(WorkflowRun, old.id).lease_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: s.repo.claim(), range(2)))
    winners = [item for item in claimed if item]
    assert len(winners) == 1 and winners[0].id == old.id
    with pytest.raises(LeaseLost):
        s.repo.step(old.id, "source", "succeeded", {"sources": []}, lease_token=old.lease_token)
    WorkflowExecutor(s.services).execute(winners[0])
    assert s.repo.detail(s.project, old.id)[0].status == "succeeded"


@pytest.mark.parametrize("case", ["empty", "provider_error", "exhausted", "email_error"])
def test_failure_and_empty_paths(setup, monkeypatch, case):
    s = setup
    if case == "empty":
        s.services.github.list_updated_issues = lambda *_: []
        monkeypatch.setattr("agent_core.workflows.executor.build_client", lambda _: pytest.fail("empty sources must not call model"))
    elif case == "provider_error":
        def fail(*_): raise RuntimeError("secret provider detail")
        monkeypatch.setattr("agent_core.workflows.executor.build_client", fail)
    elif case == "exhausted":
        monkeypatch.setattr("agent_core.workflows.executor.build_client", lambda _: SimpleNamespace(complete=lambda *_: NormalizedReply(tool_calls=[{"id": "1", "name": "unavailable", "args": {}}])))
    else:
        s.workflow.config = {**s.workflow.config, "notifyEmail": True}
        def fail_email(*_): raise RuntimeError("SMTP error")
        s.services.email.send = fail_email
    run = s.repo.enqueue(s.workflow, s.period)
    claimed = s.repo.claim()
    WorkflowExecutor(s.services).execute(claimed)
    result, steps = s.repo.detail(s.project, run.id)
    if case in {"exhausted", "provider_error"}:
        assert result.status == "failed" and result.artifact_id is None
        assert steps[1].status == "failed" and steps[2].status == "skipped"
        assert "secret" not in result.error
    else:
        assert result.status == "succeeded" and result.artifact_id
        assert steps[1 if case == "empty" else 3].status == ("skipped" if case == "empty" else "unknown")


def test_api_permissions_snapshot_and_workspace_isolation(setup):
    s = setup
    app = FastAPI()
    @app.middleware("http")
    async def identity(request, call_next):
        ut = current_user_id.set(s.user)
        wt = current_workspace_id.set(request.headers.get("X-Test-Workspace", s.workspace))
        try: return await call_next(request)
        finally:
            current_workspace_id.reset(wt)
            current_user_id.reset(ut)
    app.include_router(build_router({}, lambda: s.services))
    with TestClient(app) as client:
        base = f"/api/projects/{s.project}/workflows"
        response = client.post(base, json=s.workflow.config)
        assert response.status_code == 201
        workflow_id = response.json()["id"]
        assert client.patch(f"{base}/{workflow_id}", json={"name": "Renamed"}).json()["revision"] == 2
        response = client.post(f"{base}/{workflow_id}/runs", json=s.period.model_dump(mode="json"))
        assert response.status_code == 202
        run_id = response.json()["id"]
        assert client.get(f"/api/projects/{s.project}/workflow-runs/{run_id}").json()["snapshot"]["name"] == "Renamed"
        assert client.get(base, headers={"X-Test-Workspace": str(uuid4())}).status_code == 403
        other_workspace = str(uuid4())
        with s.database.session() as session:
            session.add(Workspace(id=other_workspace, name="Other workspace"))
            session.flush()
            session.add(WorkspaceMember(workspace_id=other_workspace, user_id=s.user, role="editor"))
            session.commit()
        assert client.get(base, headers={"X-Test-Workspace": other_workspace}).status_code == 404
        assert client.get(f"/api/projects/{s.project}/workflow-runs/{run_id}", headers={"X-Test-Workspace": other_workspace}).status_code == 404
        with s.database.session() as session:
            member = session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == s.user, WorkspaceMember.workspace_id == s.workspace))
            member.role = "viewer"
            session.commit()
        assert client.get(base).status_code == 200
        assert client.post(base, json=s.workflow.config).status_code == 403
        assert client.patch(f"{base}/{workflow_id}", json={"name": "Denied"}).status_code == 403
        assert client.post(f"{base}/{workflow_id}/runs", json=s.period.model_dump(mode="json")).status_code == 403


def test_project_report_uses_only_latest_pinned_indexed_version(setup):
    s = setup
    with s.database.session() as session:
        asset = LibraryAsset(name="Notes.md", stored_name=str(uuid4()), mime_type="text/markdown",
            size_bytes=12, source="upload", project_id=s.project, is_project_source=True,
            index_status="ready", version=2)
        session.add(asset)
        session.flush()
        session.add(ArtifactChunk(asset_id=asset.id, chunk_index=0,
            content="Verified project note", embedding=[0.0] * 384))
        session.commit()
        asset_id = asset.id
    run = SimpleNamespace(snapshot={"template": "project-report"}, project_id=s.project)
    sources = WorkflowExecutor(s.services)._collect_sources(run)
    assert len(sources) == 1 and sources[0]["body"] == "Verified project note"
    assert sources[0]["version"] == 2 and asset_id in sources[0]["url"]


def test_library_source_is_not_visible_across_workspaces(setup):
    s = setup
    with s.database.session() as session:
        asset = LibraryAsset(name="private.md", stored_name=str(uuid4()), mime_type="text/markdown",
            size_bytes=7, source="upload", project_id=s.project, is_project_source=True)
        session.add(asset)
        session.commit()
        asset_id = asset.id
    assert s.services.library.get(asset_id) is not None
    other_workspace = str(uuid4())
    with s.database.session() as session:
        session.add(Workspace(id=other_workspace, name="Other"))
        session.commit()
    token = current_workspace_id.set(other_workspace)
    try:
        assert s.services.library.get(asset_id) is None
        assert s.services.library.list(project_id=s.project, scope="project") == []
    finally:
        current_workspace_id.reset(token)


def test_connector_owner_scope_covers_lookup_and_error_status(setup):
    s = setup
    other_user = str(uuid4())
    with s.database.session() as session:
        session.add(User(id=other_user, email=f"{other_user}@example.com"))
        session.flush()
        session.add_all([ConnectorConnection(user_id=owner, workspace_id=s.workspace, connector_slug="github", encrypted_token="test", scopes=[], status="connected") for owner in (other_user, s.user)])
        session.commit()
    repo = ConnectorRepository(s.database)
    assert repo.get_connection("github", s.user).user_id == s.user
    repo.set_connection_status("github", "reauth_required", owner_id=s.user)
    assert repo.get_connection("github", s.user).status == "reauth_required"
    assert repo.get_connection("github", other_user).status == "connected"


def test_revoked_permission_stops_run_before_source_or_model(setup):
    s = setup
    run = s.repo.enqueue(s.workflow, s.period)
    claimed = s.repo.claim()
    with s.database.session() as session:
        member = session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == s.user))
        member.role = "viewer"
        session.commit()
    s.services.github.list_updated_issues = lambda *_: pytest.fail("revoked user must not fetch sources")
    WorkflowExecutor(s.services).execute(claimed)
    result, steps = s.repo.detail(s.project, run.id)
    assert result.status == "failed" and result.artifact_id is None
    assert [step.status for step in steps] == ["failed", "skipped", "skipped", "skipped"]
    assert s.calls == []
