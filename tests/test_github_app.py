from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from agent_core.github_app import GITHUB_SLUG, GitHubAppExecutor, GitHubAppService, GitHubConnectorError
from agent_core.storage import Plugin


class FakeConnectorRepository:
    def __init__(self):
        self.connection = None
        self.states = {}
        self.events = []

    def get_connection(self, _slug):
        return self.connection

    def save_connection(self, _slug, encrypted_token, account_email, scopes, expires_at, status="connected"):
        self.connection = SimpleNamespace(id="connection-1", encrypted_token=encrypted_token, account_email=account_email, scopes=scopes, expires_at=expires_at, status=status)
        return self.connection

    def set_connection_status(self, _slug, status):
        self.connection.status = status

    def delete_connection(self, _slug):
        self.connection = None
        return True

    def create_oauth_state(self, state, connector_slug, expires_at):
        self.states[state] = SimpleNamespace(connector_slug=connector_slug, expires_at=expires_at)

    def consume_oauth_state(self, state, now):
        item = self.states.pop(state, None)
        return item if item and item.expires_at > now else None

    def audit(self, *args, **kwargs):
        self.events.append((args, kwargs))


def github(repo=None, **values):
    settings = {
        "github_app_id": "123", "github_app_slug": "agent-series-test", "github_app_private_key": "unused",
        "github_app_install_url": "https://github.com/apps/agent-series-test/installations/new",
        "connector_encryption_key": Fernet.generate_key().decode(),
    }
    settings.update(values)
    return GitHubAppService(repo or FakeConnectorRepository(), SimpleNamespace(**settings))


def test_github_install_url_saves_short_lived_state():
    repo = FakeConnectorRepository()
    parsed = urlparse(github(repo).authorization_url())
    state = parse_qs(parsed.query)["state"][0]
    assert parsed.netloc == "github.com"
    assert repo.states[state].connector_slug == GITHUB_SLUG


def test_github_installation_persists_only_encrypted_installation_id(monkeypatch):
    repo = FakeConnectorRepository()
    service = github(repo)
    state = parse_qs(urlparse(service.authorization_url()).query)["state"][0]
    monkeypatch.setattr(service, "_app_headers", lambda: {"Authorization": "Bearer app"})
    monkeypatch.setattr(service, "_github_json", lambda *_args, **_kwargs: {"account": {"login": "octo-org"}, "permissions": {"contents": "read"}, "repository_selection": "selected"})

    assert service.complete_installation("42", state)["status"] == "connected"
    assert service._fernet().decrypt(repo.connection.encrypted_token.encode()) == b'{"installation_id": "42"}'
    with pytest.raises(GitHubConnectorError):
        service.complete_installation("42", state)


def test_github_executor_exposes_read_only_tools(monkeypatch):
    repo = FakeConnectorRepository()
    service = github(repo)
    repo.connection = SimpleNamespace(id="connection-1", status="connected", encrypted_token="unused")
    monkeypatch.setattr(service, "_installation_headers", lambda: ({"Authorization": "Bearer installation"}, repo.connection))
    monkeypatch.setattr(service, "_github_json", lambda *_args, **_kwargs: {"repositories": [{"full_name": "octo/repo", "description": "Test"}]})
    tools = GitHubAppExecutor(service).tools(Plugin(id="p", slug=GITHUB_SLUG, name="GitHub", enabled=True, connection_status="connected", capabilities=["search"]))
    assert {tool.name for tool in tools} == {"list_github_repositories", "read_github_repository_file", "search_github_issues"}
    assert "octo/repo" in next(tool for tool in tools if tool.name == "list_github_repositories").func()
