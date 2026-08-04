"""create chat and RAG storage

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("chats", sa.Column("id", sa.String(36), primary_key=True), sa.Column("title", sa.String(160), nullable=False), sa.Column("provider", sa.String(32), nullable=False), sa.Column("model", sa.String(160), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("chat_messages", sa.Column("id", sa.String(36), primary_key=True), sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False), sa.Column("position", sa.Integer, nullable=False), sa.Column("role", sa.String(16), nullable=False), sa.Column("content", sa.Text, nullable=False), sa.Column("tool_call_id", sa.String(160)), sa.Column("tool_name", sa.String(160)), sa.Column("tool_calls", sa.JSON))
    op.create_index("ix_chat_messages_chat_id", "chat_messages", ["chat_id"])
    op.create_table("documents", sa.Column("id", sa.String(36), primary_key=True), sa.Column("original_name", sa.String(255), nullable=False), sa.Column("stored_name", sa.String(255), unique=True, nullable=False), sa.Column("sha256", sa.String(64), unique=True, nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("page_count", sa.Integer), sa.Column("error", sa.Text), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_table("document_chunks", sa.Column("id", sa.String(36), primary_key=True), sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False), sa.Column("chunk_index", sa.Integer, nullable=False), sa.Column("page_number", sa.Integer, nullable=False), sa.Column("content", sa.Text, nullable=False), sa.Column("embedding", Vector(384), nullable=False))
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("chat_messages")
    op.drop_table("chats")
