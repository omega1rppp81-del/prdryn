from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Guild settings
# ---------------------------------------------------------------------------


class GuildSettings(Base, TimestampMixin):
    __tablename__ = "guild_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)

    vote_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    extra_vote_channel_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    log_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    admin_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    council_role_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    admin_role_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    auditor_role_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    chair_role_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    numbering_format: Mapped[str] = mapped_column(String(32), default="sequential")
    embed_color: Mapped[int] = mapped_column(Integer, default=0x5865F2)
    message_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    default_duration_hours: Mapped[int] = mapped_column(Integer, default=48)
    default_vote_type: Mapped[str] = mapped_column(String(32), default="standard")
    default_anonymity: Mapped[str] = mapped_column(String(32), default="open")
    default_quorum_rule: Mapped[str] = mapped_column(String(32), default="min_percent")
    default_change_mode: Mapped[str] = mapped_column(String(32), default="none")

    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_hours_before: Mapped[int] = mapped_column(Integer, default=4)
    reminder_interval_hours: Mapped[int] = mapped_column(Integer, default=6)

    isolation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    data_retention_days: Mapped[int] = mapped_column(Integer, default=365)
    auto_archive_days: Mapped[int] = mapped_column(Integer, default=30)

    next_vote_number: Mapped[int] = mapped_column(Integer, default=1)

    votes: Mapped[list["Vote"]] = relationship(back_populates="guild_settings")


# ---------------------------------------------------------------------------
# Council member snapshot
# ---------------------------------------------------------------------------


class CouncilMember(Base, TimestampMixin):
    __tablename__ = "council_members"
    __table_args__ = (
        UniqueConstraint("guild_id", "user_id", name="uq_council_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    council_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    veto_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    participations: Mapped[list["VoteParticipant"]] = relationship(
        back_populates="member",
    )


# ---------------------------------------------------------------------------
# Vote
# ---------------------------------------------------------------------------


class Vote(Base, TimestampMixin):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_number: Mapped[int] = mapped_column(Integer, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)

    title: Mapped[str] = mapped_column(String(256), nullable=False)
    short_title: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    additional_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    linked_documents: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    discussion_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    vote_type: Mapped[str] = mapped_column(String(32), default="standard")
    anonymity_level: Mapped[str] = mapped_column(String(32), default="open")
    change_mode: Mapped[str] = mapped_column(String(32), default="none")
    confirmation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_after_join: Mapped[bool] = mapped_column(Boolean, default=False)
    leave_rule: Mapped[str] = mapped_column(String(32), default="keep_vote")

    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    mandatory_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mandatory_role_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mandatory_user_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    mandatory_snapshot_at: Mapped[str] = mapped_column(String(32), default="start")

    quorum_rule: Mapped[str] = mapped_column(String(32), default="min_percent")
    quorum_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quorum_required_role_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    quorum_on_fail: Mapped[str] = mapped_column(String(32), default="auto_reject")

    majority_rule: Mapped[str] = mapped_column(String(32), default="simple")
    tie_rule: Mapped[str] = mapped_column(String(32), default="not_accepted")
    abstain_counted_in_majority: Mapped[bool] = mapped_column(Boolean, default=False)
    min_affirmative_votes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)

    show_results_immediately: Mapped[bool] = mapped_column(Boolean, default=True)
    show_voter_list: Mapped[bool] = mapped_column(Boolean, default=True)
    show_percentages: Mapped[bool] = mapped_column(Boolean, default=True)
    min_votes_for_results: Mapped[int] = mapped_column(Integer, default=0)

    allow_early_end: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_extend_on_no_quorum: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_extend_hours: Mapped[int] = mapped_column(Integer, default=24)

    starts_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_paused_seconds: Mapped[int] = mapped_column(Integer, default=0)

    approval_status: Mapped[str] = mapped_column(String(32), default="none")
    approved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    approval_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    custom_options: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    max_multi_choices: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weights: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    memento: Mapped[bool] = mapped_column(Boolean, default=False)

    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    related_vote_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chain_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    result_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    quorum_reached: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    final_decision: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    guild_settings_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("guild_settings.id"),
        nullable=True,
    )
    guild_settings: Mapped[Optional["GuildSettings"]] = relationship(back_populates="votes")

    participants: Mapped[list["VoteParticipant"]] = relationship(
        back_populates="vote",
        cascade="all, delete-orphan",
    )
    options: Mapped[list["VoteOption"]] = relationship(
        back_populates="vote",
        cascade="all, delete-orphan",
        order_by="VoteOption.position",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="vote",
        cascade="all, delete-orphan",
    )
    mandatory_list: Mapped[list["VoteMandatoryMember"]] = relationship(
        back_populates="vote",
        cascade="all, delete-orphan",
    )
    message_copies: Mapped[list["VoteMessage"]] = relationship(
        back_populates="vote",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# Published vote message copies (multi-channel support)
# ---------------------------------------------------------------------------


class VoteMessage(Base, TimestampMixin):
    __tablename__ = "vote_messages"
    __table_args__ = (
        UniqueConstraint("message_id", name="uq_vote_message_copies"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[int] = mapped_column(
        ForeignKey("votes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)

    vote: Mapped["Vote"] = relationship(back_populates="message_copies")


# ---------------------------------------------------------------------------
# Vote option
# ---------------------------------------------------------------------------


class VoteOption(Base, TimestampMixin):
    __tablename__ = "vote_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[int] = mapped_column(ForeignKey("votes.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    vote: Mapped["Vote"] = relationship(back_populates="options")
    votes: Mapped[list["VoteParticipant"]] = relationship(back_populates="option")


# ---------------------------------------------------------------------------
# Vote participant (vote record)
# ---------------------------------------------------------------------------


class VoteParticipant(Base, TimestampMixin):
    __tablename__ = "vote_participants"
    __table_args__ = (
        UniqueConstraint("vote_id", "user_id", name="uq_vote_participant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[int] = mapped_column(ForeignKey("votes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    member_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("council_members.id"),
        nullable=True,
    )
    option_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vote_options.id"),
        nullable=True,
    )
    has_voted: Mapped[bool] = mapped_column(Boolean, default=False)
    voted_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    change_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    vote: Mapped["Vote"] = relationship(back_populates="participants")
    option: Mapped[Optional["VoteOption"]] = relationship(back_populates="votes")
    member: Mapped[Optional["CouncilMember"]] = relationship(back_populates="participations")


# ---------------------------------------------------------------------------
# Mandatory member snapshot
# ---------------------------------------------------------------------------


class VoteMandatoryMember(Base, TimestampMixin):
    __tablename__ = "vote_mandatory_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[int] = mapped_column(ForeignKey("votes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    has_voted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_exempt: Mapped[bool] = mapped_column(Boolean, default=False)
    exempt_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    vote: Mapped["Vote"] = relationship(back_populates="mandatory_list")


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("votes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="discord")

    vote: Mapped[Optional["Vote"]] = relationship(back_populates="audit_logs")


# ---------------------------------------------------------------------------
# Vote comment
# ---------------------------------------------------------------------------


class VoteComment(Base, TimestampMixin):
    __tablename__ = "vote_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[int] = mapped_column(ForeignKey("votes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    vote: Mapped["Vote"] = relationship()


# ---------------------------------------------------------------------------
# Vote template
# ---------------------------------------------------------------------------


class VoteTemplate(Base, TimestampMixin):
    __tablename__ = "vote_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)

    vote_type: Mapped[str] = mapped_column(String(32), default="standard")
    anonymity_level: Mapped[str] = mapped_column(String(32), default="open")
    change_mode: Mapped[str] = mapped_column(String(32), default="none")
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    quorum_rule: Mapped[str] = mapped_column(String(32), default="min_percent")
    quorum_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    majority_rule: Mapped[str] = mapped_column(String(32), default="simple")
    tie_rule: Mapped[str] = mapped_column(String(32), default="not_accepted")
    default_duration_hours: Mapped[int] = mapped_column(Integer, default=48)
    custom_options: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    default_title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    default_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Multi-round voting
# ---------------------------------------------------------------------------


class VoteRound(Base, TimestampMixin):
    __tablename__ = "vote_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[int] = mapped_column(ForeignKey("votes.id", ondelete="CASCADE"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    options_snapshot: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    result_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    eliminated_options: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    vote: Mapped["Vote"] = relationship()


# ---------------------------------------------------------------------------
# Veto
# ---------------------------------------------------------------------------


class VoteVeto(Base, TimestampMixin):
    __tablename__ = "vote_vetoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vote_id: Mapped[int] = mapped_column(ForeignKey("votes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    veto_level: Mapped[int] = mapped_column(Integer, default=3)
    veto_direction: Mapped[str] = mapped_column(String(16), default="reject")
    resolved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    vote: Mapped["Vote"] = relationship()


# ---------------------------------------------------------------------------
# Batch vote (package)
# ---------------------------------------------------------------------------


class VoteBundle(Base, TimestampMixin):
    __tablename__ = "vote_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    vote_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Vote statistics (cached)
# ---------------------------------------------------------------------------


class UserVoteStats(Base, TimestampMixin):
    __tablename__ = "user_vote_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    total_votes_cast: Mapped[int] = mapped_column(Integer, default=0)
    total_mandatory: Mapped[int] = mapped_column(Integer, default=0)
    mandatory_attended: Mapped[int] = mapped_column(Integer, default=0)
    votes_changed: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    max_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_vote_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("guild_id", "user_id", name="uq_user_vote_stats"),
    )
