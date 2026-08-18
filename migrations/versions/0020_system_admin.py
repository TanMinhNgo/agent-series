"""add system administration state and audit log

Revision ID: 0020_system_admin
Revises: 0019_chat_message_pins
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_system_admin"
down_revision = "0019_chat_message_pins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_table(
        "system_audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_system_audit_logs_actor_user_id", "system_audit_logs", ["actor_user_id"])
    op.create_index("ix_system_audit_logs_subject_user_id", "system_audit_logs", ["subject_user_id"])
    op.create_index("ix_system_audit_logs_event_type", "system_audit_logs", ["event_type"])
    op.create_index("ix_system_audit_logs_created_at", "system_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("system_audit_logs")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_column("users", "is_active")
