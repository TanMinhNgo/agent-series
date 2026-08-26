"""store an explicit provider and model for each schedule

Revision ID: 0028_schedule_provider_model
Revises: 0027_schedule_run_retries
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_schedule_provider_model"
down_revision = "0027_schedule_run_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("schedules", sa.Column("model", sa.String(length=160), nullable=True))
    op.execute("""
        UPDATE schedules AS schedule
        SET provider = chat.provider, model = chat.model
        FROM chats AS chat
        WHERE schedule.chat_id = chat.id
          AND schedule.provider IS NULL
          AND schedule.model IS NULL
    """)


def downgrade() -> None:
    op.drop_column("schedules", "model")
    op.drop_column("schedules", "provider")
