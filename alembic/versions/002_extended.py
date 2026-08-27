"""Add comments, templates, rounds, vetoes, bundles, stats

Revision ID: 002_extended
Revises: 001_initial
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_extended"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vote_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_id", sa.Integer(), sa.ForeignKey("votes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_edited", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_comments_vote_id", "vote_comments", ["vote_id"])

    op.create_table(
        "vote_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("vote_type", sa.String(32), server_default="standard", nullable=False),
        sa.Column("anonymity_level", sa.String(32), server_default="open", nullable=False),
        sa.Column("change_mode", sa.String(32), server_default="none", nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("quorum_rule", sa.String(32), server_default="min_percent", nullable=False),
        sa.Column("quorum_value", sa.Float(), nullable=True),
        sa.Column("majority_rule", sa.String(32), server_default="simple", nullable=False),
        sa.Column("tie_rule", sa.String(32), server_default="not_accepted", nullable=False),
        sa.Column("default_duration_hours", sa.Integer(), server_default="48", nullable=False),
        sa.Column("custom_options", sa.JSON(), nullable=True),
        sa.Column("default_title", sa.String(256), nullable=True),
        sa.Column("default_description", sa.Text(), nullable=True),
        sa.Column("default_reason", sa.Text(), nullable=True),
        sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_templates_guild_id", "vote_templates", ["guild_id"])

    op.create_table(
        "vote_rounds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_id", sa.Integer(), sa.ForeignKey("votes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("options_snapshot", sa.JSON(), nullable=True),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eliminated_options", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_rounds_vote_id", "vote_rounds", ["vote_id"])

    op.create_table(
        "vote_vetoes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_id", sa.Integer(), sa.ForeignKey("votes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_vetoes_vote_id", "vote_vetoes", ["vote_id"])

    op.create_table(
        "vote_bundles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("vote_ids", sa.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_bundles_guild_id", "vote_bundles", ["guild_id"])

    op.create_table(
        "user_vote_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("total_votes_cast", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_mandatory", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mandatory_attended", sa.Integer(), server_default="0", nullable=False),
        sa.Column("votes_changed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_vote_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "user_id", name="uq_user_vote_stats"),
    )
    op.create_index("ix_user_vote_stats_guild_id", "user_vote_stats", ["guild_id"])
    op.create_index("ix_user_vote_stats_user_id", "user_vote_stats", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_vote_stats")
    op.drop_table("vote_bundles")
    op.drop_table("vote_vetoes")
    op.drop_table("vote_rounds")
    op.drop_table("vote_templates")
    op.drop_table("vote_comments")
