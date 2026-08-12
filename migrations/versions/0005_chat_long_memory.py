"""add chat long-term memory

Revision ID: 0005_chat_long_memory
Revises: 0004_chat_history_actions
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0005_chat_long_memory"
down_revision = "0004_chat_history_actions"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("chats", sa.Column("context_source_chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="SET NULL"), nullable=True))
    op.create_table("chat_memory_chunks", sa.Column("id", sa.String(36), primary_key=True), sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(16), nullable=False), sa.Column("content", sa.Text, nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False), sa.Column("chunk_index", sa.Integer, nullable=False), sa.Column("embedding", Vector(384), nullable=False), sa.Column("forgotten", sa.Boolean, nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("chat_id", "fingerprint", "chunk_index", name="uq_chat_memory_chunk"))
    op.create_index("ix_chat_memory_chunks_chat_id", "chat_memory_chunks", ["chat_id"])
    op.create_index("ix_chat_memory_chunks_fingerprint", "chat_memory_chunks", ["fingerprint"])
    op.create_index("ix_chat_memory_chunks_forgotten", "chat_memory_chunks", ["forgotten"])

def downgrade() -> None:
    op.drop_table("chat_memory_chunks")
    op.drop_column("chats", "context_source_chat_id")
