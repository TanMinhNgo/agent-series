"""track remote ImageKit storage for user files

Revision ID: 0031_imagekit_storage
Revises: 0030_schedule_run_heartbeat
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_imagekit_storage"
down_revision = "0030_schedule_run_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("media_attachments", "library_assets", "documents"):
        op.add_column(table, sa.Column("storage_provider", sa.String(length=32), nullable=False, server_default="local"))
        op.add_column(table, sa.Column("storage_file_id", sa.String(length=128), nullable=True))
        op.create_unique_constraint(f"uq_{table}_storage_file_id", table, ["storage_file_id"])
        op.alter_column(table, "storage_provider", server_default=None)


def downgrade() -> None:
    for table in ("documents", "library_assets", "media_attachments"):
        op.drop_constraint(f"uq_{table}_storage_file_id", table, type_="unique")
        op.drop_column(table, "storage_file_id")
        op.drop_column(table, "storage_provider")
