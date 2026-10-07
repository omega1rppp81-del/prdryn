"""add operator access to guild settings

Revision ID: 010_operator_access
Revises: 009_isolation
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa

revision = "010_operator_access"
down_revision = "009_isolation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guild_settings", sa.Column("operator_access_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("guild_settings", sa.Column("operator_user_id", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("guild_settings", "operator_user_id")
    op.drop_column("guild_settings", "operator_access_enabled")
