from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models import (
    AuditAction,
    CouncilMember,
    GuildSettings,
    Vote,
    VoteMandatoryMember,
    VoteOption,
    VoteParticipant,
    VoteStatus,
)


async def get_or_create_guild_settings(session: AsyncSession, guild_id: int) -> GuildSettings:
    result = await session.execute(
        select(GuildSettings).where(GuildSettings.guild_id == guild_id)
    )
    settings_obj = result.scalar_one_or_none()
    if settings_obj is None:
        settings_obj = GuildSettings(guild_id=guild_id)
        session.add(settings_obj)
        await session.flush()
    return settings_obj


async def get_active_votes(session: AsyncSession, guild_id: int) -> list[Vote]:
    result = await session.execute(
        select(Vote)
        .where(Vote.guild_id == guild_id, Vote.status == VoteStatus.OPEN)
        .options(selectinload(Vote.options), selectinload(Vote.participants))
        .order_by(Vote.created_at.desc())
    )
    return list(result.scalars().all())


async def get_scheduled_votes(session: AsyncSession, guild_id: int) -> list[Vote]:
    result = await session.execute(
        select(Vote)
        .where(Vote.guild_id == guild_id, Vote.status == VoteStatus.SCHEDULED)
        .order_by(Vote.starts_at)
    )
    return list(result.scalars().all())


async def get_recent_completed(session: AsyncSession, guild_id: int, limit: int = 10) -> list[Vote]:
    result = await session.execute(
        select(Vote)
        .where(Vote.guild_id == guild_id, Vote.status == VoteStatus.COMPLETED)
        .order_by(Vote.actual_end_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_vote_by_id(
    session: AsyncSession, vote_id: int, guild_id: int | None = None
) -> Vote | None:
    stmt = select(Vote).where(Vote.id == vote_id)
    if guild_id is not None:
        stmt = stmt.where(Vote.guild_id == guild_id)
    result = await session.execute(
        stmt.options(
            selectinload(Vote.options),
            selectinload(Vote.participants),
            selectinload(Vote.mandatory_list),
            selectinload(Vote.audit_logs),
        )
    )
    return result.scalar_one_or_none()


async def get_vote_by_message(session: AsyncSession, message_id: int) -> Vote | None:
    result = await session.execute(
        select(Vote)
        .where(Vote.message_id == message_id)
        .options(
            selectinload(Vote.options),
            selectinload(Vote.participants),
        )
    )
    return result.scalar_one_or_none()


async def get_vote_message_targets(
    session: AsyncSession, vote: Vote
) -> list[tuple[int, int]]:
    """Return (channel_id, message_id) pairs for every published copy of a vote."""
    from bot.models.models import VoteMessage

    pairs = set()
    if vote.message_id and vote.channel_id:
        pairs.add((vote.channel_id, vote.message_id))

    result = await session.execute(
        select(VoteMessage).where(VoteMessage.vote_id == vote.id)
    )
    for copy in result.scalars().all():
        if copy.channel_id and copy.message_id:
            pairs.add((copy.channel_id, copy.message_id))

    return list(pairs)


async def get_next_vote_number(session: AsyncSession, guild_id: int) -> int:
    settings_obj = await get_or_create_guild_settings(session, guild_id)
    num = settings_obj.next_vote_number
    settings_obj.next_vote_number = num + 1
    return num


async def create_vote(
    session: AsyncSession,
    *,
    guild_id: int,
    title: str,
    creator_id: int,
    creator_name: str,
    description: str | None = None,
    reason: str | None = None,
    additional_info: str | None = None,
    category: str | None = None,
    vote_type: str = "standard",
    anonymity_level: str = "open",
    change_mode: str = "none",
    is_mandatory: bool = False,
    quorum_rule: str = "min_percent",
    quorum_value: float | None = None,
    majority_rule: str = "simple",
    tie_rule: str = "not_accepted",
    custom_options: list[str] | None = None,
    starts_at: dt.datetime | None = None,
    ends_at: dt.datetime | None = None,
    allow_early_end: bool = True,
    confirmation_required: bool = False,
    channel_id: int | None = None,
    related_vote_id: int | None = None,
) -> Vote:
    vote_number = await get_next_vote_number(session, guild_id)

    vote = Vote(
        vote_number=vote_number,
        guild_id=guild_id,
        channel_id=channel_id,
        title=title,
        description=description,
        reason=reason,
        additional_info=additional_info,
        category=category,
        creator_id=creator_id,
        creator_name=creator_name,
        vote_type=vote_type,
        anonymity_level=anonymity_level,
        change_mode=change_mode,
        is_mandatory=is_mandatory,
        quorum_rule=quorum_rule,
        quorum_value=quorum_value,
        majority_rule=majority_rule,
        tie_rule=tie_rule,
        allow_early_end=allow_early_end,
        confirmation_required=confirmation_required,
        custom_options=custom_options,
        starts_at=starts_at,
        ends_at=ends_at,
        related_vote_id=related_vote_id,
        status=VoteStatus.DRAFT if starts_at and starts_at > dt.datetime.utcnow() else VoteStatus.DRAFT,
    )
    session.add(vote)
    await session.flush()

    default_options = _get_default_options(vote_type)
    for i, label in enumerate(default_options):
        opt = VoteOption(vote_id=vote.id, label=label, position=i)
        session.add(opt)

    if custom_options:
        for i, label in enumerate(custom_options):
            opt = VoteOption(vote_id=vote.id, label=label, position=len(default_options) + i)
            session.add(opt)

    await session.flush()
    return vote


def _get_default_options(vote_type: str) -> list[str]:
    if vote_type == "standard":
        return ["ЗА", "ПРОТИВ", "ВОЗДЕРЖАЛСЯ"]
    elif vote_type == "no_abstain":
        return ["ЗА", "ПРОТИВ"]
    return []


async def open_vote(session: AsyncSession, vote: Vote) -> Vote:
    vote.status = VoteStatus.OPEN
    if not vote.starts_at:
        vote.starts_at = dt.datetime.utcnow()
    if not vote.actual_end_at:
        vote.actual_end_at = None

    if vote.guild_id:
        settings_obj = await get_or_create_guild_settings(session, vote.guild_id)
        vote.guild_settings_id = settings_obj.id

    await session.flush()
    return vote


async def complete_vote(session: AsyncSession, vote: Vote, reason: str | None = None) -> Vote:
    vote.status = VoteStatus.COMPLETED
    vote.actual_end_at = dt.datetime.utcnow()
    vote.completion_reason = reason or "Срок голосования истёк"
    await session.flush()
    return vote


async def cancel_vote(session: AsyncSession, vote: Vote, reason: str) -> Vote:
    vote.status = VoteStatus.CANCELLED
    vote.cancel_reason = reason
    vote.actual_end_at = dt.datetime.utcnow()
    await session.flush()
    return vote


async def pause_vote(session: AsyncSession, vote: Vote) -> Vote:
    vote.status = VoteStatus.PAUSED
    vote.paused_at = dt.datetime.utcnow()
    await session.flush()
    return vote


async def resume_vote(session: AsyncSession, vote: Vote) -> Vote:
    if vote.paused_at:
        paused_duration = dt.datetime.utcnow() - vote.paused_at
        vote.total_paused_seconds += int(paused_duration.total_seconds())
        vote.paused_at = None
    vote.status = VoteStatus.OPEN
    await session.flush()
    return vote


async def extend_vote(session: AsyncSession, vote: Vote, new_end: dt.datetime) -> Vote:
    vote.ends_at = new_end
    await session.flush()
    return vote


async def cast_vote(
    session: AsyncSession,
    vote: Vote,
    user_id: int,
    option_id: int,
    user_name: str | None = None,
    weight: float = 1.0,
) -> VoteParticipant:
    existing = await session.execute(
        select(VoteParticipant).where(
            VoteParticipant.vote_id == vote.id,
            VoteParticipant.user_id == user_id,
        )
    )
    participant = existing.scalar_one_or_none()

    is_new_vote = participant is None or not participant.has_voted

    if participant is None:
        participant = VoteParticipant(
            vote_id=vote.id,
            user_id=user_id,
            user_name=user_name,
            option_id=option_id,
            has_voted=True,
            voted_at=dt.datetime.utcnow(),
            weight=weight,
        )
        session.add(participant)
    else:
        participant.option_id = option_id
        participant.has_voted = True
        participant.voted_at = dt.datetime.utcnow()
        participant.weight = weight
        participant.change_count += 1

    await session.flush()

    if is_new_vote and vote.guild_id:
        try:
            await update_user_stats(
                session,
                guild_id=vote.guild_id,
                user_id=user_id,
                is_mandatory=vote.is_mandatory,
                is_new_vote=True,
            )
        except Exception:
            pass

    return participant


async def revoke_vote(session: AsyncSession, vote: Vote, user_id: int) -> VoteParticipant | None:
    result = await session.execute(
        select(VoteParticipant).where(
            VoteParticipant.vote_id == vote.id,
            VoteParticipant.user_id == user_id,
        )
    )
    participant = result.scalar_one_or_none()
    if participant:
        participant.option_id = None
        participant.has_voted = False
        participant.voted_at = None
        await session.flush()
    return participant


async def calculate_results(session: AsyncSession, vote: Vote) -> dict:
    options_result = await session.execute(
        select(VoteOption).where(VoteOption.vote_id == vote.id).order_by(VoteOption.position)
    )
    options = list(options_result.scalars().all())

    votes_result = await session.execute(
        select(VoteParticipant).where(
            VoteParticipant.vote_id == vote.id,
            VoteParticipant.has_voted == True,
        )
    )
    participants = list(votes_result.scalars().all())

    total_voted = len(participants)

    total_eligible = 0
    if vote.is_mandatory:
        mandatory_result = await session.execute(
            select(func.count(VoteMandatoryMember.id)).where(
                VoteMandatoryMember.vote_id == vote.id,
                VoteMandatoryMember.is_exempt == False,
            )
        )
        total_eligible = mandatory_result.scalar() or 0
    else:
        member_result = await session.execute(
            select(func.count(CouncilMember.id)).where(
                CouncilMember.guild_id == vote.guild_id,
                CouncilMember.is_active == True,
            )
        )
        total_eligible = member_result.scalar() or 0

    if total_eligible == 0:
        total_eligible = total_voted

    turnout = (total_voted / total_eligible * 100) if total_eligible > 0 else 0

    option_results = []
    for opt in options:
        count = sum(
            p.weight for p in participants if p.option_id == opt.id
        )
        option_results.append({
            "option_id": opt.id,
            "label": opt.label,
            "emoji": opt.emoji,
            "count": count,
            "percentage": (count / total_voted * 100) if total_voted > 0 else 0,
        })

    quorum_reached = _check_quorum(vote, total_voted, total_eligible)
    winner = _determine_winner(vote, option_results, total_voted, total_eligible)

    abstain_count = 0
    for opt in options:
        if opt.label.upper() in ("ВОЗДЕРЖАЛСЯ", "ВОЗДЕРЖАТЬСЯ"):
            abstain_count = next((r["count"] for r in option_results if r["option_id"] == opt.id), 0)
            break

    result_data = {
        "options": option_results,
        "total_voted": total_voted,
        "total_eligible": total_eligible,
        "turnout_percent": round(turnout, 1),
        "quorum_reached": quorum_reached,
        "winner": winner,
        "abstain_count": abstain_count,
        "calculated_at": dt.datetime.utcnow().isoformat(),
    }

    vote.result_data = result_data
    vote.quorum_reached = quorum_reached
    vote.final_decision = winner
    await session.flush()

    return result_data


def _check_quorum(vote: Vote, total_voted: int, total_eligible: int) -> bool:
    if vote.quorum_rule == "min_count":
        return total_voted >= (vote.quorum_value or 0)
    elif vote.quorum_rule == "min_percent":
        if total_eligible == 0:
            return False
        return (total_voted / total_eligible * 100) >= (vote.quorum_value or 0)
    return True


def _determine_winner(vote: Vote, option_results: list[dict], total_voted: int, total_eligible: int) -> str:
    if not option_results:
        return "no_result"

    sorted_options = sorted(option_results, key=lambda x: x["count"], reverse=True)

    if vote.majority_rule == "unanimous":
        if len(sorted_options) > 0 and sorted_options[0]["count"] == total_voted:
            return sorted_options[0]["label"]
        return "not_accepted"

    if vote.majority_rule == "all_participants":
        threshold = total_eligible / 2
    else:
        denominator = total_voted
        if not vote.abstain_counted_in_majority:
            abstain = next((r["count"] for r in option_results if r["label"].upper() in ("ВОЗДЕРЖАЛСЯ", "ВОЗДЕРЖАТЬСЯ")), 0)
            denominator = total_voted - abstain
        threshold = denominator / 2

    if sorted_options[0]["count"] > threshold:
        return sorted_options[0]["label"]

    if len(sorted_options) > 1 and sorted_options[0]["count"] == sorted_options[1]["count"]:
        return _handle_tie(vote)

    return "not_accepted"


def _handle_tie(vote: Vote) -> str:
    if vote.tie_rule == "not_accepted":
        return "not_accepted"
    elif vote.tie_rule == "extend":
        return "tie_extend"
    elif vote.tie_rule == "re_vote":
        return "tie_re_vote"
    elif vote.tie_rule == "chair_vote":
        return "pending_chair"
    return "not_accepted"


async def check_user_can_vote(session: AsyncSession, vote: Vote, user_id: int) -> tuple[bool, str]:
    if vote.status != VoteStatus.OPEN:
        return False, "Голосование не активно"

    if vote.ends_at and dt.datetime.utcnow() > vote.ends_at:
        return False, "Срок голосования истёк"

    member_result = await session.execute(
        select(CouncilMember).where(
            CouncilMember.guild_id == vote.guild_id,
            CouncilMember.user_id == user_id,
            CouncilMember.is_active == True,
        )
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        return False, "У вас нет права голоса"

    existing = await session.execute(
        select(VoteParticipant).where(
            VoteParticipant.vote_id == vote.id,
            VoteParticipant.user_id == user_id,
        )
    )
    participant = existing.scalar_one_or_none()

    if participant and participant.has_voted and vote.change_mode == "none":
        return False, "Вы уже проголосовали. Изменение голоса запрещено"

    return True, "OK"


async def get_vote_participants_info(session: AsyncSession, vote: Vote) -> dict:
    mandatory_result = await session.execute(
        select(VoteMandatoryMember).where(VoteMandatoryMember.vote_id == vote.id)
    )
    mandatory = list(mandatory_result.scalars().all())

    all_result = await session.execute(
        select(CouncilMember).where(
            CouncilMember.guild_id == vote.guild_id,
            CouncilMember.is_active == True,
        )
    )
    all_members = list(all_result.scalars().all())

    voted_result = await session.execute(
        select(VoteParticipant).where(
            VoteParticipant.vote_id == vote.id,
            VoteParticipant.has_voted == True,
        )
    )
    voted = list(voted_result.scalars().all())

    return {
        "mandatory": mandatory,
        "all_members": all_members,
        "voted": voted,
        "total_eligible": len(all_members),
        "total_voted": len(voted),
    }


async def sync_council_members(session: AsyncSession, guild_id: int, members: list[dict]) -> None:
    await session.execute(
        update(CouncilMember)
        .where(CouncilMember.guild_id == guild_id)
        .values(is_active=False)
    )

    for m in members:
        result = await session.execute(
            select(CouncilMember).where(
                CouncilMember.guild_id == guild_id,
                CouncilMember.user_id == m["user_id"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.is_active = True
            existing.display_name = m.get("display_name")
            existing.role_id = m.get("role_id")
            existing.weight = m.get("weight", 1.0)
            existing.council_number = m.get("council_number")
            existing.sphere = m.get("sphere")
            existing.veto_level = m.get("veto_level")
        else:
            member = CouncilMember(
                guild_id=guild_id,
                user_id=m["user_id"],
                display_name=m.get("display_name"),
                role_id=m.get("role_id"),
                weight=m.get("weight", 1.0),
                council_number=m.get("council_number"),
                sphere=m.get("sphere"),
                veto_level=m.get("veto_level"),
                is_active=True,
            )
            session.add(member)

    await session.flush()


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


async def add_comment(
    session: AsyncSession,
    vote_id: int,
    user_id: int,
    content: str,
    user_name: str | None = None,
) -> "VoteComment":
    from bot.models.models import VoteComment

    comment = VoteComment(
        vote_id=vote_id,
        user_id=user_id,
        user_name=user_name,
        content=content,
    )
    session.add(comment)
    await session.flush()
    return comment


async def get_comments(session: AsyncSession, vote_id: int) -> list:
    from bot.models.models import VoteComment

    result = await session.execute(
        select(VoteComment)
        .where(VoteComment.vote_id == vote_id, VoteComment.is_deleted == False)
        .order_by(VoteComment.created_at)
    )
    return list(result.scalars().all())


async def delete_comment(session: AsyncSession, comment_id: int, user_id: int) -> bool:
    from bot.models.models import VoteComment

    result = await session.execute(
        select(VoteComment).where(VoteComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        return False
    if comment.user_id != user_id:
        return False
    comment.is_deleted = True
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


async def create_template(
    session: AsyncSession,
    *,
    guild_id: int,
    name: str,
    created_by: int,
    description: str | None = None,
    vote_type: str = "standard",
    anonymity_level: str = "open",
    change_mode: str = "none",
    is_mandatory: bool = False,
    quorum_rule: str = "min_percent",
    quorum_value: float | None = None,
    majority_rule: str = "simple",
    tie_rule: str = "not_accepted",
    default_duration_hours: int = 48,
    custom_options: list[str] | None = None,
    default_title: str | None = None,
    default_description: str | None = None,
    default_reason: str | None = None,
) -> "VoteTemplate":
    from bot.models.models import VoteTemplate

    tmpl = VoteTemplate(
        guild_id=guild_id,
        name=name,
        description=description,
        created_by=created_by,
        vote_type=vote_type,
        anonymity_level=anonymity_level,
        change_mode=change_mode,
        is_mandatory=is_mandatory,
        quorum_rule=quorum_rule,
        quorum_value=quorum_value,
        majority_rule=majority_rule,
        tie_rule=tie_rule,
        default_duration_hours=default_duration_hours,
        custom_options=custom_options,
        default_title=default_title,
        default_description=default_description,
        default_reason=default_reason,
    )
    session.add(tmpl)
    await session.flush()
    return tmpl


async def get_templates(session: AsyncSession, guild_id: int) -> list:
    from bot.models.models import VoteTemplate

    result = await session.execute(
        select(VoteTemplate)
        .where(VoteTemplate.guild_id == guild_id)
        .order_by(VoteTemplate.use_count.desc())
    )
    return list(result.scalars().all())


async def get_template_by_id(
    session: AsyncSession, template_id: int, guild_id: int | None = None
):
    from bot.models.models import VoteTemplate

    stmt = select(VoteTemplate).where(VoteTemplate.id == template_id)
    if guild_id is not None:
        stmt = stmt.where(VoteTemplate.guild_id == guild_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_template(
    session: AsyncSession, template_id: int, guild_id: int | None = None
) -> bool:
    from bot.models.models import VoteTemplate

    stmt = select(VoteTemplate).where(VoteTemplate.id == template_id)
    if guild_id is not None:
        stmt = stmt.where(VoteTemplate.guild_id == guild_id)
    result = await session.execute(stmt)
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        return False
    await session.delete(tmpl)
    await session.flush()
    return True


async def increment_template_use(session: AsyncSession, template_id: int) -> None:
    from bot.models.models import VoteTemplate

    result = await session.execute(
        select(VoteTemplate).where(VoteTemplate.id == template_id)
    )
    tmpl = result.scalar_one_or_none()
    if tmpl:
        tmpl.use_count += 1
        await session.flush()


# ---------------------------------------------------------------------------
# Clone vote
# ---------------------------------------------------------------------------


async def clone_vote(
    session: AsyncSession,
    vote_id: int,
    creator_id: int,
    creator_name: str,
    guild_id: int | None = None,
) -> "Vote":
    source = await get_vote_by_id(session, vote_id, guild_id)
    if not source:
        raise ValueError("Голосование не найдено")

    vote_number = await get_next_vote_number(session, source.guild_id)

    new_vote = Vote(
        vote_number=vote_number,
        guild_id=source.guild_id,
        channel_id=source.channel_id,
        title=f"[Копия] {source.title}",
        short_title=source.short_title,
        description=source.description,
        reason=source.reason,
        additional_info=source.additional_info,
        category=source.category,
        priority=source.priority,
        creator_id=creator_id,
        creator_name=creator_name,
        vote_type=source.vote_type,
        anonymity_level=source.anonymity_level,
        change_mode=source.change_mode,
        confirmation_required=source.confirmation_required,
        is_mandatory=source.is_mandatory,
        quorum_rule=source.quorum_rule,
        quorum_value=source.quorum_value,
        quorum_on_fail=source.quorum_on_fail,
        majority_rule=source.majority_rule,
        tie_rule=source.tie_rule,
        abstain_counted_in_majority=source.abstain_counted_in_majority,
        allow_early_end=source.allow_early_end,
        custom_options=source.custom_options,
        related_vote_id=source.id,
        status=VoteStatus.DRAFT,
    )
    session.add(new_vote)
    await session.flush()

    for opt in (source.options or []):
        new_opt = VoteOption(
            vote_id=new_vote.id,
            label=opt.label,
            emoji=opt.emoji,
            position=opt.position,
            description=opt.description,
            color=opt.color,
        )
        session.add(new_opt)

    await session.flush()
    return new_vote


# ---------------------------------------------------------------------------
# Veto
# ---------------------------------------------------------------------------


async def cast_veto(
    session: AsyncSession,
    vote_id: int,
    user_id: int,
    reason: str,
    user_name: str | None = None,
    veto_level: int = 3,
    veto_direction: str = "reject",
) -> "VoteVeto":
    from bot.models.models import VoteVeto

    existing_result = await session.execute(
        select(VoteVeto).where(
            VoteVeto.vote_id == vote_id,
            VoteVeto.status == "active",
        )
    )
    existing = list(existing_result.scalars().all())

    for ev in existing:
        if ev.user_id == user_id:
            ev.status = "superseded"
        elif ev.veto_direction == veto_direction and ev.veto_level >= veto_level:
            ev.status = "overruled"

    veto = VoteVeto(
        vote_id=vote_id,
        user_id=user_id,
        user_name=user_name,
        reason=reason,
        status="active",
        veto_level=veto_level,
        veto_direction=veto_direction,
    )
    session.add(veto)
    await session.flush()
    return veto


async def resolve_veto(
    session: AsyncSession,
    veto_id: int,
    resolved_by: int,
    resolution: str,
    comment: str | None = None,
) -> bool:
    from bot.models.models import VoteVeto

    result = await session.execute(
        select(VoteVeto).where(VoteVeto.id == veto_id, VoteVeto.status == "active")
    )
    veto = result.scalar_one_or_none()
    if not veto:
        return False
    veto.status = resolution
    veto.resolved_by = resolved_by
    veto.resolved_at = dt.datetime.utcnow()
    veto.resolution_comment = comment
    await session.flush()
    return True


async def get_vetoes(
    session: AsyncSession, vote_id: int, guild_id: int | None = None
) -> list:
    from bot.models.models import Vote as VoteModel
    from bot.models.models import VoteVeto

    stmt = (
        select(VoteVeto)
        .join(VoteModel, VoteModel.id == VoteVeto.vote_id)
        .where(VoteVeto.vote_id == vote_id)
        .order_by(VoteVeto.created_at.desc())
    )
    if guild_id is not None:
        stmt = stmt.where(VoteModel.guild_id == guild_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Multi-round
# ---------------------------------------------------------------------------


async def create_round(
    session: AsyncSession,
    vote_id: int,
    round_number: int,
    description: str | None = None,
) -> "VoteRound":
    from bot.models.models import VoteRound

    rnd = VoteRound(
        vote_id=vote_id,
        round_number=round_number,
        description=description,
        status="pending",
    )
    session.add(rnd)
    await session.flush()
    return rnd


async def start_round(session: AsyncSession, round_id: int) -> bool:
    from bot.models.models import VoteRound

    result = await session.execute(
        select(VoteRound).where(VoteRound.id == round_id)
    )
    rnd = result.scalar_one_or_none()
    if not rnd:
        return False
    rnd.status = "active"
    rnd.started_at = dt.datetime.utcnow()
    await session.flush()
    return True


async def complete_round(
    session: AsyncSession,
    round_id: int,
    result_data: dict,
    eliminated: list[str] | None = None,
) -> bool:
    from bot.models.models import VoteRound

    result = await session.execute(
        select(VoteRound).where(VoteRound.id == round_id)
    )
    rnd = result.scalar_one_or_none()
    if not rnd:
        return False
    rnd.status = "completed"
    rnd.ended_at = dt.datetime.utcnow()
    rnd.result_data = result_data
    rnd.eliminated_options = eliminated
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# User stats
# ---------------------------------------------------------------------------


async def update_user_stats(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    is_mandatory: bool = False,
    is_new_vote: bool = True,
) -> "UserVoteStats":
    from bot.models.models import UserVoteStats

    result = await session.execute(
        select(UserVoteStats).where(
            UserVoteStats.guild_id == guild_id,
            UserVoteStats.user_id == user_id,
        )
    )
    stats = result.scalar_one_or_none()

    if not stats:
        stats = UserVoteStats(
            guild_id=guild_id,
            user_id=user_id,
        )
        session.add(stats)

    if is_new_vote:
        stats.total_votes_cast += 1
        stats.last_vote_at = dt.datetime.utcnow()

        if is_mandatory:
            stats.total_mandatory += 1
            stats.mandatory_attended += 1
            stats.streak += 1
            if stats.streak > stats.max_streak:
                stats.max_streak = stats.streak
        else:
            stats.streak += 1
            if stats.streak > stats.max_streak:
                stats.max_streak = stats.streak

    await session.flush()
    return stats


async def get_user_stats(session: AsyncSession, guild_id: int, user_id: int):
    from bot.models.models import UserVoteStats

    result = await session.execute(
        select(UserVoteStats).where(
            UserVoteStats.guild_id == guild_id,
            UserVoteStats.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_leaderboard(session: AsyncSession, guild_id: int, limit: int = 10) -> list:
    from bot.models.models import UserVoteStats

    result = await session.execute(
        select(UserVoteStats)
        .where(UserVoteStats.guild_id == guild_id)
        .order_by(UserVoteStats.total_votes_cast.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def search_votes(
    session: AsyncSession,
    guild_id: int,
    query: str | None = None,
    category: str | None = None,
    creator_id: int | None = None,
    status: str | None = None,
    limit: int = 25,
) -> list[Vote]:
    q = select(Vote).where(Vote.guild_id == guild_id)

    if query:
        q = q.where(
            Vote.title.ilike(f"%{query}%")
            | Vote.description.ilike(f"%{query}%")
            | Vote.reason.ilike(f"%{query}%")
        )
    if category:
        q = q.where(Vote.category == category)
    if creator_id:
        q = q.where(Vote.creator_id == creator_id)
    if status:
        q = q.where(Vote.status == status)

    q = q.options(
        selectinload(Vote.options),
        selectinload(Vote.participants),
    ).order_by(Vote.created_at.desc()).limit(limit)

    result = await session.execute(q)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


async def create_bundle(
    session: AsyncSession,
    *,
    guild_id: int,
    name: str,
    created_by: int,
    description: str | None = None,
) -> "VoteBundle":
    from bot.models.models import VoteBundle

    bundle = VoteBundle(
        guild_id=guild_id,
        name=name,
        description=description,
        created_by=created_by,
        vote_ids=[],
    )
    session.add(bundle)
    await session.flush()
    return bundle


async def add_vote_to_bundle(
    session: AsyncSession,
    bundle_id: int,
    vote_id: int,
) -> bool:
    from bot.models.models import VoteBundle

    result = await session.execute(
        select(VoteBundle).where(VoteBundle.id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        return False
    ids = bundle.vote_ids or []
    if vote_id not in ids:
        ids.append(vote_id)
        bundle.vote_ids = ids
    await session.flush()
    return True


async def get_bundle(session: AsyncSession, bundle_id: int):
    from bot.models.models import VoteBundle

    result = await session.execute(
        select(VoteBundle).where(VoteBundle.id == bundle_id)
    )
    return result.scalar_one_or_none()


async def publish_bundle(session: AsyncSession, bundle_id: int) -> bool:
    from bot.models.models import VoteBundle

    result = await session.execute(
        select(VoteBundle).where(VoteBundle.id == bundle_id)
    )
    bundle = result.scalar_one_or_none()
    if not bundle:
        return False
    bundle.status = "published"
    bundle.published_at = dt.datetime.utcnow()
    await session.flush()
    return True
