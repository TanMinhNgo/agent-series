"""add templates and chat controls

Revision ID: 0014_chat_controls
Revises: 0013_artifact_sources
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_chat_controls"
down_revision = "0013_artifact_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("parent_chat_id", sa.String(36), nullable=True))
    op.add_column("chats", sa.Column("branch_from_position", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_chats_parent_chat_id", "chats", "chats", ["parent_chat_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_chats_parent_chat_id", "chats", ["parent_chat_id"])
    op.add_column("chat_messages", sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_chat_messages_bookmarked", "chat_messages", ["bookmarked"])
    op.execute("CREATE INDEX ix_chat_messages_content_fts ON chat_messages USING gin (to_tsvector('simple', content))")
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prompt_templates_project_id", "prompt_templates", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_prompt_templates_project_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")
    op.execute("DROP INDEX ix_chat_messages_content_fts")
    op.drop_index("ix_chat_messages_bookmarked", table_name="chat_messages")
    op.drop_column("chat_messages", "bookmarked")
    op.drop_index("ix_chats_parent_chat_id", table_name="chats")
    op.drop_constraint("fk_chats_parent_chat_id", "chats", type_="foreignkey")
    op.drop_column("chats", "branch_from_position")
    op.drop_column("chats", "parent_chat_id")
