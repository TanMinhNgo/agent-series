"""Enforce workflow trigger uniqueness without deleting existing runs."""
from alembic import op
import sqlalchemy as sa

revision = "0039_workflow_guards"
down_revision = "0038_workflow_recovery"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve all historical runs; only the earliest retains a duplicate key.
    op.execute(sa.text('''
        UPDATE workflow_runs SET idempotency_key = NULL WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY workflow_id, user_id, idempotency_key ORDER BY created_at, id
                ) AS n FROM workflow_runs WHERE idempotency_key IS NOT NULL
            ) duplicates WHERE n > 1
        )
    '''))
    op.create_unique_constraint("uq_workflow_trigger", "workflow_runs", ["workflow_id", "user_id", "idempotency_key"])


def downgrade():
    op.drop_constraint("uq_workflow_trigger", "workflow_runs", type_="unique")
