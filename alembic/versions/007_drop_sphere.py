"""drop sphere column from council_members

Revision ID: 007_drop_sphere
Revises: 006_vote_messages
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = "007_drop_sphere"
down_revision = "006_vote_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("council_members", "sphere")


def downgrade() -> None:
    op.add_column("council_members", sa.Column("sphere", sa.String(64), nullable=True))