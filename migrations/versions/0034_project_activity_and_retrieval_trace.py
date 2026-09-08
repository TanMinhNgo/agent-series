"""add project activity and assistant retrieval traces

Revision ID: 0034_project_activity_trace
Revises: 0033_artifact_message_links
"""

from alembic import op
import sqlalchemy as sa


revision = "0034_project_activity_trace"
down_revision = "0033_artifact_message_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_activities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=True),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_table(
        "message_retrieval_traces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_kind", sa.String(24), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("chunk_ref", sa.String(80), nullable=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
    )
    for table, columns in {
        "project_activities": ("project_id", "actor_user_id", "event_type", "subject_id", "created_at", "user_id", "workspace_id"),
        "message_retrieval_traces": ("message_id", "project_id", "source_id", "user_id", "workspace_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    op.drop_table("message_retrieval_traces")
    op.drop_table("project_activities")
