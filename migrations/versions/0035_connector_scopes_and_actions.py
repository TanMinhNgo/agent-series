"""add project connector scopes and external action approvals

Revision ID: 0035_connector_scopes
Revises: 0034_project_activity_trace
"""

from alembic import op
import sqlalchemy as sa

revision = "0035_connector_scopes"
down_revision = "0034_project_activity_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("project_connector_scopes",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_slug", sa.String(80), nullable=False), sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
        sa.UniqueConstraint("project_id", "connector_slug", name="uq_project_connector_scope"))
    op.create_table("external_action_proposals",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False), sa.Column("config", sa.JSON(), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("error", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True))
    for table, columns in {"project_connector_scopes": ("project_id", "connector_slug", "user_id", "workspace_id"), "external_action_proposals": ("project_id", "action_type", "status", "expires_at", "user_id", "workspace_id")}.items():
        for column in columns: op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    op.drop_table("external_action_proposals")
    op.drop_table("project_connector_scopes")
