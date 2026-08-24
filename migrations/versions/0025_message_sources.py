"""store response sources separately from visible content

Revision ID: 0025_message_sources
Revises: 0024_response_feedback
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_message_sources"
down_revision = "0024_response_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("sources", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "sources")
