import json
from types import SimpleNamespace
from urllib.error import URLError

import pytest

import api.main as main_module
from agent_core.ollama import OllamaCatalog, OllamaUnavailableError
from agent_core.providers import OllamaClient
from agent_core.tools.base import ToolSpec


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_ollama_catalog_discovers_installed_models(monkeypatch):
    monkeypatch.setattr(
        "agent_core.ollama.urlopen",
        lambda request, timeout: FakeResponse({"models": [{"name": "qwen3:8b"}, {"name": "llama3.2:3b"}, {"name": "cloud:latest", "remote_host": "https://ollama.com"}, {"name": "qwen3:8b"}]}),
    )

    assert OllamaCatalog("http://127.0.0.1:11434").models() == ("qwen3:8b", "llama3.2:3b")


def test_ollama_catalog_reports_offline_runtime(monkeypatch):
    monkeypatch.setattr("agent_core.ollama.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")))

    with pytest.raises(OllamaUnavailableError, match="Không thể kết nối Ollama"):
        OllamaCatalog("http://127.0.0.1:11434").models()


def test_ollama_client_normalizes_tool_calls(monkeypatch):
    monkeypatch.setattr(
        "agent_core.providers.urlopen",
        lambda request, timeout: FakeResponse(
            {"message": {"content": "", "tool_calls": [{"function": {"name": "search_knowledge_base", "arguments": {"query": "RAG là gì?"}}}]}}
        ),
    )
    tool = ToolSpec(name="search_knowledge_base", description="Search", parameters={"type": "object"}, func=lambda: "")
    client = OllamaClient("http://127.0.0.1:11434", "qwen3:8b", 0.2, 99)

    reply = client.complete("system", [{"role": "user", "content": "RAG là gì?"}], [tool])

    assert reply.text == ""
    assert reply.tool_calls == [{"id": "ollama_call_0", "name": "search_knowledge_base", "args": {"query": "RAG là gì?"}}]


def test_llama_3b_uses_conservative_local_generation_options(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse({"message": {"content": "Xin chào"}})

    monkeypatch.setattr("agent_core.providers.urlopen", fake_urlopen)
    client = OllamaClient("http://127.0.0.1:11434", "llama3.2:3b", 0.7, 2048)

    client.complete("system", [{"role": "user", "content": "hello"}], [])

    assert captured["payload"]["options"] == {"temperature": 0.1, "num_predict": 512}


def test_ollama_history_is_text_only_and_preserves_tool_observation():
    client = OllamaClient("http://127.0.0.1:11434", "qwen3:8b", 0.2, 99)

    messages = client._to_messages(
        "system",
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "x", "name": "search_knowledge_base", "args": {"query": "hello"}}]},
            {"role": "tool", "id": "x", "name": "search_knowledge_base", "content": "result"},
        ],
    )

    assert messages[1] == {"role": "user", "content": "hello"}
    assert messages[2]["tool_calls"][0]["function"]["name"] == "search_knowledge_base"
    assert messages[3] == {"role": "tool", "content": "result"}


def test_ollama_agent_receives_no_function_tools(monkeypatch):
    selected = SimpleNamespace(
        provider="ollama",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="llama3.2:3b",
        temperature=0.2,
        max_tokens=32,
        max_steps=2,
    )
    fake_services = SimpleNamespace(
        settings=SimpleNamespace(with_provider_model=lambda _provider, _model: selected),
        ollama=SimpleNamespace(require_model=lambda _model: None),
        workspace=SimpleNamespace(get=lambda *_args: None),
        knowledge=SimpleNamespace(search=lambda *_args, **_kwargs: ""),
        media=SimpleNamespace(hydrate_history=lambda history: history),
        chats=SimpleNamespace(history=lambda _id: []),
        web_search=None,
    )
    monkeypatch.setattr(main_module, "services", lambda: fake_services)
    chat = SimpleNamespace(
        id="chat-1",
        provider="ollama",
        model="llama3.2:3b",
        user_id="user-1",
        project_id=None,
        collection_id=None,
        context_source_chat_id=None,
    )

    agent = main_module.make_agent(fake_services, chat, plugin_tools=[ToolSpec(name="plugin_read", description="plugin", parameters={}, func=lambda: "")], history=[])

    assert agent.registry.specs() == []
    assert "Không có tool" in agent.system_prompt
