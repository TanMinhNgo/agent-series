from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from agent_core.integrations.github_app import GitHubAppService, GitHubConnectorError
from agent_core.workflows.contracts import RunInput, WorkflowConfig
from agent_core.workflows.executor import WorkflowExecutor, render_citations

START = datetime(2026, 9, 1, tzinfo=UTC)
END = START + timedelta(days=7)


def issue(number, updated=None, pr=False):
    return {"number": number, "title": f"Issue {number}", "updated_at": (updated or START).isoformat(), "created_at": START.isoformat(), "state": "closed", "body": "x" * 1100, **({"pull_request": {"url": "unused"}} if pr else {})}


def connector(monkeypatch, pages):
    owners = []
    service = GitHubAppService(SimpleNamespace(audit=lambda *_: None), object())
    monkeypatch.setattr(service, "_installation_headers", lambda owner: (owners.append(owner) or {}, SimpleNamespace(id="connection")))
    monkeypatch.setattr(service, "_github_json", lambda path, _: pages[int(parse_qs(urlsplit(path).query)["page"][0]) - 1])
    return service, owners


def test_github_pagination_boundaries_dedup_and_types(monkeypatch):
    first = [issue(1, START - timedelta(seconds=1)), issue(2, START, True)] + [issue(3)] * 98
    service, owners = connector(monkeypatch, [first, [issue(3), issue(4, END)]])
    result = service.list_updated_issues("org/repo", START, END, "runner")
    assert [item["number"] for item in result] == [2, 3]
    assert result[0]["kind"] == "pr" and result[0]["url"] == "https://github.com/org/repo/pull/2"
    assert result[0]["bodyTruncated"] and len(result[0]["body"]) == 1000
    assert owners == ["runner"]


@pytest.mark.parametrize("pages", [
    [[issue(n + page * 100) for n in range(100)] for page in range(3)],
    [[issue(1)] * 100] * 10,
])
def test_github_never_silently_truncates(monkeypatch, pages):
    service, _ = connector(monkeypatch, pages)
    with pytest.raises(GitHubConnectorError, match="thu hẹp"):
        service.list_updated_issues("org/repo", START, END, "runner")


def test_empty_and_connector_failure_are_distinct(monkeypatch):
    service, _ = connector(monkeypatch, [[]])
    assert service.list_updated_issues("org/repo", START, END, "runner") == []
    def denied(*_):
        raise GitHubConnectorError("denied")
    monkeypatch.setattr(service, "_installation_headers", denied)
    with pytest.raises(GitHubConnectorError, match="denied"):
        service.list_updated_issues("org/repo", START, END, "runner")


@pytest.mark.parametrize("content", ["", "No citation", "Unknown [S9]", "[S1] https://evil.example", "[S1](javascript:alert(1))", "[S1] <a href='evil'>go</a>"])
def test_rejects_unverifiable_report_links(content):
    with pytest.raises(ValueError):
        render_citations(content, [{"id": "S1", "url": "https://github.com/org/repo/issues/1"}])


def test_resolves_source_ids():
    assert render_citations("Done [S1]", [{"id": "S1", "url": "https://github.com/org/repo/issues/1"}]) == "Done [S1](https://github.com/org/repo/issues/1)"


def test_non_github_templates_do_not_require_repository():
    assert WorkflowConfig(name="Digest", template="daily-ai-digest", provider="openai", model="test").repository is None
    assert WorkflowConfig(name="Project", template="project-report", provider="openai", model="test").repository is None


def test_digest_keeps_each_source_content_with_its_citation():
    payload = {"sources": [
        {"name": "First", "url": "https://example.com/1", "content": "first fact"},
        {"name": "Second", "url": "https://example.com/2", "content": "second fact"},
    ]}
    executor = WorkflowExecutor(SimpleNamespace(chats=SimpleNamespace(database=None),
        web_search=SimpleNamespace(require_sources=lambda _: payload)))
    run = SimpleNamespace(snapshot={"template": "daily-ai-digest", "prompt": "AI"})
    sources = executor._collect_sources(run)
    assert [item["body"] for item in sources] == ["first fact", "second fact"]
    assert [item["id"] for item in sources] == ["S1", "S2"]
    del payload["sources"][1]["content"]
    with pytest.raises(ValueError, match="thiếu nội dung"):
        executor._collect_sources(run)


def test_project_report_reads_only_pinned_indexed_content():
    from contextlib import nullcontext

    selected = SimpleNamespace(id="asset-1", name="Notes.md", version=2,
        is_project_source=True, index_status="ready")
    other = SimpleNamespace(id="asset-2", is_project_source=False)
    class Session:
        def scalars(self, statement):
            assert "asset-1" in str(statement.compile(compile_kwargs={"literal_binds": True}))
            return [SimpleNamespace(content="actual note", chunk_index=0)]
    executor = WorkflowExecutor(SimpleNamespace(chats=SimpleNamespace(database=SimpleNamespace(
        session=lambda: nullcontext(Session()))), library=SimpleNamespace(list=lambda **_: [selected, other])))
    run = SimpleNamespace(snapshot={"template": "project-report"}, project_id="project")
    sources = executor._collect_sources(run)
    assert len(sources) == 1 and sources[0]["body"] == "actual note"
    assert sources[0]["version"] == 2 and sources[0]["url"].endswith("asset-1/preview")
    selected.index_status = "queued"
    with pytest.raises(ValueError, match="chưa index"):
        executor._collect_sources(run)


def test_github_template_requires_repository():
    with pytest.raises(ValueError, match="repository"):
        WorkflowConfig(name="Weekly", template="github-weekly-summary", provider="openai", model="test")


@pytest.mark.parametrize("start,end", [("2026-09-01", "2026-09-02"), (END, START), (START, START + timedelta(days=32)), (START, datetime.now(UTC) + timedelta(days=1))])
def test_rejects_invalid_run_period(start, end):
    with pytest.raises(ValueError):
        RunInput(startsAt=start, endsAt=end)


def test_github_reauth_marks_only_the_requested_owner(monkeypatch):
    from cryptography.fernet import InvalidToken
    marked = []
    connection = SimpleNamespace(id="connection", status="connected", encrypted_token="bad")
    repo = SimpleNamespace(
        get_connection=lambda slug, owner: connection if owner == "runner" else None,
        set_connection_status=lambda slug, status, owner_id: marked.append((status, owner_id)),
    )
    def invalid(_):
        raise InvalidToken()
    service = GitHubAppService(repo, object())
    monkeypatch.setattr(service, "_fernet", lambda: SimpleNamespace(decrypt=invalid))
    with pytest.raises(GitHubConnectorError, match="kết nối lại"):
        service._installation_headers("runner")
    assert marked == [("reauth_required", "runner")]


def test_connector_repository_keeps_other_workspace_member_connection_unchanged():
    from agent_core.persistence.store import Base, Database, User, Workspace, ConnectorConnection, ConnectorRepository, current_user_id, current_workspace_id
    db = Database("sqlite://")
    Base.metadata.create_all(db.engine, tables=[User.__table__, Workspace.__table__, ConnectorConnection.__table__])
    user_token, workspace_token = current_user_id.set("runner"), current_workspace_id.set("team")
    try:
        with db.session() as session:
            session.add_all([User(id=owner, email=f"{owner}@example.com") for owner in ("other", "runner")])
            session.add(Workspace(id="team", name="Team"))
            session.flush()
            session.add_all([ConnectorConnection(user_id=owner, workspace_id="team", connector_slug="github", encrypted_token="test", scopes=[], status="connected") for owner in ("other", "runner")])
            session.commit()
        repo = ConnectorRepository(db)
        assert repo.get_connection("github", "runner").user_id == "runner"
        repo.set_connection_status("github", "reauth_required", owner_id="runner")
        assert repo.get_connection("github", "runner").status == "reauth_required"
        assert repo.get_connection("github", "other").status == "connected"
    finally:
        current_workspace_id.reset(workspace_token)
        current_user_id.reset(user_token)
        db.engine.dispose()
