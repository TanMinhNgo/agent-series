from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from agent_core.runtime.auth import AuthService, GOOGLE_AUTH_STATE_PURPOSE
from agent_core.persistence.store import User


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        google_auth_client_id="client-id",
        google_auth_client_secret="client-secret",
        google_auth_redirect_uri="http://localhost:8000/api/auth/google/callback",
        auth_session_days=14,
    )


def test_google_authorize_uses_email_as_hint_and_persists_state() -> None:
    created: list[tuple[str, str]] = []

    class Repository:
        def create_auth_oauth_state(self, state, purpose, _expires_at):
            created.append((state, purpose))

    url = AuthService(Repository(), settings()).google_authorization_url("Me@Example.com")
    query = parse_qs(urlparse(url).query)

    assert query["login_hint"] == ["me@example.com"]
    assert query["scope"] == ["openid email profile"]
    assert created[0][0] == query["state"][0]
    assert created[0][1] == GOOGLE_AUTH_STATE_PURPOSE


def test_google_signin_links_existing_user_by_verified_email(monkeypatch) -> None:
    existing = User(id="user-1", email="me@example.com", role="owner")
    created_sessions: list[tuple[str, str]] = []

    class Repository:
        def consume_auth_oauth_state(self, _state, _now):
            return GOOGLE_AUTH_STATE_PURPOSE

        def get_user_for_identity(self, _provider, _subject):
            return None

        def user_count(self):
            return 1

        def get_user_by_email(self, _email):
            return existing

        def link_or_get_identity(self, user_id, provider, subject):
            assert (user_id, provider, subject) == ("user-1", "google", "google-subject")
            return existing

        def create_session(self, user_id, token_hash, _expires_at):
            created_sessions.append((user_id, token_hash))

        def add_system_audit(self, *_args, **_kwargs):
            return None

        def claim_legacy_data(self, _user_id):
            raise AssertionError("Existing user must not claim data again")

        def ensure_personal_workspace(self, _user_id, _display_name):
            return SimpleNamespace(id="workspace-1")

        def claim_legacy_workspace_data(self, _user_id, _workspace_id):
            return None

    service = AuthService(Repository(), settings())
    monkeypatch.setattr(service, "_exchange_google_code", lambda _code: {"id_token": "unused"})
    monkeypatch.setattr(service, "_verified_google_profile", lambda _token: {
        "email": "me@example.com", "subject": "google-subject", "name": "Me",
    })

    user, raw_session = service.complete_google_sign_in("code", "state")

    assert user is existing
    assert raw_session
    assert created_sessions[0][0] == "user-1"
