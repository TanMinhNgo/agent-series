"""link generated artifact versions to their chat turn

Revision ID: 0033_artifact_message_links
Revises: 0032_workspaces_rbac
"""

from alembic import op
import sqlalchemy as sa


revision = "0033_artifact_message_links"
down_revision = "0032_workspaces_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_message_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("asset_id", sa.String(length=36), sa.ForeignKey("library_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.String(length=36), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_message_id", sa.String(length=36), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assistant_message_id", sa.String(length=36), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
        sa.UniqueConstraint("asset_id", "assistant_message_id", name="uq_artifact_message_link"),
    )
    for column in ("asset_id", "chat_id", "user_message_id", "assistant_message_id", "user_id", "workspace_id"):
        op.create_index(f"ix_artifact_message_links_{column}", "artifact_message_links", [column])


def downgrade() -> None:
    op.drop_table("artifact_message_links")
