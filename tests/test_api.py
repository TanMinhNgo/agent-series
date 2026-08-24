from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

import pytest
import api.main as main_module
from pydantic import ValidationError
from types import SimpleNamespace

from api.main import (
    BranchChatRequest,
    FeedbackRequest,
    ProjectRequest,
    ScheduleRequest,
    ScheduleUpdateRequest,
    ShareRequest,
    app,
    create_chat_branch,
    create_response_feedback,
    detach_response_sources,
    list_chats,
    make_agent,
    message_json,
    model_error_message,
    prepare_chat_regeneration,
    persisted_history,
    recent_chat_history,
)
from agent_core.background import BackgroundWorker
from agent_core.artifacts import extract_artifact_text
from agent_core.plugin_catalog import CATALOG, find_catalog_plugin
from agent_core.plugin_execution import connected_read_tools
from agent_core.memory import MemoryService
from agent_core.knowledge import ALLOWED_DOCUMENT_SUFFIXES, build_knowledge_tool, extract_document_parts
from agent_core.credentials import CredentialError, UserCredentialService
from agent_core.storage import Chat, Plugin, Schedule, ScheduleRepository, current_user_id, document_scope_key, utc_now
from agent_core.scheduler import ScheduleWorker


def test_message_json_exposes_message_creation_time() -> None:
    created_at = datetime(2026, 8, 19, 9, 30, tzinfo=UTC).isoformat()

    assert message_json({"role": "user", "content": "Xin chào", "created_at": created_at}) == {
        "role": "user",
        "content": "Xin chào",
        "createdAt": created_at,
    }


def test_utc_now_is_timezone_aware() -> None:
    assert utc_now().tzinfo is UTC


def test_chat_json_exposes_unread_state() -> None:
    chat = SimpleNamespace(
        id="chat-1",
        title="Lịch: học frontend",
        provider="openai",
        model="gpt-test",
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
        updated_at=datetime(2026, 8, 24, tzinfo=UTC),
        pinned=False,
        archived=False,
        is_unread=True,
        context_source_chat_id=None,
        project_id=None,
        parent_chat_id=None,
        branch_from_position=None,
        collection_id=None,
    )

    assert main_module.chat_json(chat)["isUnread"] is True


def test_schedule_worker_restores_owner_and_replaces_legacy_chat(monkeypatch) -> None:
    observed: list[str | None] = []
    created: list[Chat] = []

    class Chats:
        database = object()

        def get(self, chat_id):
            observed.append(current_user_id.get())
            # The prior bug left this ownerless chat linked to the schedule.
            return None if chat_id == "legacy-chat" else created[0] if created else None

        def create(self, provider, model):
            observed.append(current_user_id.get())
            chat = Chat(id="replacement-chat", user_id="user-1", provider=provider, model=model)
            created.append(chat)
            return chat

        def update(self, _chat_id, **_values):
            observed.append(current_user_id.get())
            return created[0]

        def history(self, _chat_id):
            observed.append(current_user_id.get())
            return []

        def replace_history(self, _chat_id, history):
            observed.append(current_user_id.get())
            assert [item["role"] for item in history] == ["user", "assistant"]

        def set_unread(self, chat_id, unread):
            observed.append(current_user_id.get())
            assert (chat_id, unread) == ("replacement-chat", True)
            return created[0]

    class Runs:
        def attach_chat(self, schedule_id, chat_id):
            observed.append(current_user_id.get())
            assert (schedule_id, chat_id) == ("schedule-1", "replacement-chat")

        def finish(self, _run_id, **_values):
            observed.append(current_user_id.get())

    class AgentStub:
        history: list[dict] = []

        def run(self, prompt):
            assert prompt == "Dạy frontend"
            self.history = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "Bài học đã sẵn sàng."},
            ]
            return SimpleNamespace(text="Bài học đã sẵn sàng.", content_blocks=[])

    services = SimpleNamespace(
        chats=Chats(),
        settings=SimpleNamespace(provider="openai", active_model="gpt-test"),
        memory=SimpleNamespace(recall=lambda *_args: ""),
        workspace=SimpleNamespace(list_plugins=lambda: []),
    )
    worker = ScheduleWorker(services)
    worker.runs = Runs()
    monkeypatch.setattr("agent_core.scheduler.make_agent", lambda *_args, **_kwargs: AgentStub())
    monkeypatch.setattr("agent_core.scheduler.connected_read_tools", lambda _plugins: [])
    monkeypatch.setattr("agent_core.scheduler.BackgroundJobRepository", lambda _database: SimpleNamespace(enqueue=lambda *_args, **_kwargs: None))
    schedule = Schedule(
        id="schedule-1",
        user_id="user-1",
        title="Củng cố frontend",
        prompt="Dạy frontend",
        chat_id="legacy-chat",
    )

    worker.execute(schedule, "run-1")

    assert created and all(user_id == "user-1" for user_id in observed)
    assert current_user_id.get() is None


def test_health_and_public_config_do_not_expose_provider_keys(monkeypatch) -> None:
    # The registry deliberately preserves models disabled by an administrator.
    # Stub the available set here so this public-response contract never depends
    # on the shared local PostgreSQL state used by other tests.
    monkeypatch.setattr(main_module, "available_provider_models", lambda _user_id: {"gemini": ["gemini-test"]})

    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        payload = client.get("/api/config").json()

    assert payload["providers"] == {"gemini": ["gemini-test"]}
    assert "key" not in str(payload).lower()


def test_detach_response_sources_keeps_inline_answer_text_and_deduplicates_sources() -> None:
    content = (
        "RAG truy hồi tài liệu trước khi sinh câu trả lời "
        "[rag.md](/api/documents/rag/file#đoạn-1).\n\n"
        "Nguồn: [rag.md](/api/documents/rag/file#đoạn-1)"
    )

    visible, sources = detach_response_sources(content)

    assert visible == "RAG truy hồi tài liệu trước khi sinh câu trả lời."
    assert sources == [{"name": "rag.md", "url": "/api/documents/rag/file#đoạn-1", "kind": "library"}]


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


def test_messages_include_only_current_users_feedback(monkeypatch) -> None:
    class Chats:
        def get(self, _chat_id): return SimpleNamespace(id="chat-1")
        def history(self, _chat_id):
            return [
                {"message_id": "user-1", "role": "user", "content": "Câu hỏi"},
                {"message_id": "assistant-1", "role": "assistant", "content": "Trả lời"},
            ]

    class Personalization:
        def feedback_by_message_ids(self, message_ids):
            assert message_ids == ["assistant-1"]
            return {"assistant-1": "helpful"}

    monkeypatch.setattr(main_module, "services", lambda: SimpleNamespace(chats=Chats(), personalization=Personalization()))

    result = main_module.messages("chat-1")

    assert result[0].get("feedbackKind") is None
    assert result[1]["feedbackKind"] == "helpful"


def test_feedback_branch_and_regenerate_endpoints_delegate_the_selected_message(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None]] = []
    timestamp = datetime(2026, 8, 24, tzinfo=UTC)
    branch = SimpleNamespace(
        id="branch-1",
        title="Nhánh hội thoại",
        provider="openai",
        model="gpt-5.6-terra",
        created_at=timestamp,
        updated_at=timestamp,
        pinned=False,
        archived=False,
        context_source_chat_id=None,
        project_id=None,
        parent_chat_id="chat-1",
        branch_from_position=1,
        collection_id=None,
    )

    class Personalization:
        def record_feedback(self, message_id, kind, note):
            calls.append(("feedback", message_id, kind))
            return SimpleNamespace(id="feedback-1", message_id=message_id, kind=kind, note=note)

    class Chats:
        def create_branch(self, chat_id, message_id):
            calls.append(("branch", chat_id, message_id))
            return branch

        def prepare_regeneration(self, chat_id, message_id):
            calls.append(("regenerate", chat_id, message_id))
            return "Câu hỏi gốc"

    monkeypatch.setattr(main_module, "services", lambda: SimpleNamespace(personalization=Personalization(), chats=Chats()))

    feedback = create_response_feedback("assistant-1", FeedbackRequest(kind="helpful"))
    created_branch = create_chat_branch("chat-1", BranchChatRequest(assistantMessageId="assistant-1"))
    regeneration = prepare_chat_regeneration("chat-1", BranchChatRequest(assistantMessageId="assistant-1"))

    assert feedback == {"id": "feedback-1", "messageId": "assistant-1", "kind": "helpful", "note": None}
    assert created_branch["id"] == "branch-1"
    assert regeneration == {"content": "Câu hỏi gốc"}
    assert calls == [
        ("feedback", "assistant-1", "helpful"),
        ("branch", "chat-1", "assistant-1"),
        ("regenerate", "chat-1", "assistant-1"),
    ]


def test_user_credential_service_encrypts_and_hides_plaintext(monkeypatch) -> None:
    from cryptography.fernet import Fernet

    saved = {}
    class Repository:
        def save_user_provider_credential(self, user_id, provider, ciphertext, key_hint):
            saved.update(user_id=user_id, provider=provider, ciphertext=ciphertext, key_hint=key_hint)
            return SimpleNamespace(provider=provider, ciphertext=ciphertext, key_hint=key_hint)
        def user_provider_credential(self, user_id, provider):
            return SimpleNamespace(ciphertext=saved["ciphertext"]) if saved else None
        def user_provider_credentials(self, _user_id): return []

    service = UserCredentialService(Repository(), SimpleNamespace(user_credential_encryption_key=Fernet.generate_key().decode(), provider_models={"anthropic": ("claude-test",)}))
    monkeypatch.setattr(service, "validate", lambda _provider, _key: None)
    service.save("user-1", "openai", "sk-secret-value")

    assert saved["key_hint"] == "••••alue"
    assert "sk-secret-value" not in saved["ciphertext"]
    assert service.api_key("user-1", "openai") == "sk-secret-value"
    with pytest.raises(CredentialError):
        service.save("user-1", "unknown", "sk-secret-value")


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

    class AgentStub:
        history: list[dict] = []
        def run(self, _content, _attachments, on_step):
            self.history = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ]
            return SimpleNamespace(text="world", content_blocks=[])

    class Jobs:
        def __init__(self, _database): pass
        def enqueue(self, _kind, _payload): pass

    service = SimpleNamespace(
        chats=Chats(),
        memory=SimpleNamespace(recall=lambda *_args, **_kwargs: ""),
        workspace=SimpleNamespace(get=lambda *_args, **_kwargs: None, list_plugins=lambda: []),
    )
    monkeypatch.setattr(main_module, "services", lambda: service)
    monkeypatch.setattr(main_module, "make_agent", lambda *_args, **_kwargs: AgentStub())
    monkeypatch.setattr(main_module, "BackgroundJobRepository", Jobs)

    events = list(main_module.stream_chat("chat-1", "hello", []))

    assert observed == ["user-1"]
    message_event = next(event for event in events if 'event: message' in event)
    assert '"createdAt"' in message_event


def test_stream_chat_retrieves_the_global_library_before_creating_the_agent(monkeypatch) -> None:
    chat = Chat(id="chat-1", user_id="user-1", provider="openai", model="gpt-5.6-terra")
    observed: dict[str, object] = {}

    class Chats:
        database = object()
        def get(self, _chat_id): return chat
        def history(self, _chat_id): return []
        def replace_history(self, _chat_id, _history): pass

    class AgentStub:
        history: list[dict] = []
        def run(self, _content, _attachments, on_step):
            self.history = [{"role": "user", "content": "RAG là gì?"}, {"role": "assistant", "content": "RAG"}]
            return SimpleNamespace(text="RAG", content_blocks=[])

    class Jobs:
        def __init__(self, _database): pass
        def enqueue(self, _kind, _payload): pass

    class Knowledge:
        def search(self, query, top_k=4, project_id=None, collection_id=None):
            observed["search"] = (query, top_k, project_id, collection_id)
            return "[Nguồn 1: [rag.md](/api/documents/doc-1/file), đoạn 1]\\nRAG dùng truy hồi."

    service = SimpleNamespace(
        chats=Chats(),
        knowledge=Knowledge(),
        memory=SimpleNamespace(recall=lambda *_args, **_kwargs: ""),
        workspace=SimpleNamespace(get=lambda *_args, **_kwargs: None, list_plugins=lambda: []),
    )
    monkeypatch.setattr(main_module, "services", lambda: service)
    def make_agent_stub(*args, **kwargs):
        observed["context"] = args[3]
        return AgentStub()
    monkeypatch.setattr(main_module, "make_agent", make_agent_stub)
    monkeypatch.setattr(main_module, "BackgroundJobRepository", Jobs)

    list(main_module.stream_chat("chat-1", "RAG là gì?", []))

    assert observed["search"] == ("RAG là gì?", 4, None, None)
    assert "RAG dùng truy hồi" in str(observed["context"])


def test_knowledge_extracts_markdown_and_docx_parts(tmp_path: Path) -> None:
    markdown = tmp_path / "rag.md"
    markdown.write_text("# RAG\nRAG truy hồi ngữ cảnh trước khi trả lời.", encoding="utf-8")
    markdown_parts, markdown_count = extract_document_parts(markdown, ".md")
    assert markdown_count == len(markdown_parts) == 1
    assert "truy hồi" in markdown_parts[0][1]

    from docx import Document as DocxDocument

    document = DocxDocument()
    document.add_paragraph("DOCX cũng trở thành nguồn cho RAG.")
    stream = BytesIO()
    document.save(stream)
    docx_path = tmp_path / "rag.docx"
    docx_path.write_bytes(stream.getvalue())
    docx_parts, docx_count = extract_document_parts(docx_path, ".docx")
    assert docx_count == len(docx_parts) == 1
    assert "nguồn cho RAG" in docx_parts[0][1]
    assert ALLOWED_DOCUMENT_SUFFIXES == {".pdf", ".docx", ".md"}


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
    monkeypatch.setattr(main_module, "selected_settings", lambda *_args: SimpleNamespace(max_steps=5))
    monkeypatch.setattr(main_module, "build_client", lambda _settings: object())
    monkeypatch.setattr(main_module, "build_knowledge_tool", lambda *_args: None)
    monkeypatch.setattr(main_module, "build_default_registry", lambda *_args, **_kwargs: object())

    agent = make_agent(services, chat, history=history)
    agent.history.append({"role": "assistant", "content": "Câu trả lời mới"})

    assert history == [{"role": "user", "content": "Câu hỏi cũ"}]


def test_global_knowledge_tool_searches_only_global_documents() -> None:
    calls = []
    service = SimpleNamespace(search=lambda *args: calls.append(args) or "[1] global.pdf (trang 1)\nNội dung")

    tool = build_knowledge_tool(service)

    assert tool is not None
    assert tool.func("Tìm nội dung", 3).startswith("[1] global.pdf")
    assert calls == [("Tìm nội dung", 3, None, None)]


def test_project_knowledge_requires_a_selected_collection() -> None:
    service = SimpleNamespace(search=lambda *_args: "not used")

    assert build_knowledge_tool(service, "project-1") is None
    assert build_knowledge_tool(service, "project-1", "collection-1") is not None


def test_memory_recall_is_scoped_to_the_current_chat_and_optional_source() -> None:
    captured = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            captured.append(statement)
            return SimpleNamespace(all=lambda: [])

    service = MemoryService(SimpleNamespace(session=lambda: Session()), "unused")
    service._embed = lambda _values, _prefix: [[0.1, 0.2]]  # type: ignore[method-assign]

    assert service.recall("search term", "current-chat", "source-chat") == ""

    params = captured[0].compile().params
    assert ["current-chat", "source-chat"] in params.values()


def test_share_request_accepts_an_optional_expiry() -> None:
    assert ShareRequest.model_validate({"expiresAt": "2026-08-20T09:00:00+07:00"}).expires_at is not None
    assert ShareRequest().expires_at is None


def test_background_worker_indexes_a_document_job() -> None:
    job = SimpleNamespace(id="job-1", type="document_index", payload={"document_id": "document-1"})
    calls: list[tuple[str, object]] = []

    class Jobs:
        def claim(self, _now):
            return job

        def heartbeat(self, _now, current_job_type=None, last_error=None):
            if current_job_type or last_error:
                calls.append(("heartbeat", current_job_type or last_error))

        def succeed(self, job_id):
            calls.append(("succeed", job_id))

        def fail(self, job_id, error, _now):
            calls.append(("fail", (job_id, error)))

    class Knowledge:
        def index(self, document_id):
            calls.append(("index", document_id))

    assert BackgroundWorker(Jobs(), Knowledge()).run_once(datetime.now(UTC))
    assert calls == [("heartbeat", "document_index"), ("index", "document-1"), ("succeed", "job-1")]


def test_background_worker_retries_a_failed_document_index() -> None:
    job = SimpleNamespace(id="job-1", type="document_index", payload={"document_id": "document-1"})
    calls: list[tuple[str, object]] = []

    class Jobs:
        def claim(self, _now): return job
        def heartbeat(self, _now, current_job_type=None, last_error=None):
            if last_error: calls.append(("heartbeat", last_error))
        def succeed(self, job_id): calls.append(("succeed", job_id))
        def fail(self, job_id, error, _now): calls.append(("fail", (job_id, error)))

    class Knowledge:
        def index(self, _document_id):
            return SimpleNamespace(status="failed", error="embedding unavailable")

    assert BackgroundWorker(Jobs(), Knowledge()).run_once(datetime.now(UTC))
    assert calls[0][0] == "fail"
    assert "embedding unavailable" in str(calls[0][1])
    assert not any(kind == "succeed" for kind, _ in calls)


def test_background_worker_indexes_memory_from_persisted_history() -> None:
    job = SimpleNamespace(id="job-2", type="memory_index", payload={"chat_id": "chat-1"})
    calls: list[tuple[str, object]] = []

    class Jobs:
        def claim(self, _now): return job
        def heartbeat(self, _now, current_job_type=None, last_error=None): pass
        def succeed(self, job_id): calls.append(("succeed", job_id))
        def fail(self, job_id, error, _now): calls.append(("fail", (job_id, error)))

    class Knowledge: pass
    class Chats:
        def history(self, chat_id):
            calls.append(("history", chat_id))
            return [{"role": "user", "content": "hello"}]

    class Memory:
        def index_history(self, chat_id, history): calls.append(("memory", (chat_id, history)))

    assert BackgroundWorker(Jobs(), Knowledge(), Memory(), Chats()).run_once(datetime.now(UTC))
    assert calls == [
        ("history", "chat-1"),
        ("memory", ("chat-1", [{"role": "user", "content": "hello"}])),
        ("succeed", "job-2"),
    ]


def test_file_cleanup_worker_deletes_only_a_file_inside_known_storage(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    media_dir = tmp_path / "uploads"
    knowledge_dir.mkdir()
    media_dir.mkdir()
    file_path = knowledge_dir / "document.pdf"
    file_path.write_text("content", encoding="utf-8")

    worker = BackgroundWorker(
        SimpleNamespace(),
        SimpleNamespace(knowledge_dir=knowledge_dir),
        media_dir=media_dir,
    )
    worker._cleanup_files([{"storage": "knowledge", "stored_name": "document.pdf"}])

    assert not file_path.exists()
    with pytest.raises(ValueError, match="Đường dẫn"):
        worker._cleanup_files([{"storage": "media", "stored_name": "../outside.txt"}])


def test_document_sha_is_deduplicated_per_project_scope() -> None:
    assert document_scope_key(None) == "__library__"
    assert document_scope_key("project-a") == "project-a"


def test_artifact_text_preview_extracts_utf8_source(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text("# Kế hoạch\nArtifact có thể được truy hồi.", encoding="utf-8")
    assert "truy hồi" in extract_artifact_text(path, ".md")


def test_background_worker_indexes_an_artifact_job() -> None:
    job = SimpleNamespace(id="job-artifact", type="artifact_index", payload={"asset_id": "asset-1"})
    calls: list[tuple[str, str]] = []

    class Jobs:
        def claim(self, _now): return job
        def heartbeat(self, *_args, **_kwargs): pass
        def succeed(self, job_id): calls.append(("succeed", job_id))
        def fail(self, job_id, _error, _now): calls.append(("fail", job_id))

    class Artifacts:
        def index(self, asset_id): calls.append(("index", asset_id))

    assert BackgroundWorker(Jobs(), SimpleNamespace(), artifacts=Artifacts()).run_once(datetime.now(UTC))
    assert calls == [("index", "asset-1"), ("succeed", "job-artifact")]


def test_project_status_is_limited_to_workspace_statuses() -> None:
    assert ProjectRequest(name="Agent Series").status == "active"
    assert ProjectRequest(name="Agent Series", status="completed").status == "completed"
    with pytest.raises(ValidationError):
        ProjectRequest(name="Agent Series", status="planning")


def test_schedule_request_accepts_frontend_camel_case_fields() -> None:
    payload = ScheduleRequest.model_validate({"title": "Demo", "startsAt": "2026-08-13T09:00:00+07:00", "endsAt": None, "projectId": None})
    assert payload.starts_at.hour == 9


def test_schedule_update_accepts_a_status_only_patch() -> None:
    assert ScheduleUpdateRequest.model_validate({"status": "paused"}).status == "paused"


def test_next_recurring_run_skips_missed_intervals() -> None:
    schedule = Schedule(
        id="schedule-1",
        title="Daily digest",
        starts_at=datetime(2026, 8, 10, 9, tzinfo=UTC),
        recurrence="daily",
        next_run_at=datetime(2026, 8, 10, 9, tzinfo=UTC),
    )
    assert ScheduleRepository.next_run_after(schedule, datetime(2026, 8, 17, 10, tzinfo=UTC)) == datetime(2026, 8, 18, 9, tzinfo=UTC)


def test_plugin_tools_require_an_enabled_connected_read_plugin() -> None:
    plugin = Plugin(id="plugin-1", slug="github", name="GitHub", enabled=True, connection_status="connected", capabilities=["search"])
    assert connected_read_tools([plugin]) == []  # no executor is registered yet
    plugin.enabled = False
    assert connected_read_tools([plugin]) == []


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
