"""track a worker heartbeat so long runs are not reclaimed as stale

Revision ID: 0030_schedule_run_heartbeat
Revises: 0029_schedule_notifications
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_schedule_run_heartbeat"
down_revision = "0029_schedule_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedule_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_schedule_runs_heartbeat_at", "schedule_runs", ["heartbeat_at"])
    # Existing runs have never reported a heartbeat; seed it from their start so
    # recovery keeps treating them exactly as it did before this migration.
    op.execute("UPDATE schedule_runs SET heartbeat_at = started_at WHERE heartbeat_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_schedule_runs_heartbeat_at", table_name="schedule_runs")
    op.drop_column("schedule_runs", "heartbeat_at")
