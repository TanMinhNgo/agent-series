"""rename chat message bookmarks to pins

Revision ID: 0019_chat_message_pins
Revises: 0018_google_signin
"""

from alembic import op

revision = "0019_chat_message_pins"
down_revision = "0018_google_signin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("chat_messages", "bookmarked", new_column_name="pinned")


def downgrade() -> None:
    op.alter_column("chat_messages", "pinned", new_column_name="bookmarked")
