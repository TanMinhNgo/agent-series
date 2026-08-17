"""add project workspace ownership

Revision ID: 0011_project_workspace
Revises: 0010_job_reliability
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_project_workspace"
down_revision = "0010_job_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("instructions", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("memory_mode", sa.String(24), nullable=False, server_default="default"))
    for table in ("chats", "documents", "library_assets"):
        op.add_column(table, sa.Column("project_id", sa.String(36), nullable=True))
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])
        op.create_foreign_key(f"fk_{table}_project_id", table, "projects", ["project_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    for table in ("library_assets", "documents", "chats"):
        op.drop_constraint(f"fk_{table}_project_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_project_id", table_name=table)
        op.drop_column(table, "project_id")
    op.drop_column("projects", "memory_mode")
    op.drop_column("projects", "instructions")
