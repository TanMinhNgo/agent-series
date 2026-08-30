"""add multi-workspace membership and scope existing user data

Revision ID: 0032_workspaces_rbac
Revises: 0031_imagekit_storage
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0032_workspaces_rbac"
down_revision = "0031_imagekit_storage"
branch_labels = None
depends_on = None


OWNED_TABLES = (
    "chats", "chat_memory_chunks", "chat_shares", "chat_messages", "response_feedback",
    "user_preferences", "prompt_templates", "media_attachments", "library_assets",
    "artifact_chunks", "projects", "schedules", "schedule_runs", "plugins",
    "connector_connections", "oauth_states", "connector_audit_logs", "documents",
    "document_chunks", "knowledge_collections", "background_jobs",
)
USERS_ID_FOREIGN_KEY = "users.id"
SET_NULL = "SET NULL"


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("is_personal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey(USERS_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspaces_created_by_user_id", "workspaces", ["created_by_user_id"])
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey(USERS_ID_FOREIGN_KEY, ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("invited_by_user_id", sa.String(36), sa.ForeignKey(USERS_ID_FOREIGN_KEY, ondelete=SET_NULL), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "email", name="uq_workspace_invitation_email"),
    )
    op.create_index("ix_workspace_invitations_workspace_id", "workspace_invitations", ["workspace_id"])
    op.create_index("ix_workspace_invitations_email", "workspace_invitations", ["email"])
    op.create_index("ix_workspace_invitations_expires_at", "workspace_invitations", ["expires_at"])
    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("workspace_id", sa.String(36), nullable=True))
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
        op.create_foreign_key(f"fk_{table}_workspace_id", table, "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE")

    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, COALESCE(display_name, email) FROM users")).fetchall()
    for user_id, label in users:
        workspace_id = str(uuid4())
        bind.execute(sa.text("INSERT INTO workspaces (id, name, is_personal, created_by_user_id, created_at, updated_at) VALUES (:id, :name, true, :user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), {"id": workspace_id, "name": f"{label} - Personal", "user_id": user_id})
        bind.execute(sa.text("INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at) VALUES (:id, :workspace_id, :user_id, 'owner', CURRENT_TIMESTAMP)"), {"id": str(uuid4()), "workspace_id": workspace_id, "user_id": user_id})
        for table in OWNED_TABLES:
            bind.execute(sa.text(f"UPDATE {table} SET workspace_id = :workspace_id WHERE user_id = :user_id"), {"workspace_id": workspace_id, "user_id": user_id})


def downgrade() -> None:
    for table in reversed(OWNED_TABLES):
        op.drop_constraint(f"fk_{table}_workspace_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_column(table, "workspace_id")
    op.drop_table("workspace_invitations")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
