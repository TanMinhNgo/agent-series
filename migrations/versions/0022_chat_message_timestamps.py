"""add durable timestamps to chat messages

Revision ID: 0022_message_timestamps
Revises: 0021_model_registry
"""
from alembic import op
import sqlalchemy as sa


revision = "0022_message_timestamps"
down_revision = "0021_model_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    # Historical rows did not retain per-message time. The chat update time is
    # the closest durable timestamp available and keeps legacy transcripts valid.
    op.execute(
        """
        UPDATE chat_messages
        SET created_at = COALESCE(
          (SELECT chats.updated_at FROM chats WHERE chats.id = chat_messages.chat_id),
          CURRENT_TIMESTAMP
        )
        WHERE created_at IS NULL
        """
    )
    op.alter_column("chat_messages", "created_at", nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_column("chat_messages", "created_at")
