"""veto roles and remove chair/admin role fields concept (prepare)

Revision ID: 012_veto_roles
Revises: 011_participant_options
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa

revision = "012_veto_roles"
down_revision = "011_participant_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guild_settings",
        sa.Column("veto_role_ids_level1", sa.JSON(), nullable=True),
    )
    op.add_column(
        "guild_settings",
        sa.Column("veto_role_ids_level2", sa.JSON(), nullable=True),
    )
    op.add_column(
        "guild_settings",
        sa.Column("veto_role_ids_level3", sa.JSON(), nullable=True),
    )
    op.add_column(
        "votes",
        sa.Column("veto_window_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "votes",
        sa.Column("vetoed_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("guild_settings") as batch:
        batch.drop_column("admin_role_id")
        batch.drop_column("chair_role_id")


def downgrade() -> None:
    op.add_column(
        "guild_settings",
        sa.Column("admin_role_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "guild_settings",
        sa.Column("chair_role_id", sa.BigInteger(), nullable=True),
    )
    op.drop_column("votes", "vetoed_at")
    op.drop_column("votes", "veto_window_expires_at")
    op.drop_column("guild_settings", "veto_role_ids_level3")
    op.drop_column("guild_settings", "veto_role_ids_level2")
    op.drop_column("guild_settings", "veto_role_ids_level1")
