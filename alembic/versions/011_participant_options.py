"""add option_ids and revoked_at to vote participants

Revision ID: 011_participant_options
Revises: 010_operator_access
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa

revision = "011_participant_options"
down_revision = "010_operator_access"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vote_participants", sa.Column("option_ids", sa.JSON(), nullable=True))
    op.add_column("vote_participants", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("vote_participants", "revoked_at")
    op.drop_column("vote_participants", "option_ids")
