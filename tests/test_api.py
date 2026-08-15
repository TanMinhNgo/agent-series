from datetime import UTC, datetime

from fastapi.testclient import TestClient

import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from api.main import ProjectRequest, ScheduleRequest, app, list_chats, model_error_message
from agent_core.plugin_catalog import CATALOG, find_catalog_plugin
from agent_core.storage import Chat


def test_health_and_public_config_do_not_expose_provider_keys(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODELS", "gemini-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        payload = client.get("/api/config").json()

    assert payload["providers"] == {"gemini": ["gemini-test"]}
    assert "key" not in str(payload).lower()


def test_model_error_message_explains_tool_reasoning_conflict() -> None:
    chat = Chat(id="chat-1", provider="openai", model="gpt-5.6-terra")
    error = RuntimeError("Function tools with reasoning_effort are not supported")

    assert "gpt-5.6-terra" in model_error_message(chat, error)
    assert "không hỗ trợ reasoning" in model_error_message(chat, error)


def test_chat_history_list_is_paginated(monkeypatch) -> None:
    records = [
        SimpleNamespace(
            id=f"chat-{index}", title="Cuộc trò chuyện mới", provider="openai", model="gpt-5.6-terra",
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            pinned=False, archived=False, context_source_chat_id=None,
        )
        for index in range(3)
    ]

    class Chats:
        def list(self, offset: int, limit: int):
            return records[offset:offset + limit], len(records)

    class Services:
        chats = Chats()

    monkeypatch.setattr("api.main.services", lambda: Services())
    page = list_chats(offset=0, limit=2)

    assert [item["id"] for item in page["items"]] == ["chat-0", "chat-1"]
    assert page["total"] == 3
    assert page["nextOffset"] == 2


def test_project_status_is_limited_to_workspace_statuses() -> None:
    assert ProjectRequest(name="Agent Series").status == "active"
    assert ProjectRequest(name="Agent Series", status="completed").status == "completed"
    with pytest.raises(ValidationError):
        ProjectRequest(name="Agent Series", status="planning")


def test_schedule_request_accepts_frontend_camel_case_fields() -> None:
    payload = ScheduleRequest.model_validate({"title": "Demo", "startsAt": "2026-08-13T09:00:00+07:00", "endsAt": None, "projectId": None})
    assert payload.starts_at.hour == 9


def test_plugin_catalog_has_unique_slugs_and_expected_core_apps() -> None:
    slugs = [item.slug for item in CATALOG]
    expected_categories = {
        "productivity", "creative", "developer", "business", "education", "analytics", "communication",
        "security", "finance", "health", "travel", "entertainment", "other",
    }
    assert len(slugs) == len(set(slugs)) == 65
    assert {item.category for item in CATALOG} == expected_categories
    assert all(sum(item.category == category for item in CATALOG) == 5 for category in expected_categories)
    assert [item.slug for item in CATALOG if item.featured] == ["google-workspace", "notion", "figma", "github", "slack"]
    assert find_catalog_plugin("github").name == "GitHub"
    assert find_catalog_plugin("missing") is None
