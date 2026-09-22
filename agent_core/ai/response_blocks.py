"""Parse the small, safe interactive-response dialect returned by the agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


_BLOCK_START = re.compile(r"```agent-block[ \t]*\r?\n")
_ALLOWED_TYPES = {"trig-circle", "chart", "data-table"}
_MAX_BLOCKS = 4


@dataclass(frozen=True)
class ParsedResponse:
    markdown: str
    blocks: list[dict[str, Any]]


def parse_response(text: str) -> ParsedResponse:
    """Remove valid agent blocks from Markdown and return their validated configs."""

    blocks: list[dict[str, Any]] = []

    def replace(block: str, payload: str) -> str:
        if len(blocks) >= _MAX_BLOCKS:
            return ""
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return block
        if not isinstance(value, dict) or value.get("type") not in _ALLOWED_TYPES:
            return block
        config = value.get("config", {})
        if not isinstance(config, dict):
            return block
        blocks.append({"type": value["type"], "config": config})
        return ""

    parts: list[str] = []
    position = 0
    for start in _BLOCK_START.finditer(text):
        if start.start() < position:
            continue
        end = text.find("```", start.end())
        if end < 0:
            break
        parts.append(text[position : start.start()])
        parts.append(replace(text[start.start() : end + 3], text[start.end() : end]))
        position = end + 3
    parts.append(text[position:])
    markdown = "".join(parts).strip()
    return ParsedResponse(markdown=markdown, blocks=blocks)
