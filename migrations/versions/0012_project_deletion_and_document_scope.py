"""make project deletion reliable and scope document deduplication

Revision ID: 0012_project_deletion
Revises: 0011_project_workspace
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_project_deletion"
down_revision = "0011_project_workspace"
branch_labels = None
depends_on = None

GLOBAL_DOCUMENT_SCOPE = "__library__"


def upgrade() -> None:
    op.add_column("documents", sa.Column("scope_key", sa.String(36), nullable=True))
    op.execute(
        sa.text(
            "UPDATE documents SET scope_key = COALESCE(project_id, :global_scope) "
            "WHERE scope_key IS NULL"
        ).bindparams(global_scope=GLOBAL_DOCUMENT_SCOPE)
    )
    op.alter_column("documents", "scope_key", nullable=False)
    op.drop_constraint("documents_sha256_key", "documents", type_="unique")
    op.create_unique_constraint("uq_documents_scope_sha256", "documents", ["scope_key", "sha256"])

    op.drop_constraint("schedules_project_id_fkey", "schedules", type_="foreignkey")
    op.create_foreign_key(
        "schedules_project_id_fkey",
        "schedules",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("schedules_project_id_fkey", "schedules", type_="foreignkey")
    op.create_foreign_key(
        "schedules_project_id_fkey",
        "schedules",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("uq_documents_scope_sha256", "documents", type_="unique")
    op.create_unique_constraint("documents_sha256_key", "documents", ["sha256"])
    op.drop_column("documents", "scope_key")
