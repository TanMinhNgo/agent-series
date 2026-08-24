"""Tavily-backed web search used only for grounded external citations."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .tools.base import ToolSpec

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _safe_external_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value.strip())
    return value.strip() if parsed.scheme == "https" and parsed.netloc else None


class WebSearchService:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 3) -> str:
        if not self.enabled:
            return "[Lỗi] Tìm web chưa được cấu hình."
        if not query.strip():
            return "[Lỗi] Câu hỏi tìm web đang trống."
        payload = json.dumps(
            {
                "api_key": self.api_key,
                "query": query.strip(),
                "search_depth": "basic",
                "max_results": max(1, min(int(max_results), 3)),
                "include_answer": False,
                "include_raw_content": False,
            }
        ).encode("utf-8")
        request = Request(TAVILY_SEARCH_URL, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=12) as response:  # noqa: S310 - fixed Tavily endpoint
                response_payload = json.loads(response.read().decode("utf-8"))
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
            sources.append({"name": name, "url": url, "kind": "external"})
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


def sources_from_web_steps(steps: list[Any]) -> list[dict[str, str]]:
    """Extract safe persisted sources from completed ``search_web`` tool calls."""
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for step in steps:
        if getattr(step, "tool", None) != "search_web":
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
