"""add versioned project artifact sources

Revision ID: 0013_artifact_sources
Revises: 0012_project_deletion
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "0013_artifact_sources"
down_revision = "0012_project_deletion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("library_assets", sa.Column("artifact_id", sa.String(36), nullable=True))
    op.add_column("library_assets", sa.Column("version", sa.Integer(), nullable=True))
    op.add_column("library_assets", sa.Column("is_project_source", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("library_assets", sa.Column("index_status", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("library_assets", sa.Column("index_error", sa.Text(), nullable=True))
    op.execute("UPDATE library_assets SET artifact_id = id, version = 1, is_project_source = (project_id IS NOT NULL)")
    op.alter_column("library_assets", "artifact_id", nullable=False)
    op.alter_column("library_assets", "version", nullable=False)
    op.create_index("ix_library_assets_artifact_id", "library_assets", ["artifact_id"])
    op.create_index("ix_library_assets_is_project_source", "library_assets", ["is_project_source"])
    op.create_unique_constraint("uq_library_assets_artifact_version", "library_assets", ["artifact_id", "version"])
    op.create_table(
        "artifact_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("library_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.UniqueConstraint("asset_id", "chunk_index", name="uq_artifact_chunks_asset_index"),
    )
    op.create_index("ix_artifact_chunks_asset_id", "artifact_chunks", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_artifact_chunks_asset_id", table_name="artifact_chunks")
    op.drop_table("artifact_chunks")
    op.drop_constraint("uq_library_assets_artifact_version", "library_assets", type_="unique")
    op.drop_index("ix_library_assets_is_project_source", table_name="library_assets")
    op.drop_index("ix_library_assets_artifact_id", table_name="library_assets")
    op.drop_column("library_assets", "index_error")
    op.drop_column("library_assets", "index_status")
    op.drop_column("library_assets", "is_project_source")
    op.drop_column("library_assets", "version")
    op.drop_column("library_assets", "artifact_id")
