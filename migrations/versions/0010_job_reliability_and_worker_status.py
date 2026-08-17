"""add job deduplication and worker status

Revision ID: 0010_job_reliability
Revises: 0009_background_jobs
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_job_reliability"
down_revision = "0009_background_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("background_jobs", sa.Column("dedupe_key", sa.String(160), nullable=True))
    op.create_index(
        "uq_background_jobs_active_dedupe",
        "background_jobs",
        ["type", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
        sqlite_where=sa.text("status IN ('queued', 'running') AND dedupe_key IS NOT NULL"),
    )
    op.create_table(
        "worker_status",
        sa.Column("worker_id", sa.String(48), primary_key=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_job_type", sa.String(48), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_status")
    op.drop_index("uq_background_jobs_active_dedupe", table_name="background_jobs")
    op.drop_column("background_jobs", "dedupe_key")
