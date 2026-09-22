"""Leases, retries and cancellation for workflow runs."""
from alembic import op
import sqlalchemy as sa

revision = "0038_workflow_recovery"
down_revision = "0037_workflows"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("schedules", sa.Column("workflow_id", sa.String(36), sa.ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_schedules_workflow_id", "schedules", ["workflow_id"])
    op.add_column("workflow_runs", sa.Column("idempotency_key", sa.String(160), nullable=True))
    op.add_column("workflow_runs", sa.Column("lease_token", sa.String(36), nullable=True))
    op.add_column("workflow_runs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workflow_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workflow_runs", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_workflow_runs_idempotency_key", "workflow_runs", ["idempotency_key"])
    op.create_index("ix_workflow_runs_lease_until", "workflow_runs", ["lease_until"])
    op.add_column("workflow_step_runs", sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("workflow_step_runs", sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_workflow_step_runs_retry_at", "workflow_step_runs", ["retry_at"])

def downgrade():
    op.drop_index("ix_schedules_workflow_id", table_name="schedules")
    op.drop_column("schedules", "workflow_id")
    op.drop_index("ix_workflow_step_runs_retry_at", table_name="workflow_step_runs")
    op.drop_column("workflow_step_runs", "retry_at")
    op.drop_column("workflow_step_runs", "attempt")
    op.drop_index("ix_workflow_runs_lease_until", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_idempotency_key", table_name="workflow_runs")
    op.drop_column("workflow_runs", "cancel_requested")
    op.drop_column("workflow_runs", "heartbeat_at")
    op.drop_column("workflow_runs", "lease_until")
    op.drop_column("workflow_runs", "lease_token")
    op.drop_column("workflow_runs", "idempotency_key")
