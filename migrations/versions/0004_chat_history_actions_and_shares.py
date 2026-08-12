"""add chat history actions and public snapshots

Revision ID: 0004_chat_history_actions
Revises: 0003_chat_message_content_blocks
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_chat_history_actions"
down_revision = "0003_chat_message_content_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("chats", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("chat_shares", sa.Column("id", sa.String(36), primary_key=True), sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("token", sa.String(64), nullable=False, unique=True), sa.Column("title", sa.String(160), nullable=False), sa.Column("provider", sa.String(32), nullable=False), sa.Column("model", sa.String(160), nullable=False), sa.Column("messages", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_chat_shares_token", "chat_shares", ["token"])


def downgrade() -> None:
    op.drop_index("ix_chat_shares_token", table_name="chat_shares")
    op.drop_table("chat_shares")
    op.drop_column("chats", "archived")
    op.drop_column("chats", "pinned")
