"""add personal library assets and recurring schedule fields

Revision ID: 0007_library_assets
Revises: 0006_plugin_catalog
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_library_assets"
down_revision = "0006_plugin_catalog"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("library_assets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("stored_name", sa.String(255), nullable=False, unique=True), sa.Column("mime_type", sa.String(120), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("source", sa.String(24), nullable=False, server_default="upload"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.add_column("schedules", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column("schedules", sa.Column("recurrence", sa.String(16), nullable=False, server_default="once"))
    op.add_column("schedules", sa.Column("status", sa.String(16), nullable=False, server_default="active"))
    op.add_column("schedules", sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_table("library_assets")
    op.drop_column("schedules", "next_run_at"); op.drop_column("schedules", "status"); op.drop_column("schedules", "recurrence"); op.drop_column("schedules", "prompt")
