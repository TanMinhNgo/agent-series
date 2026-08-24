"""scope plugin and connector uniqueness to each user

Revision ID: 0023_per_user_plugin_connections
Revises: 0022_message_timestamps
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_per_user_plugin_connections"
down_revision = "0022_message_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("plugins_slug_key", "plugins", type_="unique")
    op.drop_constraint("uq_plugins_catalog_slug", "plugins", type_="unique")
    op.drop_constraint("connector_connections_connector_slug_key", "connector_connections", type_="unique")
    op.create_unique_constraint("uq_plugins_user_slug", "plugins", ["user_id", "slug"])
    op.create_unique_constraint("uq_plugins_user_catalog_slug", "plugins", ["user_id", "catalog_slug"])
    op.create_unique_constraint("uq_connector_connections_user_slug", "connector_connections", ["user_id", "connector_slug"])


def downgrade() -> None:
    op.drop_constraint("uq_connector_connections_user_slug", "connector_connections", type_="unique")
    op.drop_constraint("uq_plugins_user_catalog_slug", "plugins", type_="unique")
    op.drop_constraint("uq_plugins_user_slug", "plugins", type_="unique")
    op.create_unique_constraint("connector_connections_connector_slug_key", "connector_connections", ["connector_slug"])
    op.create_unique_constraint("uq_plugins_catalog_slug", "plugins", ["catalog_slug"])
    op.create_unique_constraint("plugins_slug_key", "plugins", ["slug"])
