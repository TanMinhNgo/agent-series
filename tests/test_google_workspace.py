from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from agent_core.google_workspace import GOOGLE_WORKSPACE_SLUG, GoogleConnectorError, GoogleWorkspaceExecutor, GoogleWorkspaceService
from agent_core.storage import Plugin


class FakeConnectorRepository:
    def __init__(self):
        self.connection = None
        self.states = {}
        self.events = []

    def get_connection(self, _slug):
        return self.connection

    def save_connection(self, _slug, encrypted_token, account_email, scopes, expires_at, status="connected"):
        self.connection = SimpleNamespace(
            id="connection-1", encrypted_token=encrypted_token, account_email=account_email,
            scopes=scopes, expires_at=expires_at, status=status,
        )
        return self.connection

    def set_connection_status(self, _slug, status):
        if self.connection:
            self.connection.status = status
        return self.connection

    def delete_connection(self, _slug):
        had_connection = self.connection is not None
        self.connection = None
        return had_connection

    def create_oauth_state(self, state, connector_slug, expires_at):
        self.states[state] = SimpleNamespace(state=state, connector_slug=connector_slug, expires_at=expires_at)

    def consume_oauth_state(self, state, now):
        item = self.states.pop(state, None)
        return item if item and item.expires_at > now else None

    def audit(self, *args, **kwargs):
        self.events.append((args, kwargs))


def connector(repo=None, **settings):
    values = {
        "google_oauth_client_id": "client-id",
        "google_oauth_client_secret": "client-secret",
        "google_oauth_redirect_uri": "http://localhost:8000/api/connectors/google/callback",
        "connector_encryption_key": Fernet.generate_key().decode(),
        "app_web_url": "http://localhost:5173",
    }
    values.update(settings)
    return GoogleWorkspaceService(repo or FakeConnectorRepository(), SimpleNamespace(**values))


def test_google_authorization_url_has_minimum_read_only_scopes_and_saved_state():
    repo = FakeConnectorRepository()
    service = connector(repo)

    parsed = urlparse(service.authorization_url())
    query = parse_qs(parsed.query)

    assert parsed.netloc == "accounts.google.com"
    assert query["access_type"] == ["offline"]
    assert "drive.readonly" in query["scope"][0]
    assert "calendar.readonly" in query["scope"][0]
    assert "gmail.readonly" in query["scope"][0]
    assert query["state"][0] in repo.states


def test_google_callback_encrypts_tokens_and_state_cannot_be_reused(monkeypatch):
    repo = FakeConnectorRepository()
    service = connector(repo)
    state = parse_qs(urlparse(service.authorization_url()).query)["state"][0]
    monkeypatch.setattr(service, "_request_token", lambda _payload: {"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600})

    result = service.complete_authorization("code", state)

    assert result["status"] == "connected"
    assert "access-secret" not in repo.connection.encrypted_token
    assert service._decode_token(repo.connection)["refresh_token"] == "refresh-secret"
    with pytest.raises(GoogleConnectorError):
        service.complete_authorization("code", state)


def test_google_executor_is_read_only_and_audits_drive_results(monkeypatch):
    repo = FakeConnectorRepository()
    service = connector(repo)
    repo.connection = SimpleNamespace(
        id="connection-1", encrypted_token="unused", account_email="me@example.com", scopes=[],
        expires_at=datetime.now(UTC) + timedelta(hours=1), status="connected",
    )
    monkeypatch.setattr(service, "_access_token", lambda: ("access", repo.connection))
    monkeypatch.setattr(service, "_http_json", lambda *_args, **_kwargs: {"files": [{"id": "file-1", "name": "Roadmap", "mimeType": "application/pdf", "modifiedTime": "2026-08-18T00:00:00Z"}]})

    tools = GoogleWorkspaceExecutor(service).tools()
    drive = next(tool for tool in tools if tool.name == "search_google_drive_files")

    assert {tool.name for tool in tools} == {
        "search_google_drive_files",
        "read_google_drive_file",
        "search_gmail_messages",
        "read_gmail_message",
        "get_upcoming_google_calendar_events",
    }
    assert "Roadmap" in drive.func("road", 50)
    assert any(event[0][1] == "tool_invoked" for event in repo.events)


def test_google_connector_requires_a_valid_encryption_key():
    service = connector(connector_encryption_key="not-a-fernet-key")

    with pytest.raises(GoogleConnectorError, match="CONNECTOR_ENCRYPTION_KEY"):
        service.authorization_url()
