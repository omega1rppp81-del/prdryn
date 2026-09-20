from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from bot.models import Vote

from sqlalchemy import func as sa_func

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATUS_SYMBOL = {
    "draft": "✎",
    "scheduled": "◷",
    "open": "◆",
    "paused": "┃",
    "completed": "◆",
    "cancelled": "✕",
    "archived": "▣",
}

_STATUS_TEXT = {
    "draft": "Черновик",
    "scheduled": "Запланировано",
    "open": "Открыто",
    "paused": "Приостановлено",
    "completed": "Завершено",
    "cancelled": "Отменено",
    "archived": "Архивировано",
}

_STATUS_COLOR = {
    "draft": 0x5865F2,
    "scheduled": 0x5865F2,
    "open": 0x2B2D31,
    "paused": 0xF0B232,
    "completed": 0x2B2D31,
    "cancelled": 0xED4245,
    "archived": 0x2B2D31,
}

_TYPE_TEXT = {
    "standard": "Стандартное",
    "no_abstain": "Без воздержания",
    "single_choice": "Выбор варианта",
    "multi_choice": "Множественный выбор",
    "ranked": "Рейтинговое",
    "weighted": "С весами",
}

_ANONYMITY_TEXT = {
    "open": "Открытое",
    "anonymous_members": "Анонимное для участников",
    "anonymous_admins": "Анонимное для администраторов",
    "partial": "Частично анонимное",
    "full": "Полностью анонимное",
}

_A = {
    "g": "\x1b[32m",
    "r": "\x1b[31m",
    "y": "\x1b[33m",
    "w": "\x1b[37m",
    "d": "\x1b[90m",
    "b": "\x1b[1m",
    "x": "\x1b[0m",
}

_VOTE_COLOR = {"ЗА": "g", "ПРОТИВ": "r", "ВОЗДЕРЖАЛСЯ": "y", "ВОЗДЕРЖАТЬСЯ": "y"}

_VOTE_SYM = {"ЗА": "◆", "ПРОТИВ": "◇", "ВОЗДЕРЖАЛСЯ": "○", "ВОЗДЕРЖАТЬСЯ": "○"}


def _bar(ratio: float, color_code: str, length: int = 10) -> str:
    filled = round(ratio * length)
    c = _A[color_code]
    return c + "█" * filled + "\x1b[90m" + "░" * (length - filled) + "\x1b[0m"


# ---------------------------------------------------------------------------
# Active vote embed
# ---------------------------------------------------------------------------


async def build_vote_embed(vote: "Vote", show_results: bool = True, session: "AsyncSession | None" = None) -> discord.Embed:
    color = _STATUS_COLOR.get(vote.status, 0x2B2D31)
    sym = _STATUS_SYMBOL.get(vote.status, "◆")
    stxt = _STATUS_TEXT.get(vote.status, vote.status)

    desc = []
    desc.append(f"{'━' * 48}")
    desc.append(f"  {sym}  ГОЛОСОВАНИЕ №{vote.vote_number}  ┃  {stxt}")
    desc.append(f"{'━' * 48}")
    desc.append("")
    desc.append(f"```text\n{vote.title}\n```")

    if vote.description:
        desc.append("")
        desc.append(f"```ansi\n\x1b[37m{vote.description.replace(chr(92)+'n', chr(10))[:500]}\x1b[0m\n```")
    if vote.reason:
        desc.append("")
        lines = vote.reason.replace("\\n", "\n")[:300].split("\n")
        quoted = "\n".join(f"\x1b[37m{line}\x1b[0m" for line in lines)
        desc.append(f"```ansi\n{quoted}\n```")
    if vote.additional_info:
        desc.append("")
        desc.append(f"```ansi\n\x1b[90m{vote.additional_info.replace(chr(92)+'n', chr(10))[:200]}\x1b[0m\n```")

    embed = discord.Embed(description="\n".join(desc), color=color)

    # ── Parameters ──
    abstain = "Разрешено" if vote.vote_type == "standard" else "Запрещено"
    change = "Разрешено" if vote.change_mode in ("change", "revoke") else "Запрещено"
    mandatory = "Да" if vote.is_mandatory else "Нет"

    params = (
        f"```\n"
        f"  Тип         {_TYPE_TEXT.get(vote.vote_type, vote.vote_type)}\n"
        f"  Режим       {_ANONYMITY_TEXT.get(vote.anonymity_level, vote.anonymity_level)}\n"
        f"  Изменение   {change}\n"
        f"  Обязат.     {mandatory}\n"
        f"  Воздержание {abstain}\n"
        f"```"
    )
    embed.add_field(name="── Параметры ──", value=params, inline=False)

    # ── Results (ANSI) ──
    if show_results and vote.result_data and "options" in vote.result_data:
        embed.add_field(
            name="── Результаты ──",
            value="```ansi\n" + _results_ansi(vote.result_data) + "\n```",
            inline=False,
        )
    elif vote.status == "open":
        voted_count = len([p for p in (vote.participants or []) if p.has_voted])
        total_eligible = 0
        if session is not None:
            from sqlalchemy import select as sa_select
            from bot.models import CouncilMember
            member_result = await session.execute(
                sa_select(sa_func.count(CouncilMember.id)).where(
                    CouncilMember.guild_id == vote.guild_id,
                    CouncilMember.is_active == True,
                )
            )
            total_eligible = member_result.scalar() or 0
        if total_eligible == 0:
            total_eligible = voted_count
        embed.add_field(
            name="── Проголосовало ──",
            value=f"```ansi\n  \x1b[32m{voted_count}\x1b[0m из {total_eligible} участников\n```",
            inline=False,
        )

    # ── Author + deadline (normal text, not ANSI) ──
    meta_parts = []
    if vote.ends_at:
        meta_parts.append(f"**Срок:** {discord.utils.format_dt(vote.ends_at, 'f')} ({discord.utils.format_dt(vote.ends_at, 'R')})")
    if vote.anonymity_level == "open":
        meta_parts.append(f"**Автор:** <@{vote.creator_id}>")
    else:
        meta_parts.append("**Автор:** Скрыт")

    if meta_parts:
        embed.add_field(name="\u200b", value="\n".join(meta_parts), inline=False)

    embed.set_footer(text=f"ID: {vote.id}")
    return embed


# ---------------------------------------------------------------------------
# Results ANSI block
# ---------------------------------------------------------------------------


def _results_ansi(data: dict, show_winner: bool = False) -> str:
    lines = []
    winner_label = data.get("winner") if show_winner else None

    for opt in data["options"]:
        label = opt["label"]
        pct = opt["percentage"]
        count = opt["count"]

        ck = _VOTE_COLOR.get(label, "d")
        c = _A[ck]
        bar = _bar(pct / 100, ck)

        marker = f"  \x1b[32m◆\x1b[0m" if label == winner_label else ""
        lines.append(
            f"\x1b[1m{label:<14}\x1b[0m "
            f"{bar}  {pct:>5.1f}%  {count}{marker}"
        )

    total_voted = data.get("total_voted", 0)
    total_eligible = data.get("total_eligible", 0)
    turnout = data.get("turnout_percent", 0)
    lines.append("")
    lines.append(
        f"\x1b[90mПроголосовало: {total_voted} из {total_eligible}"
        f"  │  Явка: {turnout:.1f}%\x1b[0m"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Completed vote embed
# ---------------------------------------------------------------------------


async def build_completed_embed(vote: "Vote", session: "AsyncSession | None" = None) -> discord.Embed:
    sym = _STATUS_SYMBOL.get("completed", "◆")

    desc = []
    desc.append(f"{'━' * 48}")
    desc.append(f"  {sym}  ГОЛОСОВАНИЕ №{vote.vote_number}  ┃  ЗАВЕРШЕНО")
    desc.append(f"{'━' * 48}")
    desc.append("")
    desc.append(f"```text\n{vote.title}\n```")

    if vote.completion_reason:
        desc.append(f"```ansi\n\x1b[37mПричина: {vote.completion_reason[:300]}\x1b[0m\n```")

    embed = discord.Embed(description="\n".join(desc), color=0x2B2D31)

    # ── Results (ANSI) ──
    if vote.result_data and "options" in vote.result_data:
        embed.add_field(
            name="── Результаты ──",
            value="```ansi\n" + _results_ansi(vote.result_data, show_winner=True) + "\n```",
            inline=False,
        )

    # ── Council table (ANSI) ──
    if session is not None:
        table = await _build_council_table(session, vote)
        if table:
            embed.add_field(
                name="── Совет ──",
                value="```ansi\n" + table + "\n```",
                inline=False,
            )

    # ── Author + timestamp (normal text) ──
    meta_parts = []
    if vote.anonymity_level == "open":
        meta_parts.append(f"**Автор:** <@{vote.creator_id}>")
    if vote.actual_end_at:
        meta_parts.append(f"**Завершено:** {discord.utils.format_dt(vote.actual_end_at, 'f')}")
    if meta_parts:
        embed.add_field(name="\u200b", value="\n".join(meta_parts), inline=False)

    embed.set_footer(text=f"ID: {vote.id}")
    return embed


# ---------------------------------------------------------------------------
# Council table
# ---------------------------------------------------------------------------


async def _build_council_table(session: "AsyncSession", vote: "Vote") -> str:
    from sqlalchemy import select

    from bot.models import CouncilMember, VoteParticipant

    members_result = await session.execute(
        select(CouncilMember)
        .where(CouncilMember.guild_id == vote.guild_id, CouncilMember.is_active == True)
        .order_by(
            CouncilMember.council_number.asc().nullslast(),
            CouncilMember.display_name.asc(),
        )
    )
    members = list(members_result.scalars().all())
    if not members:
        return ""

    participants_result = await session.execute(
        select(VoteParticipant)
        .where(VoteParticipant.vote_id == vote.id, VoteParticipant.has_voted == True)
    )
    votes_by_user = {p.user_id: p for p in participants_result.scalars().all()}

    lines = []
    for m in members:
        num = m.council_number
        label = f"О5-{num}" if num is not None else "О5-?"

        participant = votes_by_user.get(m.user_id)
        if participant and participant.option_id:
            from bot.models import VoteOption

            opt_r = await session.execute(select(VoteOption).where(VoteOption.id == participant.option_id))
            option = opt_r.scalar_one_or_none()
            vl = option.label if option else "—"

            ck = _VOTE_COLOR.get(vl, "d")
            c = _A[ck]
            sv = _VOTE_SYM.get(vl, "·")

            lines.append(f"  {label:<8} {c}{sv}  {vl}\x1b[0m")
        else:
            lines.append(f"  {label:<8} \x1b[90m·  не голосовал\x1b[0m")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


def build_vote_buttons(vote: "Vote") -> list[discord.ui.Button]:
    buttons = []
    if vote.status == "open":
        for opt in (vote.options or []):
            if opt.label == "ЗА":
                style = discord.ButtonStyle.success
                emoji = "\U0001f7e2"
            elif opt.label == "ПРОТИВ":
                style = discord.ButtonStyle.danger
                emoji = "\U0001f534"
            elif opt.label in ("ВОЗДЕРЖАЛСЯ", "ВОЗДЕРЖАТЬСЯ"):
                style = discord.ButtonStyle.secondary
                emoji = "\U0001f7e1"
            else:
                style = discord.ButtonStyle.primary
                emoji = None
            btn = discord.ui.Button(
                label=opt.label,
                custom_id=f"vote_{vote.id}_{opt.id}",
                style=style,
                emoji=emoji,
            )
            buttons.append(btn)
    return buttons


def build_admin_buttons(vote: "Vote") -> list[discord.ui.Button]:
    row1 = []
    if vote.status == "open":
        row1.append(discord.ui.Button(
            label="Приостановить",
            custom_id=f"admin_pause_{vote.id}",
            style=discord.ButtonStyle.secondary,
        ))
        row1.append(discord.ui.Button(
            label="Завершить",
            custom_id=f"admin_complete_{vote.id}",
            style=discord.ButtonStyle.danger,
        ))
    elif vote.status == "paused":
        row1.append(discord.ui.Button(
            label="Возобновить",
            custom_id=f"admin_resume_{vote.id}",
            style=discord.ButtonStyle.success,
        ))
        row1.append(discord.ui.Button(
            label="Завершить",
            custom_id=f"admin_complete_{vote.id}",
            style=discord.ButtonStyle.danger,
        ))
    return row1
