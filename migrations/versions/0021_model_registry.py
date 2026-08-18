"""persist provider model registry

Revision ID: 0021_model_registry
Revises: 0020_system_admin
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_model_registry"
down_revision = "0020_system_admin"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("provider_models", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("provider_models", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_provider_models_is_active", "provider_models", ["is_active"])
    op.create_table("system_settings", sa.Column("key", sa.String(100), primary_key=True), sa.Column("value", sa.String(500), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_index("ix_provider_models_is_active", table_name="provider_models")
    op.drop_column("provider_models", "updated_at")
    op.drop_column("provider_models", "is_active")
