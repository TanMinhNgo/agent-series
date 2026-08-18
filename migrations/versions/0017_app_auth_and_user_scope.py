"""add application auth and user ownership

Revision ID: 0017_app_auth_and_user_scope
Revises: 0016_google_connector
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_app_auth_and_user_scope"
down_revision = "0016_google_connector"
branch_labels = None
depends_on = None

OWNED_TABLES = (
    "chats", "chat_memory_chunks", "chat_shares", "chat_messages", "prompt_templates",
    "media_attachments", "library_assets", "artifact_chunks", "projects", "schedules",
    "schedule_runs", "plugins", "connector_connections", "oauth_states", "connector_audit_logs",
    "documents", "document_chunks", "knowledge_collections", "background_jobs",
)


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(320), nullable=False, unique=True), sa.Column("display_name", sa.String(160)), sa.Column("role", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table("auth_identities", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("provider", sa.String(32), nullable=False), sa.Column("provider_subject", sa.String(320), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("provider", "provider_subject", name="uq_auth_identity_provider_subject"))
    op.create_table("auth_sessions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("magic_link_tokens", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(320), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("user_provider_credentials", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("provider", sa.String(32), nullable=False), sa.Column("ciphertext", sa.Text(), nullable=False), sa.Column("key_version", sa.String(32), nullable=False), sa.Column("key_hint", sa.String(8), nullable=False), sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_credential"))
    op.create_table("provider_models", sa.Column("id", sa.String(36), primary_key=True), sa.Column("provider", sa.String(32), nullable=False), sa.Column("model_id", sa.String(200), nullable=False), sa.Column("display_name", sa.String(255), nullable=False), sa.Column("lifecycle", sa.String(32), nullable=False), sa.Column("approved", sa.Boolean(), nullable=False), sa.Column("supports_tools", sa.Boolean(), nullable=False), sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("provider", "model_id", name="uq_provider_model"))
    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", sa.String(36), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        op.create_foreign_key(f"fk_{table}_user_id", table, "users", ["user_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    for table in reversed(OWNED_TABLES):
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
    op.drop_table("provider_models"); op.drop_table("user_provider_credentials"); op.drop_table("magic_link_tokens"); op.drop_table("auth_sessions"); op.drop_table("auth_identities"); op.drop_table("users")
