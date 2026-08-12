"""Parse the small, safe interactive-response dialect returned by the agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


_BLOCK_PATTERN = re.compile(r"```agent-block\s*\n(?P<payload>.*?)```", re.DOTALL)
_ALLOWED_TYPES = {"trig-circle", "chart", "data-table"}
_MAX_BLOCKS = 4


@dataclass(frozen=True)
class ParsedResponse:
    markdown: str
    blocks: list[dict[str, Any]]


def parse_response(text: str) -> ParsedResponse:
    """Remove valid agent blocks from Markdown and return their validated configs."""

    blocks: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        if len(blocks) >= _MAX_BLOCKS:
            return ""
        try:
            value = json.loads(match.group("payload"))
        except json.JSONDecodeError:
            return match.group(0)
        if not isinstance(value, dict) or value.get("type") not in _ALLOWED_TYPES:
            return match.group(0)
        config = value.get("config", {})
        if not isinstance(config, dict):
            return match.group(0)
        blocks.append({"type": value["type"], "config": config})
        return ""

    markdown = _BLOCK_PATTERN.sub(replace, text).strip()
    return ParsedResponse(markdown=markdown, blocks=blocks)
