"""Safe extension point for tools supplied by connected workspace plugins.

The catalog is metadata only today.  Executors are intentionally opt-in: a plugin
cannot be called until a future connector registers a read-only implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

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


def project_scoped_read_tools(plugins: Iterable[Plugin], scopes: dict[str, dict]) -> list[ToolSpec]:
    """Restrict connector reads to explicit Project source identifiers."""
    repositories = {str(item).strip().lower() for item in scopes.get("github", {}).get("repositories", []) if str(item).strip()}
    file_ids = {str(item).strip() for item in scopes.get("google-workspace", {}).get("fileIds", []) if str(item).strip()}
    result: list[ToolSpec] = []
    for tool in connected_read_tools(plugins):
        if tool.name in {"read_github_repository_file", "search_github_issues"} and repositories:
            original = tool.func
            def github_read(*, repository: str, _original=original, **kwargs: Any) -> str:
                if repository.strip().lower() not in repositories:
                    return "Repository này không nằm trong phạm vi đã chọn cho Project."
                return _original(repository=repository, **kwargs)
            result.append(ToolSpec(tool.name, tool.description, tool.parameters, github_read))
        elif tool.name == "read_google_drive_file" and file_ids:
            original = tool.func
            def drive_read(*, file_id: str, _original=original, **kwargs: Any) -> str:
                if file_id.strip() not in file_ids:
                    return "File Drive này không nằm trong phạm vi đã chọn cho Project."
                return _original(file_id=file_id, **kwargs)
            result.append(ToolSpec(tool.name, tool.description, tool.parameters, drive_read))
    return result
