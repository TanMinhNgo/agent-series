"""add response feedback and user personalization

Revision ID: 0024_response_feedback
Revises: 0023_per_user_plugin_connections
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_response_feedback"
down_revision = "0023_per_user_plugin_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "response_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "message_id", name="uq_response_feedback_user_message"),
    )
    op.create_index("ix_response_feedback_user_id", "response_feedback", ["user_id"])
    op.create_index("ix_response_feedback_message_id", "response_feedback", ["message_id"])
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("style_scores", sa.JSON(), nullable=False),
        sa.Column("topic_counts", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user"),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_table("user_preferences")
    op.drop_index("ix_response_feedback_message_id", table_name="response_feedback")
    op.drop_index("ix_response_feedback_user_id", table_name="response_feedback")
    op.drop_table("response_feedback")
