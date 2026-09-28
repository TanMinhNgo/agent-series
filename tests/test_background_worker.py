"""Background jobs, knowledge indexing, artifacts and memory."""

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from agent_core.jobs.background import BackgroundWorker
from agent_core.content.artifacts import ArtifactService, extract_artifact_text
from agent_core.knowledge.memory import MemoryService
from agent_core.knowledge.rag import ALLOWED_DOCUMENT_SUFFIXES, build_knowledge_tool, extract_document_parts
from agent_core.persistence.store import document_scope_key
from api_support import RecordingJobs


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


def test_artifact_service_returns_a_unified_diff_for_the_previous_version(tmp_path: Path) -> None:
    previous = SimpleNamespace(
        id="asset-v1", artifact_id="artifact-1", name="ke-hoach.md", version=1,
        storage_provider="memory", stored_name="v1", storage_file_id=None,
    )
    current = SimpleNamespace(
        id="asset-v2", artifact_id="artifact-1", name="ke-hoach.md", version=2,
        storage_provider="memory", stored_name="v2", storage_file_id=None,
    )

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _model, asset_id):
            return {"asset-v1": previous, "asset-v2": current}.get(asset_id)

        def scalar(self, _statement):
            return previous

    storage = SimpleNamespace(read=lambda _provider, name, _file_id: {"v1": b"# Cu\nNoi dung cu\n", "v2": b"# Cu\nNoi dung moi\n"}[name])
    service = ArtifactService(SimpleNamespace(session=lambda: Session()), tmp_path, "unused", storage)

    result = service.diff("asset-v2")

    assert result == {
        "baseAssetId": "asset-v1",
        "baseVersion": 1,
        "assetId": "asset-v2",
        "version": 2,
        "diff": "--- ke-hoach.md (v1)\n+++ ke-hoach.md (v2)\n@@ -1,2 +1,2 @@\n # Cu\n-Noi dung cu\n+Noi dung moi",
    }


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


def test_background_worker_indexes_a_document_job() -> None:
    job = SimpleNamespace(id="job-1", type="document_index", payload={"document_id": "document-1"})
    calls: list[tuple[str, object]] = []

    class Knowledge:
        def index(self, document_id):
            calls.append(("index", document_id))

    assert BackgroundWorker(RecordingJobs(job, calls, record_heartbeats=True), Knowledge()).run_once(datetime.now(UTC))
    assert calls == [("heartbeat", "document_index"), ("index", "document-1"), ("succeed", "job-1")]


def test_background_worker_retries_a_failed_document_index() -> None:
    job = SimpleNamespace(id="job-1", type="document_index", payload={"document_id": "document-1"})
    calls: list[tuple[str, object]] = []

    class Knowledge:
        def index(self, _document_id):
            return SimpleNamespace(status="failed", error="embedding unavailable")

    assert BackgroundWorker(RecordingJobs(job, calls), Knowledge()).run_once(datetime.now(UTC))
    assert calls[0][0] == "fail"
    assert "embedding unavailable" in str(calls[0][1])
    assert not any(kind == "succeed" for kind, _ in calls)


def test_background_worker_indexes_memory_from_persisted_history() -> None:
    job = SimpleNamespace(id="job-2", type="memory_index", payload={"chat_id": "chat-1"})
    calls: list[tuple[str, object]] = []

    class Knowledge: pass
    class Chats:
        def history(self, chat_id):
            calls.append(("history", chat_id))
            return [{"role": "user", "content": "hello"}]

    class Memory:
        def index_history(self, chat_id, history): calls.append(("memory", (chat_id, history)))

    assert BackgroundWorker(RecordingJobs(job, calls), Knowledge(), Memory(), Chats()).run_once(datetime.now(UTC))
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
    assert extract_artifact_text(b"const answer: string = 'ok';", ".ts").startswith("const answer")


def test_background_worker_indexes_an_artifact_job() -> None:
    job = SimpleNamespace(id="job-artifact", type="artifact_index", payload={"asset_id": "asset-1"})
    calls: list[tuple[str, object]] = []

    class Artifacts:
        def index(self, asset_id): calls.append(("index", asset_id))

    assert BackgroundWorker(RecordingJobs(job, calls), SimpleNamespace(), artifacts=Artifacts()).run_once(datetime.now(UTC))
    assert calls == [("index", "asset-1"), ("succeed", "job-artifact")]
