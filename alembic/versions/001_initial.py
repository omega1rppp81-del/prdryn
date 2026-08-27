"""Initial tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guild_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("vote_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("log_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("admin_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("council_role_id", sa.BigInteger(), nullable=True),
        sa.Column("admin_role_id", sa.BigInteger(), nullable=True),
        sa.Column("auditor_role_id", sa.BigInteger(), nullable=True),
        sa.Column("chair_role_id", sa.BigInteger(), nullable=True),
        sa.Column("timezone", sa.String(64), server_default="Europe/Moscow", nullable=False),
        sa.Column("numbering_format", sa.String(32), server_default="sequential", nullable=False),
        sa.Column("embed_color", sa.Integer(), server_default="5791026", nullable=False),
        sa.Column("message_template", sa.Text(), nullable=True),
        sa.Column("default_duration_hours", sa.Integer(), server_default="48", nullable=False),
        sa.Column("default_vote_type", sa.String(32), server_default="standard", nullable=False),
        sa.Column("default_anonymity", sa.String(32), server_default="open", nullable=False),
        sa.Column("default_quorum_rule", sa.String(32), server_default="min_percent", nullable=False),
        sa.Column("default_change_mode", sa.String(32), server_default="none", nullable=False),
        sa.Column("reminder_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("reminder_hours_before", sa.Integer(), server_default="4", nullable=False),
        sa.Column("reminder_interval_hours", sa.Integer(), server_default="6", nullable=False),
        sa.Column("data_retention_days", sa.Integer(), server_default="365", nullable=False),
        sa.Column("auto_archive_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("next_vote_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id"),
    )

    op.create_table(
        "council_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=True),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "user_id", name="uq_council_member"),
    )
    op.create_index("ix_council_members_guild_id", "council_members", ["guild_id"])
    op.create_index("ix_council_members_user_id", "council_members", ["user_id"])

    op.create_table(
        "votes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_number", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("short_title", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("additional_info", sa.Text(), nullable=True),
        sa.Column("category", sa.String(128), nullable=True),
        sa.Column("priority", sa.String(32), server_default="normal", nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("linked_documents", sa.JSON(), nullable=True),
        sa.Column("discussion_link", sa.String(512), nullable=True),
        sa.Column("creator_id", sa.BigInteger(), nullable=False),
        sa.Column("creator_name", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("vote_type", sa.String(32), server_default="standard", nullable=False),
        sa.Column("anonymity_level", sa.String(32), server_default="open", nullable=False),
        sa.Column("change_mode", sa.String(32), server_default="none", nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("allow_after_join", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("leave_rule", sa.String(32), server_default="keep_vote", nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("mandatory_source", sa.String(32), nullable=True),
        sa.Column("mandatory_role_id", sa.BigInteger(), nullable=True),
        sa.Column("mandatory_user_ids", sa.JSON(), nullable=True),
        sa.Column("mandatory_snapshot_at", sa.String(32), server_default="start", nullable=False),
        sa.Column("quorum_rule", sa.String(32), server_default="min_percent", nullable=False),
        sa.Column("quorum_value", sa.Float(), nullable=True),
        sa.Column("quorum_required_role_ids", sa.JSON(), nullable=True),
        sa.Column("quorum_on_fail", sa.String(32), server_default="auto_reject", nullable=False),
        sa.Column("majority_rule", sa.String(32), server_default="simple", nullable=False),
        sa.Column("tie_rule", sa.String(32), server_default="not_accepted", nullable=False),
        sa.Column("abstain_counted_in_majority", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("min_affirmative_votes", sa.Integer(), nullable=True),
        sa.Column("result_confirmation", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("show_results_immediately", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("show_voter_list", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("show_percentages", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("min_votes_for_results", sa.Integer(), server_default="0", nullable=False),
        sa.Column("allow_early_end", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("auto_extend_on_no_quorum", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("auto_extend_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_paused_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("approval_status", sa.String(32), server_default="none", nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        sa.Column("custom_options", sa.JSON(), nullable=True),
        sa.Column("max_multi_choices", sa.Integer(), nullable=True),
        sa.Column("weights", sa.JSON(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("completion_reason", sa.Text(), nullable=True),
        sa.Column("related_vote_id", sa.Integer(), nullable=True),
        sa.Column("chain_ids", sa.JSON(), nullable=True),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("quorum_reached", sa.Boolean(), nullable=True),
        sa.Column("final_decision", sa.String(64), nullable=True),
        sa.Column("guild_settings_id", sa.Integer(), sa.ForeignKey("guild_settings.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index("ix_votes_guild_id", "votes", ["guild_id"])
    op.create_index("ix_votes_status", "votes", ["status"])

    op.create_table(
        "vote_options",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_id", sa.Integer(), sa.ForeignKey("votes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("emoji", sa.String(32), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("description", sa.String(256), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_options_vote_id", "vote_options", ["vote_id"])

    op.create_table(
        "vote_participants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_id", sa.Integer(), sa.ForeignKey("votes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("council_members.id"), nullable=True),
        sa.Column("option_id", sa.Integer(), sa.ForeignKey("vote_options.id"), nullable=True),
        sa.Column("has_voted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("voted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("change_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vote_id", "user_id", name="uq_vote_participant"),
    )
    op.create_index("ix_vote_participants_vote_id", "vote_participants", ["vote_id"])
    op.create_index("ix_vote_participants_user_id", "vote_participants", ["user_id"])

    op.create_table(
        "vote_mandatory_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_id", sa.Integer(), sa.ForeignKey("votes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=True),
        sa.Column("has_voted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_exempt", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("exempt_reason", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vote_mandatory_members_vote_id", "vote_mandatory_members", ["vote_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vote_id", sa.Integer(), sa.ForeignKey("votes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("source", sa.String(32), server_default="discord", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_vote_id", "audit_logs", ["vote_id"])
    op.create_index("ix_audit_logs_guild_id", "audit_logs", ["guild_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("vote_mandatory_members")
    op.drop_table("vote_participants")
    op.drop_table("vote_options")
    op.drop_table("votes")
    op.drop_table("council_members")
    op.drop_table("guild_settings")
