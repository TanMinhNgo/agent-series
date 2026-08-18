"""add Google connector OAuth persistence and audit logs

Revision ID: 0016_google_connector
Revises: 0015_knowledge_collections
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_google_connector"
down_revision = "0015_knowledge_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connector_slug", sa.String(80), nullable=False, unique=True),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("account_email", sa.String(320), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_connections_connector_slug", "connector_connections", ["connector_slug"])
    op.create_table(
        "oauth_states",
        sa.Column("state", sa.String(128), primary_key=True),
        sa.Column("connector_slug", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_states_connector_slug", "oauth_states", ["connector_slug"])
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])
    op.create_table(
        "connector_audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connector_slug", sa.String(80), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("connector_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(120), nullable=True),
        sa.Column("summary", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_audit_logs_connector_slug", "connector_audit_logs", ["connector_slug"])
    op.create_index("ix_connector_audit_logs_connection_id", "connector_audit_logs", ["connection_id"])
    op.create_index("ix_connector_audit_logs_event_type", "connector_audit_logs", ["event_type"])
    op.create_index("ix_connector_audit_logs_created_at", "connector_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("connector_audit_logs")
    op.drop_table("oauth_states")
    op.drop_table("connector_connections")
