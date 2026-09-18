"""Small deterministic helpers used by chat generation."""

import json
import re
from typing import Any

from agent_core.ai.ollama import OllamaError

FRESH_WEB_PATTERNS = (
    r"\b(hôm nay|hiện nay|hiện tại|mới nhất|cập nhật|tin tức|thời tiết|giá|tỷ giá|lịch thi đấu)\b",
    r"\b(tìm|tra cứu|search|web)\b",
)


def model_error_message(chat: Any, error: Exception) -> str:
    raw, normalized = str(error), str(error).lower()
    label = f"{chat.provider} / {chat.model}"
    if chat.provider == "ollama" and isinstance(error, OllamaError):
        return f"Ollama local ({chat.model}): {raw}"
    if "reasoning_effort" in normalized and "function tools" in normalized:
        return f"Model {label} không hỗ trợ reasoning khi dùng công cụ ở chế độ hiện tại. Hãy thử gửi lại hoặc chọn model khác."
    if "model" in normalized and ("not found" in normalized or "does not exist" in normalized):
        return f"Model {label} không khả dụng với API key hiện tại. Hãy chọn model khác trong danh sách."
    return f"Không thể gọi model {label}: {raw}"


def small_talk_response(query: str) -> str | None:
    normalized = re.sub(r"[!?.…]+", "", query.casefold()).strip()
    if len(normalized) > 80:
        return None
    if re.fullmatch(r"(cảm ơn|cám ơn|thanks|thank you)( nhiều)?( nha| nhé| bạn)?", normalized):
        return "Không có gì nha, mình rất vui được giúp bạn."
    if re.fullmatch(r"(xin chào|chào|hello|hi)( bạn| nha)?", normalized):
        return "Chào bạn! Mình ở đây, bạn cần mình hỗ trợ gì?"
    if re.fullmatch(r"(tạm biệt|bye|goodbye)( nha| nhé)?", normalized):
        return "Tạm biệt nha! Khi cần, cứ nhắn mình."
    if re.fullmatch(r"(bạn khỏe không|dạo này ổn không|dạo này bạn thế nào)", normalized):
        return "Mình vẫn ổn và luôn sẵn sàng hỗ trợ bạn. Còn bạn thì sao?"
    return None


def is_ollama_tool_echo(content: str) -> bool:
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    return ("function" in serialized or "tool_call" in serialized) and any(name in serialized for name in ("calculator", "search_knowledge_base", "search_web"))


def should_search_web(query: str) -> bool:
    normalized = query.casefold()
    if small_talk_response(query) is not None or normalized.strip(" !?.") == "hôm nay bạn khỏe không":
        return False
    return any(re.search(pattern, normalized) for pattern in FRESH_WEB_PATTERNS)


def web_context_from_result(value: str) -> tuple[str, list[dict[str, str]]]:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return "", []
    if not isinstance(payload, dict):
        return "", []
    context, sources = payload.get("context"), payload.get("sources")
    if not isinstance(context, str) or not isinstance(sources, list):
        return "", []
    return context, [item for item in sources if isinstance(item, dict)]
