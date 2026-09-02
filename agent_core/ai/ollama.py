"""Small Ollama HTTP boundary used by the local provider and model selector."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Base error exposed to the API without leaking urllib implementation details."""


class OllamaUnavailableError(OllamaError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaCatalog:
    """Read the models installed in the local Ollama runtime; never persist them."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, path: str, payload: dict | None = None) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"} if payload is not None else {},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode() or "{}")
        except HTTPError as exc:
            if exc.code == 404:
                raise OllamaModelNotFoundError("Model local không còn được cài trong Ollama.") from exc
            raise OllamaUnavailableError(f"Ollama trả HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OllamaUnavailableError(
                f"Không thể kết nối Ollama tại {self.base_url}. Hãy mở Ollama rồi thử lại."
            ) from exc
        except json.JSONDecodeError as exc:
            raise OllamaUnavailableError("Ollama trả về dữ liệu không hợp lệ.") from exc

    def models(self) -> tuple[str, ...]:
        payload = self._request("/api/tags")
        # Ollama may also return cloud references from its local catalog.  This
        # provider is intentionally local-only, so never expose remote_host models.
        names = [
            item.get("name", "").strip()
            for item in payload.get("models", [])
            if isinstance(item, dict) and not item.get("remote_host")
        ]
        return tuple(dict.fromkeys(name for name in names if name))

    def require_model(self, model: str) -> None:
        if model not in self.models():
            raise OllamaModelNotFoundError(
                f"Model Ollama '{model}' không được cài trên máy này. Hãy chọn một model local khác."
            )
