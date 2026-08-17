"""add schedule execution state and run history

Revision ID: 0008_schedule_execution
Revises: 0007_library_assets
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_schedule_execution"
down_revision = "0007_library_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("chat_id", sa.String(36), sa.ForeignKey("chats.id", ondelete="SET NULL"), nullable=True))
    op.add_column("schedules", sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("schedules", sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Ho_Chi_Minh"))
    op.create_table(
        "schedule_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schedule_id", sa.String(36), sa.ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("schedule_id", "scheduled_for", name="uq_schedule_runs_schedule_time"),
    )
    op.create_index("ix_schedule_runs_schedule_id", "schedule_runs", ["schedule_id"])
    op.create_index("ix_schedule_runs_scheduled_for", "schedule_runs", ["scheduled_for"])


def downgrade() -> None:
    op.drop_table("schedule_runs")
    op.drop_column("schedules", "timezone")
    op.drop_column("schedules", "last_run_at")
    op.drop_column("schedules", "chat_id")
