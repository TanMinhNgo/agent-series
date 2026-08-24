"""mark AI-created schedule chats as unread

Revision ID: 0026_schedule_chat_unread
Revises: 0025_message_sources
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_schedule_chat_unread"
down_revision = "0025_message_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("is_unread", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_chats_is_unread", "chats", ["is_unread"])


def downgrade() -> None:
    op.drop_index("ix_chats_is_unread", table_name="chats")
    op.drop_column("chats", "is_unread")
