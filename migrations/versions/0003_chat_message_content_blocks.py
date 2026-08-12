"""store safe rich-response blocks

Revision ID: 0003_chat_message_content_blocks
Revises: 0002_workspace_media
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_chat_message_content_blocks"
down_revision = "0002_workspace_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("content_blocks", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "content_blocks")
