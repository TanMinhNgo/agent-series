"""Chat history shaping and generated-artifact extraction."""

import json
from typing import Any

RECENT_USER_TURNS = 10
OLLAMA_RECENT_USER_TURNS = 4
OLLAMA_HISTORY_CHAR_LIMIT = 6_000


def recent_chat_history(history: list[dict[str, Any]], max_user_turns: int = RECENT_USER_TURNS) -> list[dict[str, Any]]:
    user_positions = [index for index, item in enumerate(history) if item.get("role") == "user"]
    if len(user_positions) <= max_user_turns:
        return history
    return history[user_positions[-max_user_turns]:]


def ollama_recent_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recent = recent_chat_history(history, max_user_turns=OLLAMA_RECENT_USER_TURNS)
    selected: list[dict[str, Any]] = []
    remaining = OLLAMA_HISTORY_CHAR_LIMIT
    for item in reversed(recent):
        content = str(item.get("content") or "")
        if not content:
            selected.append(dict(item))
            continue
        if remaining <= 0:
            continue
        clipped = content[-remaining:]
        copy = dict(item)
        copy["content"] = clipped
        selected.append(copy)
        remaining -= len(clipped)
    return list(reversed(selected))


def persisted_history(full_history: list[dict[str, Any]], agent_history: list[dict[str, Any]], initial_length: int) -> list[dict[str, Any]]:
    return [*full_history, *agent_history[initial_length:]]


def _payload_artifact_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    values = [*items, payload] if isinstance(items, list) else [payload]
    return [value["id"] for value in values if isinstance(value, dict) and isinstance(value.get("id"), str)]


def created_artifact_ids(steps: list[Any]) -> list[str]:
    asset_ids: list[str] = []
    for step in steps:
        if getattr(step, "tool", None) not in {"create_file", "create_artifact_version", "create_web_bundle"}:
            continue
        try:
            payload = json.loads(getattr(step, "result", ""))
        except (TypeError, ValueError):
            continue
        for asset_id in _payload_artifact_ids(payload):
            if asset_id not in asset_ids:
                asset_ids.append(asset_id)
    return asset_ids
