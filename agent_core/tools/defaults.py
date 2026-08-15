"""Composition root for the tools enabled by default."""

from __future__ import annotations

from .calculator import CALCULATOR_TOOL
from .currency import CURRENCY_TOOL
from .registry import ToolRegistry
from .base import ToolSpec


DEFAULT_TOOLS = (
    CALCULATOR_TOOL,
    CURRENCY_TOOL,
)


def build_default_registry(knowledge_tool: ToolSpec | None = None, extra_tools: list[ToolSpec] | None = None) -> ToolRegistry:
    """Build a registry containing the project's default tool set."""
    tools = list(DEFAULT_TOOLS)
    if knowledge_tool is not None:
        tools.append(knowledge_tool)
    if extra_tools:
        tools.extend(extra_tools)
    return ToolRegistry(tools)
