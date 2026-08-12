from fastapi.testclient import TestClient

from api.main import app, model_error_message
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
