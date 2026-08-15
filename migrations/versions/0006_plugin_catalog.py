"""add plugin catalog metadata

Revision ID: 0006_plugin_catalog
Revises: 0005_chat_long_memory
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_plugin_catalog"
down_revision = "0005_chat_long_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plugins", sa.Column("catalog_slug", sa.String(80), nullable=True))
    op.add_column("plugins", sa.Column("category", sa.String(48), nullable=True))
    op.add_column("plugins", sa.Column("capabilities", sa.JSON(), nullable=True))
    op.add_column("plugins", sa.Column("connection_status", sa.String(32), nullable=True))
    op.create_unique_constraint("uq_plugins_catalog_slug", "plugins", ["catalog_slug"])


def downgrade() -> None:
    op.drop_constraint("uq_plugins_catalog_slug", "plugins", type_="unique")
    op.drop_column("plugins", "connection_status")
    op.drop_column("plugins", "capabilities")
    op.drop_column("plugins", "category")
    op.drop_column("plugins", "catalog_slug")
