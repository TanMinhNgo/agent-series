"""Tavily-backed web search used only for grounded external citations."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..tools.base import ToolSpec

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"


def _safe_external_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value.strip())
    return value.strip() if parsed.scheme == "https" and parsed.netloc else None


class WebSourceUnavailable(RuntimeError):
    """Raised when a run demanding fresh web sources cannot obtain any."""


class WebSearchService:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def require_sources(self, query: str, max_results: int = 3) -> dict[str, Any]:
        """Fetch sources for a run that must be grounded, or refuse to continue."""
        if not self.enabled:
            raise WebSourceUnavailable("Tìm web chưa được cấu hình (thiếu TAVILY_API_KEY).")
        raw = self.search(query, max_results)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise WebSourceUnavailable(raw.strip("[]") or "Không lấy được nguồn web.") from None
        if not payload.get("sources"):
            raise WebSourceUnavailable("Không có nguồn web đáng tin cậy cho yêu cầu này.")
        return payload

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps({"api_key": self.api_key, **body}).encode("utf-8")
        with urlopen(Request(url, data=data, headers={"Content-Type": "application/json"}), timeout=20) as response:  # noqa: S310 - fixed Tavily endpoints
            return json.loads(response.read().decode("utf-8"))

    def read_url(self, url: str) -> str:
        """Read one page via Tavily Extract (Tavily fetches it, so no SSRF surface here)."""
        if not self.enabled:
            return "[Lỗi] Đọc web chưa được cấu hình."
        safe = _safe_external_url(url)
        if not safe:
            return "[Lỗi] Chỉ đọc được URL https hợp lệ."
        try:
            payload = self._post(TAVILY_EXTRACT_URL, {"urls": [safe]})
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return f"[Lỗi] Không thể đọc trang: {exc}"
        results = payload.get("results") or []
        text = str(results[0].get("raw_content") or "").strip() if results else ""
        if not text:
            return "[Lỗi] Không đọc được nội dung trang này (có thể cần đăng nhập, như Facebook, hoặc bị chặn)."
        source = {"name": safe, "url": safe, "kind": "external", "content": text[:12000]}
        return json.dumps({"sources": [source], "context": f"[{safe}]({safe})\n{text[:12000]}"}, ensure_ascii=False)

    def search(self, query: str, max_results: int = 3) -> str:
        if not self.enabled:
            return "[Lỗi] Tìm web chưa được cấu hình."
        if not query.strip():
            return "[Lỗi] Câu hỏi tìm web đang trống."
        try:
            response_payload = self._post(TAVILY_SEARCH_URL, {"query": query.strip(), "search_depth": "basic", "max_results": max(1, min(int(max_results), 3)), "include_answer": False, "include_raw_content": False})
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return f"[Lỗi] Không thể tìm web: {exc}"

        sources: list[dict[str, str]] = []
        context: list[str] = []
        for item in response_payload.get("results", []):
            url = _safe_external_url(item.get("url"))
            if not url:
                continue
            name = str(item.get("title") or url).strip()[:300]
            snippet = str(item.get("content") or "").strip()[:4000]
            sources.append({"name": name, "url": url, "kind": "external", "content": snippet})
            context.append(f"[{name}]({url})\n{snippet}")
        if not sources:
            return "[Không có kết quả web đáng tin cậy.]"
        return json.dumps({"sources": sources, "context": "\n\n".join(context)}, ensure_ascii=False)


def build_web_search_tool(service: WebSearchService) -> ToolSpec | None:
    if not service.enabled:
        return None
    return ToolSpec(
        name="search_web",
        description="Tìm nguồn web bên ngoài bằng Tavily. Chỉ dùng khi Thư viện không có hoặc không đủ thông tin. Chỉ dùng các URL được tool trả về làm nguồn.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Câu tìm kiếm cụ thể."},
                "max_results": {"type": "integer", "description": "1 đến 3, mặc định 3."},
            },
            "required": ["query"],
        },
        func=service.search,
    )


def build_read_url_tool(service: WebSearchService) -> ToolSpec | None:
    if not service.enabled:
        return None
    return ToolSpec(
        name="read_url",
        description="Đọc nội dung một trang web/bài viết/video (ví dụ YouTube) từ URL https người dùng cung cấp. Trang cần đăng nhập như Facebook thường không đọc được.",
        parameters={"type": "object", "properties": {"url": {"type": "string", "description": "URL https đầy đủ."}}, "required": ["url"]},
        func=service.read_url,
    )


def sources_from_web_steps(steps: list[Any]) -> list[dict[str, str]]:
    """Extract safe persisted sources from completed ``search_web`` tool calls."""
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for step in steps:
        if getattr(step, "tool", None) not in {"search_web", "read_url"}:
            continue
        try:
            payload = json.loads(getattr(step, "result", ""))
        except (TypeError, json.JSONDecodeError):
            continue
        for item in payload.get("sources", []):
            url = _safe_external_url(item.get("url")) if isinstance(item, dict) else None
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append({"name": str(item.get("name") or url)[:300], "url": url, "kind": "external"})
    return sources
