"""add project knowledge collections

Revision ID: 0015_knowledge_collections
Revises: 0014_chat_controls
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_knowledge_collections"
down_revision = "0014_chat_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_collections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_collections_project_id", "knowledge_collections", ["project_id"])
    op.create_table(
        "knowledge_collection_documents",
        sa.Column("collection_id", sa.String(36), sa.ForeignKey("knowledge_collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.UniqueConstraint("collection_id", "document_id", name="uq_knowledge_collection_document"),
    )
    op.add_column("chats", sa.Column("collection_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_chats_collection_id", "chats", "knowledge_collections", ["collection_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_chats_collection_id", "chats", ["collection_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_collection_id", table_name="chats")
    op.drop_constraint("fk_chats_collection_id", "chats", type_="foreignkey")
    op.drop_column("chats", "collection_id")
    op.drop_table("knowledge_collection_documents")
    op.drop_index("ix_knowledge_collections_project_id", table_name="knowledge_collections")
    op.drop_table("knowledge_collections")
