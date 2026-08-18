"""Encrypted, user-scoped BYOK credentials for cloud model providers."""

from __future__ import annotations

from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings
from .storage import AuthRepository, UserProviderCredential

SUPPORTED_PROVIDERS = {"gemini", "openai", "anthropic"}


class CredentialError(ValueError):
    pass


class UserCredentialService:
    def __init__(self, repository: AuthRepository, settings: Settings):
        self.repository, self.settings = repository, settings

    def _fernet(self) -> Fernet:
        if not self.settings.user_credential_encryption_key:
            raise CredentialError("Server chưa cấu hình USER_CREDENTIAL_ENCRYPTION_KEY để lưu API key an toàn.")
        try:
            return Fernet(self.settings.user_credential_encryption_key.encode())
        except (TypeError, ValueError) as exc:
            raise CredentialError("USER_CREDENTIAL_ENCRYPTION_KEY không hợp lệ.") from exc

    @staticmethod
    def _check_provider(provider: str) -> None:
        if provider not in SUPPORTED_PROVIDERS:
            raise CredentialError("Provider không hỗ trợ.")

    @staticmethod
    def key_hint(api_key: str) -> str:
        return f"••••{api_key[-4:]}" if len(api_key) >= 4 else "••••"

    def list_metadata(self, user_id: str) -> list[UserProviderCredential]:
        return self.repository.user_provider_credentials(user_id)

    def api_key(self, user_id: str | None, provider: str) -> str | None:
        if not user_id:
            return None
        item = self.repository.user_provider_credential(user_id, provider)
        if item is None:
            return None
        try:
            return self._fernet().decrypt(item.ciphertext.encode()).decode()
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise CredentialError("Không thể đọc API key đã lưu. Hãy thêm lại key.") from exc

    def save(self, user_id: str, provider: str, api_key: str) -> UserProviderCredential:
        self._check_provider(provider)
        value = api_key.strip()
        if len(value) < 8:
            raise CredentialError("API key không hợp lệ.")
        self.validate(provider, value)
        return self.repository.save_user_provider_credential(user_id, provider, self._fernet().encrypt(value.encode()).decode(), self.key_hint(value))

    def delete(self, user_id: str, provider: str) -> bool:
        self._check_provider(provider)
        return self.repository.delete_user_provider_credential(user_id, provider)

    def validate(self, provider: str, api_key: str) -> None:
        self._check_provider(provider)
        urls = {
            "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": api_key}),
            "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {api_key}"}),
        }
        if provider == "anthropic":
            # Anthropic has no zero-cost model-list endpoint. A minimal request validates authentication.
            model = self.settings.provider_models["anthropic"][0]
            import json
            body = json.dumps({"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}).encode()
            request = Request("https://api.anthropic.com/v1/messages", data=body, headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, method="POST")
        else:
            url, headers = urls[provider]
            request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=12) as response:
                if not 200 <= response.status < 300:
                    raise CredentialError("Provider từ chối API key.")
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise CredentialError("API key không hợp lệ hoặc không có quyền truy cập.") from exc
            raise CredentialError("Không thể xác minh API key với provider lúc này.") from exc
        except URLError as exc:
            raise CredentialError("Không thể kết nối provider để xác minh API key.") from exc
