"""require fresh web sources and email notifications for schedules

Revision ID: 0029_schedule_notifications
Revises: 0028_schedule_provider_model
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_schedule_notifications"
down_revision = "0028_schedule_provider_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("require_web_source", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("schedules", sa.Column("notify_email", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("schedule_runs", sa.Column("email_status", sa.String(length=16), nullable=True))
    op.add_column("schedule_runs", sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("schedule_runs", sa.Column("email_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("schedule_runs", "email_error")
    op.drop_column("schedule_runs", "email_sent_at")
    op.drop_column("schedule_runs", "email_status")
    op.drop_column("schedules", "notify_email")
    op.drop_column("schedules", "require_web_source")
