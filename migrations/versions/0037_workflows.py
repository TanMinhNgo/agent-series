"""Manual Project workflows and step results."""
from alembic import op
import sqlalchemy as sa

revision = "0037_workflows"
down_revision = "0036_chat_modes"
branch_labels = None
depends_on = None


def ownership():
    return [sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)]


def upgrade():
    op.create_table("workflows",
        sa.Column("id", sa.String(36), primary_key=True), *ownership(),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("workflow_runs",
        sa.Column("id", sa.String(36), primary_key=True), *ownership(),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True), sa.Column("error", sa.Text()),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("library_assets.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.create_table("workflow_step_runs",
        sa.Column("id", sa.String(36), primary_key=True), *ownership(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("step_id", sa.String(32), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("output", sa.JSON()), sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "step_id", name="uq_workflow_run_step"))


def downgrade():
    op.drop_table("workflow_step_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflows")
