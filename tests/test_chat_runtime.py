"""Chat runtime: streaming, agent construction, history and answer sources."""

import json
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace

import pytest
import api.modules.chats.module as chat_runtime
from agent_core.ai.history import created_artifact_ids, ollama_recent_history, persisted_history, recent_chat_history
from api.contracts.requests import ChatRequest
from api.modules.chats.module import ChatRunRegistry, detach_response_sources
from api.modules.chats.runtime.generation import is_ollama_tool_echo, model_error_message, should_search_web, small_talk_response
from agent_core.content.artifacts import ArtifactEditContext
from agent_core.integrations.plugin_execution import EXECUTORS, connected_read_tools, project_scoped_read_tools
from agent_core.tools import ToolSpec
from agent_core.persistence.store import Chat, Plugin, current_user_id
from api_support import FixedReplyAgent, HistoryChats, SavingChats, StubJobs, agent_services, chat_module, make_agent, message_json


def test_message_json_exposes_message_creation_time() -> None:
    created_at = datetime(2026, 8, 19, 9, 30, tzinfo=UTC).isoformat()

    assert message_json({"role": "user", "content": "Xin chào", "created_at": created_at}) == {
        "role": "user",
        "content": "Xin chào",
        "createdAt": created_at,
    }


def test_chat_request_accepts_a_per_message_research_web_toggle() -> None:
    request = ChatRequest.model_validate({"content": "Tìm tài liệu mới", "researchWeb": True})

    assert request.research_web is True


def test_created_artifact_ids_keeps_all_web_bundle_files() -> None:
    steps = [
        SimpleNamespace(
            tool="create_web_bundle",
            result=json.dumps({"items": [{"id": "html"}, {"id": "css"}, {"id": "js"}, {"id": "zip"}]}),
        )
    ]

    assert created_artifact_ids(steps) == ["html", "css", "js", "zip"]


def test_message_json_keeps_artifacts_attached_to_assistant_response() -> None:
    artifacts = [{"id": "asset-1", "name": "ke-hoach.md", "version": 1}]

    assert message_json({"role": "assistant", "content": "Đã tạo file.", "artifacts": artifacts})["artifacts"] == artifacts


def test_created_artifact_ids_ignores_unrelated_or_invalid_tool_results() -> None:
    steps = [
        SimpleNamespace(tool="search_web", result='{"id": "ignored"}'),
        SimpleNamespace(tool="create_file", result='{"id": "asset-1"}'),
        SimpleNamespace(tool="create_file", result="not-json"),
        SimpleNamespace(tool="create_file", result='{"id": "asset-1"}'),
        SimpleNamespace(tool="create_file", result='{"id": "asset-2"}'),
    ]

    assert created_artifact_ids(steps) == ["asset-1", "asset-2"]


def test_created_artifact_ids_keeps_ai_created_versions() -> None:
    steps = [
        SimpleNamespace(tool="create_artifact_version", result='{"id": "asset-v2"}'),
        SimpleNamespace(tool="create_file", result='{"id": "asset-v1"}'),
    ]

    assert created_artifact_ids(steps) == ["asset-v2", "asset-v1"]


def test_chat_request_accepts_an_optional_edit_asset_id() -> None:
    request = ChatRequest.model_validate({"content": "Đổi phần mở đầu", "editAssetId": "asset-v1"})

    assert request.edit_asset_id == "asset-v1"


def test_chat_request_accepts_a_client_run_id() -> None:
    request = ChatRequest.model_validate({"content": "Xin chào", "runId": "run-1"})

    assert request.run_id == "run-1"


def test_chat_run_registry_cancels_only_the_owner() -> None:
    registry = ChatRunRegistry()
    event = registry.start("chat-1", "run-1", "user-1")

    assert not registry.cancel("chat-1", "run-1", "user-2")
    assert registry.cancel("chat-1", "run-1", "user-1")
    assert event.is_set()


def test_chat_run_registry_serializes_turns_for_one_chat() -> None:
    registry = ChatRunRegistry()
    registry.start("chat-1", "run-1", "user-1")
    with pytest.raises(ValueError, match="đang tạo phản hồi"):
        registry.start("chat-1", "run-2", "user-1")
    registry.start("chat-2", "run-2", "user-1")
    registry.finish("chat-1", "run-1")
    registry.start("chat-1", "run-2", "user-1")


def test_rejected_chat_stream_does_not_register_a_run() -> None:
    from fastapi import HTTPException
    from api.modules.chats.controller import ChatStreamController

    registry = ChatRunRegistry()
    chat = Chat(id="chat-1", user_id="user-1", provider="openai", model="test", mode="plan")
    services = SimpleNamespace(chats=SimpleNamespace(get=lambda _: chat),
        media=SimpleNamespace(for_prompt=lambda _: []),
        artifacts=SimpleNamespace(edit_context=lambda *_: SimpleNamespace(id="asset-1")))
    controller = ChatStreamController(lambda: services, lambda *_: iter(()), registry, "Missing", "Missing")
    with pytest.raises(HTTPException) as error:
        controller.stream("chat-1", ChatRequest(content="Edit", editAssetId="asset-1", runId="run-1"))
    assert error.value.status_code == 422
    registry.start("chat-1", "run-1", "user-1")


def test_disconnected_stream_cancels_its_agent_turn() -> None:
    from api.modules.chats.runtime.stream import StreamDependencies, stream_chat
    from agent_core.ai.agent import AgentCancelled
    from agent_core.persistence.store import current_workspace_id

    registry = ChatRunRegistry()
    cancelled = registry.start("chat-1", "run-1", "user-1")
    chat = Chat(id="chat-1", user_id="user-1", provider="openai", model="test")
    def blocked_turn(*args):
        assert args[6].wait(2)
        raise AgentCancelled()
    deps = StreamDependencies(
        services=lambda: SimpleNamespace(chats=SimpleNamespace(get=lambda _: chat, history=lambda _: [])),
        sse=lambda name, _: name,
        chat_runs=registry,
        run_image_turn=lambda *_: None,
        message_json=lambda _: {},
        small_talk_response=lambda _: None,
        persist_static_response=lambda *_: None,
        run_agent_turn=blocked_turn,
        model_error_message=lambda *_: "error",
        agent_cancelled=AgentCancelled,
        image_generation_error=ValueError,
        current_user_id=current_user_id,
        current_workspace_id=current_workspace_id,
    )
    events = stream_chat(deps, "chat-1", "Long task", [], cancel_event=cancelled, run_id="run-1")
    assert next(events) == "status"
    events.close()
    assert cancelled.is_set()


def test_ollama_web_search_ignores_greetings_and_detects_fresh_questions() -> None:
    assert not should_search_web("Hôm nay bạn khỏe không?")
    assert should_search_web("Tin tức AI mới nhất hôm nay là gì?")


def test_ollama_small_talk_uses_a_natural_fast_response() -> None:
    assert small_talk_response("cảm ơn nhiều nha") == "Không có gì nha, mình rất vui được giúp bạn."
    assert small_talk_response("Cảm ơn, bạn giải thích thêm RAG nhé") is None
    assert small_talk_response("Chào bạn!") == "Chào bạn! Mình ở đây, bạn cần mình hỗ trợ gì?"
    assert small_talk_response("Dạo này ổn không?") == "Mình vẫn ổn và luôn sẵn sàng hỗ trợ bạn. Còn bạn thì sao?"


def test_ollama_history_is_limited_without_mutating_persisted_messages() -> None:
    history = [
        {"role": "user", "content": f"câu hỏi {index} " + ("x" * 2_000)}
        for index in range(6)
    ]

    prompt_history = ollama_recent_history(history)

    assert len(prompt_history) == 3
    assert sum(len(item["content"]) for item in prompt_history) <= 6_000
    assert len(history[-1]["content"]) > 2_000


def test_ollama_tool_echo_is_rejected_before_rendering() -> None:
    assert is_ollama_tool_echo('{"type":"function","function":{"name":"calculator"}}')
    assert not is_ollama_tool_echo("Đây là câu trả lời bình thường.")


def test_stream_chat_answers_ollama_small_talk_without_model_or_memory(monkeypatch) -> None:
    chat = Chat(id="chat-1", user_id="user-1", provider="ollama", model="llama3.2:3b")
    saved: list[dict] = []
    monkeypatch.setattr(chat_module, "services", lambda: SimpleNamespace(chats=SavingChats(chat, saved)))

    events = list(chat_module.stream_chat("chat-1", "cảm ơn nhiều nha", []))

    assert saved[-1]["content"] == "Không có gì nha, mình rất vui được giúp bạn."
    assert any("event: message" in event for event in events)


def test_stream_chat_answers_cloud_small_talk_without_provider_call(monkeypatch) -> None:
    chat = Chat(id="chat-1", user_id="user-1", provider="openai", model="gpt-5.6-terra")
    saved: list[dict] = []
    monkeypatch.setattr(chat_module, "services", lambda: SimpleNamespace(chats=SavingChats(chat, saved)))
    monkeypatch.setattr(chat_runtime, "build_client", lambda _settings: (_ for _ in ()).throw(AssertionError("LLM must not run")))

    events = list(chat_module.stream_chat("chat-1", "Dạo này ổn không?", []))

    assert saved[-1]["content"] == "Mình vẫn ổn và luôn sẵn sàng hỗ trợ bạn. Còn bạn thì sao?"
    assert any("event: done" in event for event in events)


def test_stream_chat_does_not_persist_a_pre_cancelled_run(monkeypatch) -> None:
    chat = Chat(id="chat-1", user_id="user-1", provider="openai", model="gpt-5.6-terra")
    monkeypatch.setattr(chat_module, "services", lambda: SimpleNamespace(chats=SimpleNamespace(get=lambda _id: chat)))
    cancel_event = Event()
    cancel_event.set()

    events = list(chat_module.stream_chat("chat-1", "Xin chào", [], cancel_event=cancel_event))

    assert any("event: cancelled" in event for event in events)


def test_detach_response_sources_keeps_inline_answer_text_and_deduplicates_sources() -> None:
    content = (
        "RAG truy hồi tài liệu trước khi sinh câu trả lời "
        "[rag.md](/api/documents/rag/file#đoạn-1).\n\n"
        "Nguồn: [rag.md](/api/documents/rag/file#đoạn-1)"
    )

    visible, sources = detach_response_sources(content)

    assert visible == "RAG truy hồi tài liệu trước khi sinh câu trả lời."
    assert sources == [{"name": "rag.md", "url": "/api/documents/rag/file#đoạn-1", "kind": "library"}]


def test_detach_response_sources_handles_spaced_labels_and_punctuation() -> None:
    visible, sources = detach_response_sources(
        "Đúng   , xem [rag.md](/api/documents/rag/file).\nTham   khảo : [rag.md](/api/documents/rag/file)"
    )

    assert visible == "Đúng, xem."
    assert sources == [{"name": "rag.md", "url": "/api/documents/rag/file", "kind": "library"}]


def test_detach_response_sources_combines_safe_web_sources() -> None:
    visible, sources = detach_response_sources(
        "Nội dung từ web.",
        [
            {"name": "Tài liệu chính thức", "url": "https://example.com/docs", "kind": "external"},
            {"name": "Không an toàn", "url": "http://example.com", "kind": "external"},
        ],
    )

    assert visible == "Nội dung từ web."
    assert sources == [{"name": "Tài liệu chính thức", "url": "https://example.com/docs", "kind": "external"}]


def test_detach_response_sources_keeps_response_without_document_citations() -> None:
    assert detach_response_sources("Câu trả lời không dùng thư viện.") == (
        "Câu trả lời không dùng thư viện.",
        [],
    )


def test_message_json_preserves_separate_sources() -> None:
    payload = message_json({
        "role": "assistant",
        "content": "Nội dung",
        "sources": [{"name": "rag.md", "url": "/api/documents/rag/file"}],
    })

    assert payload["sources"] == [{"name": "rag.md", "url": "/api/documents/rag/file"}]


def test_model_error_message_explains_tool_reasoning_conflict() -> None:
    chat = Chat(id="chat-1", provider="openai", model="gpt-5.6-terra")
    error = RuntimeError("Function tools with reasoning_effort are not supported")

    assert "gpt-5.6-terra" in model_error_message(chat, error)
    assert "không hỗ trợ reasoning" in model_error_message(chat, error)


def test_stream_chat_restores_the_chat_owner_in_its_worker_thread(monkeypatch) -> None:
    chat = Chat(id="chat-1", user_id="user-1", provider="openai", model="gpt-5.6-terra")
    observed: list[str | None] = []

    class Chats:
        database = object()
        def get(self, _chat_id): return chat
        def history(self, _chat_id):
            observed.append(current_user_id.get())
            return []
        def replace_history(self, _chat_id, _history): pass

    service = agent_services(Chats())
    monkeypatch.setattr(chat_module, "services", lambda: service)
    monkeypatch.setattr(chat_module, "make_agent", lambda *_args, **_kwargs: FixedReplyAgent("RAG là gì?", "world"))
    monkeypatch.setattr(chat_runtime, "BackgroundJobRepository", StubJobs)

    events = list(chat_module.stream_chat("chat-1", "RAG là gì?", []))

    assert observed == ["user-1"]
    message_event = next(event for event in events if 'event: message' in event)
    assert '"createdAt"' in message_event


def test_stream_chat_retrieves_the_global_library_before_creating_the_agent(monkeypatch) -> None:
    chat = Chat(id="chat-1", user_id="user-1", provider="openai", model="gpt-5.6-terra")
    observed: dict[str, object] = {}

    class Knowledge:
        def search(self, query, top_k=4, project_id=None, collection_id=None):
            observed["search"] = (query, top_k, project_id, collection_id)
            return "[Nguồn 1: [rag.md](/api/documents/doc-1/file), đoạn 1]\\nRAG dùng truy hồi."

    service = agent_services(HistoryChats(chat, []), knowledge=Knowledge())
    monkeypatch.setattr(chat_module, "services", lambda: service)
    def make_agent_stub(*args, **kwargs):
        observed["context"] = args[3]
        return FixedReplyAgent("RAG là gì?", "RAG")
    monkeypatch.setattr(chat_module, "make_agent", make_agent_stub)
    monkeypatch.setattr(chat_runtime, "BackgroundJobRepository", StubJobs)

    list(chat_module.stream_chat("chat-1", "RAG là gì?", []))

    assert observed["search"] == ("RAG là gì?", 4, None, None)
    assert "RAG dùng truy hồi" in str(observed["context"])


def test_recent_chat_history_keeps_ten_complete_user_turns() -> None:
    history = []
    for index in range(12):
        history.extend([
            {"role": "user", "content": f"question {index}"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": f"tool-{index}"}]},
            {"role": "tool", "id": f"tool-{index}", "name": "search", "content": "result"},
            {"role": "assistant", "content": f"answer {index}"},
        ])

    recent = recent_chat_history(history)

    assert recent[0] == {"role": "user", "content": "question 2"}
    assert sum(item["role"] == "user" for item in recent) == 10
    assert {item["id"] for item in recent if item["role"] == "tool"} == {f"tool-{index}" for index in range(2, 12)}


def test_persisted_history_keeps_archived_context_and_appends_new_turn() -> None:
    archived = [{"role": "user", "content": "old question"}, {"role": "assistant", "content": "old answer"}]
    context = [{"role": "user", "content": "recent question"}]
    generated = [*context, {"role": "assistant", "content": "new answer"}]

    assert persisted_history(archived, generated, len(context)) == [
        *archived,
        {"role": "assistant", "content": "new answer"},
    ]


def test_make_agent_does_not_mutate_the_history_being_persisted(monkeypatch) -> None:
    history = [{"role": "user", "content": "Câu hỏi cũ"}]
    chat = Chat(id="chat-1", provider="openai", model="gpt-5.6-terra")
    services = SimpleNamespace(
        workspace=SimpleNamespace(get=lambda *_args, **_kwargs: None),
        media=SimpleNamespace(hydrate_history=lambda value: value),
        knowledge=SimpleNamespace(),
    )
    monkeypatch.setattr(chat_runtime, "selected_settings", lambda *_args: SimpleNamespace(max_steps=5))
    monkeypatch.setattr(chat_runtime, "build_client", lambda _settings: object())
    monkeypatch.setattr(chat_runtime, "build_knowledge_tool", lambda *_args: None)
    monkeypatch.setattr(chat_runtime, "build_default_registry", lambda *_args, **_kwargs: object())

    agent = make_agent(services, chat, history=history)
    agent.history.append({"role": "assistant", "content": "Câu trả lời mới"})

    assert history == [{"role": "user", "content": "Câu hỏi cũ"}]


def test_make_agent_uses_a_version_only_tool_for_an_artifact_edit(monkeypatch) -> None:
    captured_tools = []
    created = []
    chat = Chat(id="chat-1", provider="openai", model="gpt-5.6-terra", project_id=None)
    edit = ArtifactEditContext(
        asset_id="asset-v1",
        artifact_id="artifact-1",
        name="ke-hoach.md",
        mime_type="text/markdown",
        project_id=None,
        version=1,
        content="# Bản cũ",
    )
    services = SimpleNamespace(
        workspace=SimpleNamespace(get=lambda *_args, **_kwargs: None),
        media=SimpleNamespace(hydrate_history=lambda value: value),
        knowledge=SimpleNamespace(),
        library=SimpleNamespace(
            create_version=lambda *args: created.append(args)
            or SimpleNamespace(id="asset-v2", artifact_id="artifact-1", name="ke-hoach.md", version=2),
        ),
    )
    monkeypatch.setattr(chat_runtime, "selected_settings", lambda *_args: SimpleNamespace(max_steps=5))
    monkeypatch.setattr(chat_runtime, "build_client", lambda _settings: object())
    monkeypatch.setattr(chat_runtime, "build_knowledge_tool", lambda *_args: None)
    monkeypatch.setattr(chat_runtime, "build_default_registry", lambda _knowledge, extra_tools: captured_tools.extend(extra_tools) or object())
    monkeypatch.setattr(chat_runtime, "enqueue_artifact_index", lambda *_args: None)
    monkeypatch.setattr(chat_runtime, "library_asset_json", lambda asset: {"id": asset.id, "artifactId": asset.artifact_id})

    make_agent(services, chat, history=[], artifact_edit=edit)

    assert {tool.name for tool in captured_tools} == {"create_artifact_version"}
    result = json.loads(captured_tools[0].func("# Bản mới"))
    assert result == {"id": "asset-v2", "artifactId": "artifact-1"}
    assert created == [("asset-v1", "ke-hoach.md", "text/markdown", "# Bản mới".encode())]
    with pytest.raises(ValueError, match="một version"):
        captured_tools[0].func("# Không được tạo thêm")


def test_plugin_tools_require_an_enabled_connected_read_plugin(monkeypatch) -> None:
    from agent_core.integrations.github_app import GitHubAppExecutor, GitHubAppService
    monkeypatch.setitem(EXECUTORS, "github", GitHubAppExecutor(GitHubAppService(None, None)))
    plugin = Plugin(id="plugin-1", slug="github", name="GitHub", enabled=True, connection_status="connected", capabilities=["search"])
    assert {tool.name for tool in connected_read_tools([plugin])} == {
        "list_github_repositories",
        "read_github_repository_file",
        "search_github_issues",
    }
    plugin.enabled = False
    assert connected_read_tools([plugin]) == []


def test_project_connector_tools_only_expose_explicitly_scoped_reads() -> None:
    plugin = Plugin(id="plugin-1", slug="github", name="GitHub", enabled=True, connection_status="connected", capabilities=["search"])
    class GitHubExecutor:
        def tools(self):
            return [
                ToolSpec("list_github_repositories", "", {}, lambda: "all"),
                ToolSpec("read_github_repository_file", "", {}, lambda repository, path: f"{repository}/{path}"),
                ToolSpec("search_github_issues", "", {}, lambda repository, query: f"{repository}:{query}"),
            ]
    previous = EXECUTORS.get("github")
    EXECUTORS["github"] = GitHubExecutor()
    try:
        tools = {item.name: item for item in project_scoped_read_tools([plugin], {"github": {"repositories": ["owner/allowed"]}})}
        assert set(tools) == {"read_github_repository_file", "search_github_issues"}
        assert tools["read_github_repository_file"].func(repository="owner/allowed", path="README.md") == "owner/allowed/README.md"
        assert "không nằm trong phạm vi" in tools["search_github_issues"].func(repository="owner/blocked", query="bug")
    finally:
        if previous is None:
            EXECUTORS.pop("github", None)
        else:
            EXECUTORS["github"] = previous


def test_api_agent_translates_domain_validation_error(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(chat_runtime, "selected_settings", lambda *_args: (_ for _ in ()).throw(ValueError("Model disabled")))
    with pytest.raises(HTTPException) as captured:
        make_agent(SimpleNamespace(), Chat(provider="openai", model="disabled"))
    assert captured.value.status_code == 422
    assert captured.value.detail == "Model disabled"
