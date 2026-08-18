"""replace magic link tokens with Google Sign-In

Revision ID: 0018_google_signin
Revises: 0017_app_auth_and_user_scope
"""

from alembic import op

revision = "0018_google_signin"
down_revision = "0017_app_auth_and_user_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("magic_link_tokens")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "magic_link_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
