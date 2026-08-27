from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import AuditAction, AuditLog


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
