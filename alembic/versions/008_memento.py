"""add memento flag to votes

Revision ID: 008_memento
Revises: 007_drop_sphere
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "008_memento"
down_revision = "007_drop_sphere"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("votes", sa.Column("memento", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("votes", "memento")