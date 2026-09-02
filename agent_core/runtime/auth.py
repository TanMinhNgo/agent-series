"""Application identity: Google Sign-In and opaque database-backed sessions."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import verify_oauth2_token

from .config import Settings
from ..persistence.store import AuthRepository, User

SESSION_COOKIE = "agent_series_session"
LOGGER = logging.getLogger(__name__)
GOOGLE_AUTH_PROVIDER = "google"
GOOGLE_AUTH_STATE_PURPOSE = "google-auth"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_SCOPES = ("openid", "email", "profile")


class AuthError(RuntimeError):
    pass


class AuthService:
    def __init__(self, repository: AuthRepository, settings: Settings):
        self.repository, self.settings = repository, settings

    @property
    def google_configured(self) -> bool:
        return bool(self.settings.google_auth_client_id and self.settings.google_auth_client_secret)

    def google_authorization_url(self, email: str | None = None) -> str:
        if not self.google_configured:
            raise AuthError("Google Sign-In chưa được cấu hình. Thêm GOOGLE_AUTH_CLIENT_ID và GOOGLE_AUTH_CLIENT_SECRET vào .env.")
        state = secrets.token_urlsafe(32)
        self.repository.create_auth_oauth_state(
            state,
            GOOGLE_AUTH_STATE_PURPOSE,
            datetime.now(UTC) + timedelta(minutes=10),
        )
        params = {
            "client_id": self.settings.google_auth_client_id,
            "redirect_uri": self.settings.google_auth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_AUTH_SCOPES),
            "state": state,
            "prompt": "select_account",
        }
        if email:
            normalized = email.strip().lower()
            if "@" not in normalized or len(normalized) > 320:
                raise AuthError("Email không hợp lệ.")
            params["login_hint"] = normalized
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def complete_google_sign_in(self, code: str, state: str) -> tuple[User, str]:
        if not self.google_configured:
            raise AuthError("Google Sign-In chưa được cấu hình.")
        purpose = self.repository.consume_auth_oauth_state(state, datetime.now(UTC))
        if purpose != GOOGLE_AUTH_STATE_PURPOSE:
            raise AuthError("Phiên đăng nhập Google đã hết hạn hoặc không hợp lệ. Hãy thử lại.")
        token = self._exchange_google_code(code)
        profile = self._verified_google_profile(token.get("id_token"))
        user = self.repository.get_user_for_identity(GOOGLE_AUTH_PROVIDER, profile["subject"])
        if user is None:
            first_user = self.repository.user_count() == 0
            user = self.repository.get_user_by_email(profile["email"])
            if user is None:
                user = self.repository.create_user(
                    profile["email"],
                    display_name=profile["name"],
                    role="owner" if first_user else "member",
                )
            user = self.repository.link_or_get_identity(
                user.id,
                GOOGLE_AUTH_PROVIDER,
                profile["subject"],
            )
            if first_user:
                self.repository.claim_legacy_data(user.id)
        personal_workspace = self.repository.ensure_personal_workspace(user.id, user.display_name)
        # Rows created before the workspace migration (including previously
        # claimed local data) become visible in the user's Personal workspace.
        self.repository.claim_legacy_workspace_data(user.id, personal_workspace.id)
        if user.is_active is False:
            raise AuthError("Tài khoản này đã bị vô hiệu hóa. Hãy liên hệ system admin.")
        raw_session = secrets.token_urlsafe(32)
        self.repository.create_session(
            user.id,
            self._hash(raw_session),
            datetime.now(UTC) + timedelta(days=max(1, self.settings.auth_session_days)),
        )
        self.repository.add_system_audit("google_sign_in", subject_user_id=user.id, summary="Đăng nhập Google thành công.")
        return user, raw_session

    @staticmethod
    def _hash(token: str) -> str:
        import hashlib

        return hashlib.sha256(token.encode()).hexdigest()

    def _exchange_google_code(self, code: str) -> dict[str, Any]:
        try:
            body = urlencode({
                "code": code,
                "client_id": self.settings.google_auth_client_id,
                "client_secret": self.settings.google_auth_client_secret,
                "redirect_uri": self.settings.google_auth_redirect_uri,
                "grant_type": "authorization_code",
            }).encode()
            request = Request(
                GOOGLE_TOKEN_URL,
                data=body,
                method="POST",
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed Google endpoint.
                import json

                return json.loads(response.read().decode())
        except HTTPError as exc:
            raise AuthError("Google từ chối phiên đăng nhập này. Hãy thử lại.") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise AuthError("Không thể kết nối Google lúc này. Hãy thử lại.") from exc

    def _verified_google_profile(self, raw_id_token: Any) -> dict[str, str | None]:
        if not isinstance(raw_id_token, str):
            raise AuthError("Google không trả thông tin nhận diện hợp lệ.")
        try:
            # A small tolerance prevents a valid token being rejected when the
            # local Windows clock trails Google's clock by only a few seconds.
            claims = verify_oauth2_token(
                raw_id_token,
                GoogleRequest(),
                self.settings.google_auth_client_id,
                clock_skew_in_seconds=30,
            )
        except Exception as exc:  # Google auth exposes several non-stable exception types.
            LOGGER.warning("Google ID token verification failed", exc_info=exc)
            raise AuthError("Không thể xác minh danh tính Google. Hãy thử đăng nhập lại.") from exc
        email = str(claims.get("email") or "").strip().lower()
        subject = str(claims.get("sub") or "").strip()
        if not email or not subject or claims.get("email_verified") is not True:
            raise AuthError("Google account cần có email đã xác minh để đăng nhập.")
        name = str(claims.get("name") or "").strip() or None
        return {"email": email, "subject": subject, "name": name}

    def session_user(self, raw_session: str | None) -> User | None:
        user = self.repository.user_for_session(self._hash(raw_session), datetime.now(UTC)) if raw_session else None
        return user if user and user.is_active else None

    def is_system_admin(self, user: User) -> bool:
        return bool(self.settings.system_admin_email and user.email.lower() == self.settings.system_admin_email)

    def logout(self, raw_session: str | None) -> None:
        if raw_session:
            self.repository.revoke_session(self._hash(raw_session))
