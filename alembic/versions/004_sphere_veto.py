"""Add sphere to council_members, veto_level/veto_direction to vote_vetoes

Revision ID: 004_sphere_veto
Revises: 003_council_number
Create Date: 2026-08-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_sphere_veto"
down_revision: Union[str, None] = "003_council_number"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("council_members", sa.Column("sphere", sa.String(64), nullable=True))
    op.add_column("vote_vetoes", sa.Column("veto_level", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("vote_vetoes", sa.Column("veto_direction", sa.String(16), nullable=False, server_default="reject"))


def downgrade() -> None:
    op.drop_column("vote_vetoes", "veto_direction")
    op.drop_column("vote_vetoes", "veto_level")
    op.drop_column("council_members", "sphere")
