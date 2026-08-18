"""Read-only Google Workspace connector.

The module intentionally uses small HTTPS calls instead of a broad Google SDK.  That
keeps the granted permissions visible, limits the dependency surface, and makes the
two read-only operations easy to audit.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings
from .storage import ConnectorConnection, ConnectorRepository, Plugin
from .tools.base import ToolSpec

GOOGLE_WORKSPACE_SLUG = "google-workspace"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
)


class GoogleConnectorError(RuntimeError):
    pass


class GoogleWorkspaceService:
    def __init__(self, repository: ConnectorRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.google_oauth_client_id
            and self.settings.google_oauth_client_secret
            and self.settings.connector_encryption_key
        )

    def _fernet(self) -> Fernet:
        if not self.configured:
            raise GoogleConnectorError("Google Workspace chưa được cấu hình. Kiểm tra OAuth Client và CONNECTOR_ENCRYPTION_KEY trong .env.")
        try:
            return Fernet(self.settings.connector_encryption_key.encode())
        except (ValueError, TypeError) as exc:
            raise GoogleConnectorError("CONNECTOR_ENCRYPTION_KEY không hợp lệ. Hãy tạo Fernet key mới theo .env.example.") from exc

    def status(self) -> dict[str, Any]:
        item = self.repository.get_connection(GOOGLE_WORKSPACE_SLUG)
        return {
            "connectorSlug": GOOGLE_WORKSPACE_SLUG,
            "configured": self.configured,
            "status": item.status if item else "not_connected",
            "accountEmail": item.account_email if item else None,
            "scopes": item.scopes if item else [],
            "expiresAt": item.expires_at.isoformat() if item and item.expires_at else None,
        }

    def authorization_url(self) -> str:
        self._fernet()
        state = token_urlsafe(32)
        self.repository.create_oauth_state(state, GOOGLE_WORKSPACE_SLUG, datetime.now(UTC) + timedelta(minutes=10))
        params = {
            "client_id": self.settings.google_oauth_client_id,
            "redirect_uri": self.settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def complete_authorization(self, code: str, state: str) -> dict[str, Any]:
        consumed = self.repository.consume_oauth_state(state, datetime.now(UTC))
        if consumed is None or consumed.connector_slug != GOOGLE_WORKSPACE_SLUG:
            raise GoogleConnectorError("Phiên kết nối đã hết hạn hoặc không hợp lệ. Hãy bắt đầu lại từ trang Plugin.")
        try:
            token = self._request_token({
                "code": code,
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": self.settings.google_oauth_client_secret,
                "redirect_uri": self.settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            })
            self._save_token(token)
        except GoogleConnectorError as exc:
            self.repository.audit(GOOGLE_WORKSPACE_SLUG, "oauth_failed", summary=self._safe_error(exc))
            raise
        self.repository.audit(GOOGLE_WORKSPACE_SLUG, "oauth_connected", summary="Đã cấp quyền chỉ đọc Drive metadata và Calendar.")
        return self.status()

    def disconnect(self) -> bool:
        current = self.repository.get_connection(GOOGLE_WORKSPACE_SLUG)
        removed = self.repository.delete_connection(GOOGLE_WORKSPACE_SLUG)
        self.repository.audit(
            GOOGLE_WORKSPACE_SLUG,
            "oauth_disconnected",
            connection_id=current.id if current else None,
            summary="Đã xóa token cục bộ.",
        )
        return removed

    def _request_token(self, payload: dict[str, str]) -> dict[str, Any]:
        try:
            return self._http_json(GOOGLE_TOKEN_URL, method="POST", data=payload)
        except GoogleConnectorError:
            raise

    def _save_token(self, token: dict[str, Any], previous: ConnectorConnection | None = None) -> ConnectorConnection:
        if not token.get("access_token"):
            raise GoogleConnectorError("Google không trả access token cho phiên kết nối này.")
        if previous and not token.get("refresh_token"):
            token["refresh_token"] = self._decode_token(previous).get("refresh_token")
        encrypted = self._fernet().encrypt(json.dumps(token).encode()).decode()
        expires_at = datetime.now(UTC) + timedelta(seconds=int(token.get("expires_in", 3600)))
        scopes = str(token.get("scope") or " ".join(SCOPES)).split()
        return self.repository.save_connection(
            GOOGLE_WORKSPACE_SLUG,
            encrypted,
            self._email_from_id_token(token.get("id_token")) or (previous.account_email if previous else None),
            scopes,
            expires_at,
        )

    def _decode_token(self, connection: ConnectorConnection) -> dict[str, Any]:
        try:
            return json.loads(self._fernet().decrypt(connection.encrypted_token.encode()).decode())
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.repository.set_connection_status(GOOGLE_WORKSPACE_SLUG, "reauth_required")
            raise GoogleConnectorError("Không thể đọc token Google đã lưu. Hãy kết nối lại.") from exc

    def _access_token(self) -> tuple[str, ConnectorConnection]:
        connection = self.repository.get_connection(GOOGLE_WORKSPACE_SLUG)
        if connection is None or connection.status != "connected":
            raise GoogleConnectorError("Google Workspace chưa kết nối hoặc cần kết nối lại.")
        if connection.expires_at and connection.expires_at <= datetime.now(UTC) + timedelta(seconds=60):
            token = self._decode_token(connection)
            refresh_token = token.get("refresh_token")
            if not refresh_token:
                self.repository.set_connection_status(GOOGLE_WORKSPACE_SLUG, "reauth_required")
                raise GoogleConnectorError("Phiên Google đã hết hạn. Hãy kết nối lại.")
            try:
                connection = self._save_token(self._request_token({
                    "client_id": self.settings.google_oauth_client_id,
                    "client_secret": self.settings.google_oauth_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }), previous=connection)
            except GoogleConnectorError as exc:
                self.repository.set_connection_status(GOOGLE_WORKSPACE_SLUG, "reauth_required")
                self.repository.audit(GOOGLE_WORKSPACE_SLUG, "token_refresh_failed", connection.id, summary=self._safe_error(exc))
                raise GoogleConnectorError("Không thể làm mới phiên Google. Hãy kết nối lại.") from exc
        return self._decode_token(connection)["access_token"], connection

    def search_drive_files(self, query: str, limit: int = 10) -> str:
        query = query.strip()
        if not query:
            return "Hãy cung cấp từ khóa để tìm Drive."
        access_token, connection = self._access_token()
        safe_query = query.replace("'", "\\'")
        params = {
            "q": f"trashed = false and name contains '{safe_query}'",
            "pageSize": str(max(1, min(limit, 10))),
            "orderBy": "modifiedTime desc",
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
        }
        try:
            payload = self._http_json(f"{DRIVE_FILES_URL}?{urlencode(params)}", headers={"Authorization": f"Bearer {access_token}"})
        except GoogleConnectorError as exc:
            self.repository.audit(GOOGLE_WORKSPACE_SLUG, "tool_failed", connection.id, "search_google_drive_files", self._safe_error(exc))
            raise
        files = payload.get("files", [])
        self.repository.audit(GOOGLE_WORKSPACE_SLUG, "tool_invoked", connection.id, "search_google_drive_files", f"Tìm metadata Drive: {len(files)} kết quả.")
        if not files:
            return "Không tìm thấy file Drive phù hợp."
        return "\n".join(
            f"- [{item.get('name', 'Không tên')}]({item.get('webViewLink') or 'https://drive.google.com/open?id=' + item.get('id', '')}) — {item.get('mimeType', 'unknown')}, cập nhật {item.get('modifiedTime', 'không rõ')}"
            for item in files
        )

    def upcoming_calendar_events(self, days: int = 7, limit: int = 10) -> str:
        access_token, connection = self._access_token()
        now = datetime.now(UTC)
        params = {
            "timeMin": now.isoformat().replace("+00:00", "Z"),
            "timeMax": (now + timedelta(days=max(1, min(days, 31)))).isoformat().replace("+00:00", "Z"),
            "maxResults": str(max(1, min(limit, 10))),
            "singleEvents": "true",
            "orderBy": "startTime",
            "fields": "items(id,summary,start,end,htmlLink,location)",
        }
        try:
            payload = self._http_json(f"{CALENDAR_EVENTS_URL}?{urlencode(params)}", headers={"Authorization": f"Bearer {access_token}"})
        except GoogleConnectorError as exc:
            self.repository.audit(GOOGLE_WORKSPACE_SLUG, "tool_failed", connection.id, "get_upcoming_google_calendar_events", self._safe_error(exc))
            raise
        events = payload.get("items", [])
        self.repository.audit(GOOGLE_WORKSPACE_SLUG, "tool_invoked", connection.id, "get_upcoming_google_calendar_events", f"Đọc lịch: {len(events)} sự kiện.")
        if not events:
            return "Không có sự kiện sắp tới trong khoảng thời gian đã chọn."
        return "\n".join(
            f"- [{item.get('summary') or 'Không có tiêu đề'}]({item.get('htmlLink') or '#'}) — {(item.get('start') or {}).get('dateTime') or (item.get('start') or {}).get('date') or 'không rõ thời gian'}"
            for item in events
        )

    @staticmethod
    def _email_from_id_token(id_token: Any) -> str | None:
        if not isinstance(id_token, str) or id_token.count(".") < 2:
            return None
        try:
            payload = id_token.split(".")[1] + "=" * (-len(id_token.split(".")[1]) % 4)
            return json.loads(base64.urlsafe_b64decode(payload)).get("email")
        except (ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _safe_error(error: Exception) -> str:
        return str(error).replace("\n", " ")[:500]

    @staticmethod
    def _http_json(url: str, method: str = "GET", data: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
        body = urlencode(data).encode() if data else None
        request = Request(url, data=body, method=method, headers={"Accept": "application/json", **({"Content-Type": "application/x-www-form-urlencoded"} if body else {}), **(headers or {})})
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - URLs are fixed Google endpoints.
                return json.loads(response.read().decode())
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("error_description") or "Google từ chối yêu cầu."
            except Exception:  # noqa: BLE001
                detail = "Google từ chối yêu cầu."
            raise GoogleConnectorError(str(detail)) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GoogleConnectorError("Không thể kết nối Google Workspace lúc này.") from exc


class GoogleWorkspaceExecutor:
    slug = GOOGLE_WORKSPACE_SLUG

    def __init__(self, connector: GoogleWorkspaceService):
        self.connector = connector

    def tools(self, plugin: Plugin) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="search_google_drive_files",
                description="Tìm tối đa 10 file theo tên trong Google Drive đã kết nối. Chỉ đọc metadata và link mở file.",
                parameters={"type": "object", "properties": {"query": {"type": "string", "description": "Từ khóa tên file"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["query"]},
                func=self.connector.search_drive_files,
            ),
            ToolSpec(
                name="get_upcoming_google_calendar_events",
                description="Đọc tối đa 10 sự kiện sắp tới từ Google Calendar đã kết nối. Chỉ đọc, không tạo hoặc sửa lịch.",
                parameters={"type": "object", "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 31}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}}},
                func=self.connector.upcoming_calendar_events,
            ),
        ]
