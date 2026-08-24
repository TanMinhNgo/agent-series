"""Opt-in RAG integration test against an isolated PostgreSQL/pgvector database."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from agent_core.background import BackgroundWorker
from agent_core.knowledge import KnowledgeService, build_knowledge_tool
from agent_core.storage import BackgroundJobRepository, Database, Project, WorkspaceRepository

pytestmark = pytest.mark.integration

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

if os.getenv("RUN_RAG_INTEGRATION") != "1":
    pytest.skip("Set RUN_RAG_INTEGRATION=1 to run real RAG integration tests.", allow_module_level=True)


def pdf_bytes(text: str = "Agent Series RAG integration needle: Mekong Delta source.") -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 720, text)
    canvas.save()
    return stream.getvalue()


@pytest.fixture(scope="session")
def integration_database() -> Database:
    base_url = os.getenv("DATABASE_URL")
    if not base_url:
        pytest.fail("DATABASE_URL is required for the RAG integration test.")
    source = make_url(base_url)
    test_name = f"{source.database}_rag_test"
    test_url = source.set(database=test_name)
    admin_engine = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{test_name}" WITH (FORCE)')
        connection.exec_driver_sql(f'CREATE DATABASE "{test_name}"')

    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        yield Database(os.environ["DATABASE_URL"])
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url
        admin_engine.dispose()
        cleanup_engine = create_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with cleanup_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{test_name}" WITH (FORCE)')
        cleanup_engine.dispose()


def test_real_pdf_is_indexed_and_retrieved_from_pgvector(integration_database: Database, tmp_path: Path) -> None:
    workspace = WorkspaceRepository(integration_database)
    project = workspace.create(Project, name=f"RAG integration {uuid4().hex[:8]}")
    service = KnowledgeService(integration_database, tmp_path / "knowledge", os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"))
    document, created = service.upload("rag-integration.pdf", pdf_bytes(), project.id)
    assert created
    jobs = BackgroundJobRepository(integration_database)
    jobs.enqueue_unique("document_index", {"document_id": document.id}, f"document:{document.id}")
    worker = BackgroundWorker(jobs, service)
    assert worker.run_once()

    collection = service.create_collection(project.id, "Integration sources")
    service.set_collection_documents(collection.id, [document.id])
    tool = build_knowledge_tool(service, project.id, collection.id)
    assert tool is not None
    result = tool.func("Where is the Mekong Delta source?", 4)
    assert "Mekong Delta source" in result
    assert f"/api/documents/{document.id}/file#page=1" in result

    global_document, created = service.upload(
        "global-rag-integration.pdf",
        pdf_bytes("Global RAG integration needle: Red River source."),
    )
    assert created
    jobs.enqueue_unique("document_index", {"document_id": global_document.id}, f"document:{global_document.id}")
    assert worker.run_once()
    global_tool = build_knowledge_tool(service)
    assert global_tool is not None
    global_result = global_tool.func("Where is the Red River source?", 4)
    assert "Red River source" in global_result
    assert f"/api/documents/{global_document.id}/file#page=1" in global_result
    assert document.id not in global_result
