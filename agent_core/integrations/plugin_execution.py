"""Safe extension point for tools supplied by connected workspace plugins.

The catalog is metadata only today.  Executors are intentionally opt-in: a plugin
cannot be called until a future connector registers a read-only implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..persistence.store import Plugin
from ..tools.base import ToolSpec


class PluginExecutor(Protocol):
    slug: str

    def tools(self) -> list[ToolSpec]: ...


EXECUTORS: dict[str, PluginExecutor] = {}
READ_CAPABILITIES = {"search", "sync"}


def connected_read_tools(plugins: Iterable[Plugin]) -> list[ToolSpec]:
    """Return only tools from enabled, connected plugins with read capabilities."""
    tools: list[ToolSpec] = []
    for plugin in plugins:
        if not plugin.enabled or plugin.connection_status != "connected":
            continue
        if not READ_CAPABILITIES.intersection(plugin.capabilities or []):
            continue
        executor = EXECUTORS.get(plugin.slug)
        if executor is not None:
            tools.extend(executor.tools())
    return tools
