"""Account settings and Google avatar."""
from alembic import op
import sqlalchemy as sa

revision = "0040_user_settings"
down_revision = "0039_workflow_guards"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("avatar_url", sa.String(2048), nullable=True))
    op.add_column("user_preferences", sa.Column("theme", sa.String(16), nullable=False, server_default="system"))
    op.add_column("user_preferences", sa.Column("custom_instructions", sa.Text(), nullable=False, server_default=""))
    op.add_column("user_preferences", sa.Column("auto_learn", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("user_preferences", sa.Column("default_provider", sa.String(32), nullable=True))
    op.add_column("user_preferences", sa.Column("default_model", sa.String(160), nullable=True))


def downgrade():
    for column in ("default_model", "default_provider", "auto_learn", "custom_instructions", "theme"):
        op.drop_column("user_preferences", column)
    op.drop_column("users", "avatar_url")
