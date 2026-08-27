"""add veto_level to council_members

Revision ID: 005
Revises: 004
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

revision = "005_veto_level"
down_revision = "004_sphere_veto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("council_members", sa.Column("veto_level", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("council_members", "veto_level")
