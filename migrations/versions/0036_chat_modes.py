"""add persisted chat modes

Revision ID: 0036_chat_modes
Revises: 0035_connector_scopes
"""

from alembic import op
import sqlalchemy as sa

revision = "0036_chat_modes"
down_revision = "0035_connector_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("mode", sa.String(length=16), nullable=False, server_default="standard"))
    op.alter_column("chats", "mode", server_default=None)
    op.add_column("chat_messages", sa.Column("generated_asset_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "generated_asset_ids")
    op.drop_column("chats", "mode")
