"""add workspace entities and multimodal attachments

Revision ID: 0002_workspace_media
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_workspace_media"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("attachments", sa.JSON(), nullable=True))
    op.create_table("media_attachments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("original_name", sa.String(255), nullable=False), sa.Column("stored_name", sa.String(255), unique=True, nullable=False), sa.Column("mime_type", sa.String(80), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("projects", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("description", sa.Text()), sa.Column("status", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("schedules", sa.Column("id", sa.String(36), primary_key=True), sa.Column("title", sa.String(160), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True)), sa.Column("notes", sa.Text()), sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("plugins", sa.Column("id", sa.String(36), primary_key=True), sa.Column("slug", sa.String(80), unique=True, nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("description", sa.Text()), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("config", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("plugins")
    op.drop_table("schedules")
    op.drop_table("projects")
    op.drop_table("media_attachments")
    op.drop_column("chat_messages", "attachments")
