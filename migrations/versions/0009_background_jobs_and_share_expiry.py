"""add PostgreSQL background jobs and share expiry

Revision ID: 0009_background_jobs
Revises: 0008_schedule_execution
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_background_jobs"
down_revision = "0008_schedule_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_shares", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(48), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_background_jobs_type", "background_jobs", ["type"])
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])
    op.create_index("ix_background_jobs_run_after", "background_jobs", ["run_after"])


def downgrade() -> None:
    op.drop_table("background_jobs")
    op.drop_column("chat_shares", "expires_at")
