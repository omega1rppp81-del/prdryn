"""add isolation flag to guild settings

Revision ID: 009_isolation
Revises: 008_memento
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "009_isolation"
down_revision = "008_memento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guild_settings",
        sa.Column("isolation_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("guild_settings", "isolation_enabled")