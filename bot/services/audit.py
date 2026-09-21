from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import discord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import AuditAction, AuditLog, Vote
from bot.models.models import GuildSettings

logger = logging.getLogger(__name__)

_client: discord.Client | None = None

_ACTION_META = {
    "vote_created": ("\U0001f5f3\ufe0f Голосование создано", 0x57F287),
    "vote_cast": ("\U0001f5f3\ufe0f Голос отдан", 0x5865F2),
    "cancelled": ("\U0001f6ab Голосование отменено", 0xED4245),
    "early_completion": ("\u23f9\ufe0f Голосование завершено досрочно", 0xFEE75C),
    "auto_completed": ("\u23f0 Голосование завершено по сроку", 0xFEE75C),
    "extended": ("\u23f3 Голосование продлено", 0x5865F2),
    "paused": ("\u23f8\ufe0f Голосование приостановлено", 0xFEE75C),
    "resumed": ("\u25b6\ufe0f Голосование возобновлено", 0x57F287),
    "veto_cast": ("\U0001f6d1 Наложено вето", 0xED4245),
    "reminder_sent": ("\U0001f514 Отправлено напоминание", 0x5865F2),
    "draft_edited": ("\u270f\ufe0f Черновик изменён", 0x5865F2),
    "settings_changed": ("\u2699\ufe0f Настройки изменены", 0x5865F2),
    "approved": ("\u2705 Голосование одобрено", 0x57F287),
    "rejected": ("\u274c Голосование отклонено", 0xED4245),
}


def set_client(client: discord.Client) -> None:
    global _client
    _client = client


def _format_details(details: dict[str, Any] | None) -> str:
    if not details:
        return ""
    parts = []
    reason = None
    for key, value in details.items():
        if key == "reason":
            reason = value
            continue
        parts.append(f"{key}: {value}")
    text = "; ".join(str(p) for p in parts)
    if reason:
        text = f"{text}; причина: {reason}" if text else f"Причина: {reason}"
    return text


async def _send_log_message(session: AsyncSession, entry: AuditLog) -> None:
    if _client is None:
        return
    try:
        result = await session.execute(
            select(GuildSettings).where(GuildSettings.guild_id == entry.guild_id)
        )
        gs = result.scalar_one_or_none()
        if not gs or not gs.log_channel_id:
            return
        channel = _client.get_channel(gs.log_channel_id)
        if channel is None:
            return

        meta = _ACTION_META.get(entry.action, (f"\u2139\ufe0f {entry.action}", 0x5865F2))
        title, color = meta

        anonymize = False
        if entry.vote_id:
            vote = await session.get(Vote, entry.vote_id)
            anonymize = bool(vote and vote.anonymity_level == "full")

        embed = discord.Embed(title=title, color=color)
        desc_parts = []
        if not anonymize:
            if entry.user_name:
                desc_parts.append(f"Пользователь: **{entry.user_name}**")
            details_text = _format_details(entry.details)
            if details_text:
                desc_parts.append(details_text)
        if entry.vote_id:
            desc_parts.append(f"Голосование ID: `{entry.vote_id}`")
        embed.description = "\n".join(desc_parts) or "—"
        embed.timestamp = dt.datetime.utcnow()

        await channel.send(embed=embed)
    except Exception as e:
        logger.warning("Не удалось отправить в канал логов: %s", e)


async def log_action(
    session: AsyncSession,
    *,
    action,
    guild_id: int,
    vote_id: int | None = None,
    user_id: int,
    user_name: str | None = None,
    details: dict[str, Any] | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    ip_address: str | None = None,
    source: str = "discord",
) -> AuditLog:
    action_str = action.value if hasattr(action, "value") else str(action)
    entry = AuditLog(
        vote_id=vote_id,
        guild_id=guild_id,
        action=action_str,
        user_id=user_id,
        user_name=user_name,
        details=details,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        source=source,
    )
    session.add(entry)
    await session.flush()
    await _send_log_message(session, entry)
    return entry


async def get_vote_logs(
    session: AsyncSession,
    vote_id: int,
    limit: int = 100,
) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.vote_id == vote_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_guild_logs(
    session: AsyncSession,
    guild_id: int,
    limit: int = 100,
    action_filter: str | None = None,
) -> list[AuditLog]:
    query = select(AuditLog).where(AuditLog.guild_id == guild_id)
    if action_filter:
        query = query.where(AuditLog.action == action_filter)
    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())