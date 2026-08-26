"""persist delayed retries for transient schedule provider failures

Revision ID: 0027_schedule_run_retries
Revises: 0026_schedule_chat_unread
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_schedule_run_retries"
down_revision = "0026_schedule_chat_unread"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedule_runs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("schedule_runs", sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_schedule_runs_retry_at", "schedule_runs", ["retry_at"])


def downgrade() -> None:
    op.drop_index("ix_schedule_runs_retry_at", table_name="schedule_runs")
    op.drop_column("schedule_runs", "retry_at")
    op.drop_column("schedule_runs", "retry_count")
