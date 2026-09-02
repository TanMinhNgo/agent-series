"""Read-only GitHub App connector scoped to repositories selected at install time."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from ..runtime.config import Settings
from ..persistence.store import ConnectorConnection, ConnectorRepository, Plugin
from ..tools.base import ToolSpec

GITHUB_SLUG = "github"
GITHUB_API_URL = "https://api.github.com"


class GitHubConnectorError(RuntimeError):
    pass


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class GitHubAppService:
    def __init__(self, repository: ConnectorRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.github_app_id and self.settings.github_app_slug and self.settings.github_app_private_key and self.settings.connector_encryption_key)

    def _fernet(self) -> Fernet:
        if not self.configured:
            raise GitHubConnectorError("GitHub App chưa được cấu hình. Kiểm tra GITHUB_APP_ID, GITHUB_APP_SLUG, GITHUB_APP_PRIVATE_KEY và CONNECTOR_ENCRYPTION_KEY trong .env.")
        try:
            return Fernet(self.settings.connector_encryption_key.encode())
        except (ValueError, TypeError) as exc:
            raise GitHubConnectorError("CONNECTOR_ENCRYPTION_KEY không hợp lệ. Hãy tạo Fernet key mới theo .env.example.") from exc

    def status(self) -> dict[str, Any]:
        item = self.repository.get_connection(GITHUB_SLUG)
        return {
            "connectorSlug": GITHUB_SLUG,
            "configured": self.configured,
            "status": item.status if item else "not_connected",
            "accountEmail": item.account_email if item else None,
            "scopes": item.scopes if item else [],
            "expiresAt": None,
        }

    def authorization_url(self) -> str:
        self._fernet()
        state = token_urlsafe(32)
        self.repository.create_oauth_state(state, GITHUB_SLUG, datetime.now(UTC) + timedelta(minutes=10))
        base = self.settings.github_app_install_url or f"https://github.com/apps/{self.settings.github_app_slug}/installations/new"
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}{urlencode({'state': state})}"

    def complete_installation(self, installation_id: str, state: str) -> dict[str, Any]:
        consumed = self.repository.consume_oauth_state(state, datetime.now(UTC))
        if consumed is None or consumed.connector_slug != GITHUB_SLUG:
            raise GitHubConnectorError("Phiên kết nối GitHub đã hết hạn hoặc không hợp lệ. Hãy bắt đầu lại từ trang Plugin.")
        if not installation_id.isdigit():
            raise GitHubConnectorError("GitHub installation ID không hợp lệ.")
        try:
            installation = self._github_json(f"/app/installations/{installation_id}", self._app_headers())
            account = installation.get("account") or {}
            encrypted = self._fernet().encrypt(json.dumps({"installation_id": str(installation_id)}).encode()).decode()
            connection = self.repository.save_connection(
                GITHUB_SLUG, encrypted, account.get("login") or account.get("email"),
                [f"repository_selection:{installation.get('repository_selection', 'selected')}", *sorted((installation.get("permissions") or {}).keys())], None,
            )
        except GitHubConnectorError as exc:
            self.repository.audit(GITHUB_SLUG, "oauth_failed", summary=self._safe_error(exc))
            raise
        self.repository.audit(GITHUB_SLUG, "oauth_connected", connection.id, summary="Đã kết nối GitHub App chỉ đọc.")
        return self.status()

    def disconnect(self) -> bool:
        current = self.repository.get_connection(GITHUB_SLUG)
        removed = self.repository.delete_connection(GITHUB_SLUG)
        self.repository.audit(GITHUB_SLUG, "oauth_disconnected", current.id if current else None, summary="Đã xóa liên kết GitHub App cục bộ.")
        return removed

    def _app_headers(self) -> dict[str, str]:
        now = int(datetime.now(UTC).timestamp())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _b64url(json.dumps({"iat": now - 30, "exp": now + 540, "iss": self.settings.github_app_id}, separators=(",", ":")).encode())
        try:
            key = serialization.load_pem_private_key(self.settings.github_app_private_key.encode(), password=None)
            signature = key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
        except (TypeError, ValueError) as exc:
            raise GitHubConnectorError("GITHUB_APP_PRIVATE_KEY không phải PEM RSA hợp lệ.") from exc
        return {"Authorization": f"Bearer {header}.{payload}.{_b64url(signature)}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "agent-series"}

    def _installation_headers(self) -> tuple[dict[str, str], ConnectorConnection]:
        connection = self.repository.get_connection(GITHUB_SLUG)
        if connection is None or connection.status != "connected":
            raise GitHubConnectorError("GitHub chưa kết nối hoặc cần kết nối lại.")
        try:
            payload = json.loads(self._fernet().decrypt(connection.encrypted_token.encode()).decode())
            installation_id = str(payload["installation_id"])
            token = self._github_json(f"/app/installations/{installation_id}/access_tokens", self._app_headers(), method="POST")
        except (InvalidToken, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.repository.set_connection_status(GITHUB_SLUG, "reauth_required")
            raise GitHubConnectorError("Không thể đọc liên kết GitHub đã lưu. Hãy kết nối lại.") from exc
        except GitHubConnectorError:
            self.repository.set_connection_status(GITHUB_SLUG, "reauth_required")
            raise
        return {"Authorization": f"Bearer {token['token']}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "agent-series"}, connection

    def list_repositories(self, limit: int = 10) -> str:
        headers, connection = self._installation_headers()
        payload = self._github_json(f"/installation/repositories?{urlencode({'per_page': max(1, min(limit, 30))})}", headers)
        repositories = payload.get("repositories", [])
        self.repository.audit(GITHUB_SLUG, "tool_invoked", connection.id, "list_github_repositories", f"Liệt kê {len(repositories)} repository GitHub.")
        return "\n".join(f"- {item.get('full_name')} — {item.get('description') or 'Không có mô tả'}" for item in repositories) or "GitHub App chưa được cấp repository nào."

    def read_repository_file(self, repository: str, path: str, ref: str | None = None) -> str:
        headers, connection = self._installation_headers()
        suffix = f"?{urlencode({'ref': ref})}" if ref else ""
        repository_path = self._repository_path(repository)
        file_path = self._repository_file_path(path)
        item = self._github_json(f"/repos/{repository_path}/contents/{file_path}{suffix}", headers)
        if item.get("type") != "file" or not item.get("content"):
            return "Đường dẫn này không phải file văn bản có thể đọc trực tiếp."
        content = base64.b64decode(item["content"]).decode("utf-8", errors="replace")[:20_000]
        self.repository.audit(GITHUB_SLUG, "tool_invoked", connection.id, "read_github_repository_file", f"Đọc {repository}/{path}.")
        return content

    def search_repository_issues(self, repository: str, query: str, limit: int = 10) -> str:
        headers, connection = self._installation_headers()
        payload = self._github_json(f"/repos/{repository}/issues?{urlencode({'state': 'all', 'per_page': max(1, min(limit, 30))})}", headers)
        term = query.strip().lower()
        issues = [item for item in payload if term in f"{item.get('title', '')} {item.get('body', '')}".lower()][:limit]
        self.repository.audit(GITHUB_SLUG, "tool_invoked", connection.id, "search_github_issues", f"Tìm {len(issues)} issue/PR trong {repository}.")
        return "\n".join(f"- #{item.get('number')} {item.get('title')} — {item.get('html_url')}" for item in issues) or "Không tìm thấy issue hoặc pull request phù hợp."

    @staticmethod
    def _safe_error(error: Exception) -> str:
        return str(error).replace("\n", " ")[:500]

    @staticmethod
    def _repository_path(repository: str) -> str:
        parts = repository.split("/")
        if len(parts) != 2 or not all(part and all(char.isalnum() or char in ".-_" for char in part) for part in parts):
            raise GitHubConnectorError("Repository phải có dạng owner/repository hợp lệ.")
        return "/".join(quote(part, safe="-._~") for part in parts)

    @staticmethod
    def _repository_file_path(path: str) -> str:
        parts = [part for part in path.replace("\\", "/").split("/") if part]
        if not parts or any(part in {".", ".."} for part in parts):
            raise GitHubConnectorError("Đường dẫn file GitHub không hợp lệ.")
        return "/".join(quote(part, safe="-._~") for part in parts)

    @staticmethod
    def _github_json(path: str, headers: dict[str, str], method: str = "GET") -> Any:
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith("/"):
            raise GitHubConnectorError("Đường dẫn GitHub API không hợp lệ.")
        api = urlsplit(GITHUB_API_URL)
        request_url = urlunsplit((api.scheme, api.netloc, parsed.path, parsed.query, ""))
        request = Request(request_url, method=method, headers=headers)
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed GitHub API endpoint.
                return json.loads(response.read().decode())
        except HTTPError as exc:
            if exc.code in {401, 403, 404}:
                raise GitHubConnectorError("GitHub từ chối yêu cầu hoặc App chưa được cấp quyền đọc resource này.") from exc
            raise GitHubConnectorError("GitHub không thể xử lý yêu cầu lúc này.") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GitHubConnectorError("Không thể kết nối GitHub lúc này.") from exc


class GitHubAppExecutor:
    slug = GITHUB_SLUG

    def __init__(self, connector: GitHubAppService):
        self.connector = connector

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name="list_github_repositories", description="Liệt kê repository GitHub mà GitHub App đã được cấp quyền đọc.", parameters={"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}}}, func=self.connector.list_repositories),
            ToolSpec(name="read_github_repository_file", description="Đọc nội dung file văn bản trong repository GitHub đã cấp quyền. Chỉ đọc.", parameters={"type": "object", "properties": {"repository": {"type": "string", "description": "owner/repository"}, "path": {"type": "string"}, "ref": {"type": "string"}}, "required": ["repository", "path"]}, func=self.connector.read_repository_file),
            ToolSpec(name="search_github_issues", description="Tìm issue hoặc pull request trong một repository GitHub đã cấp quyền. Chỉ đọc.", parameters={"type": "object", "properties": {"repository": {"type": "string", "description": "owner/repository"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 30}}, "required": ["repository", "query"]}, func=self.connector.search_repository_issues),
        ]
