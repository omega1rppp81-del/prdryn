from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from bot.models import Vote

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

_CHANGE_MODE_TEXT = {
    "change": "Изменение",
    "revoke": "Отзыв",
    "none": "Нет",
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
    change = _CHANGE_MODE_TEXT.get(vote.change_mode, vote.change_mode)
    mandatory = "Да" if vote.is_mandatory else "Нет"

    params = (
        f"```\n"
        f"  Тип         {_TYPE_TEXT.get(vote.vote_type, vote.vote_type)}\n"
        f"  Режим       {_ANONYMITY_TEXT.get(vote.anonymity_level, vote.anonymity_level)}\n"
        f"  Изменение   {change}\n"
        f"  Обязат.     {mandatory}\n"
        f"  Воздержание {abstain}\n"
        + (f"  Лимит       до {vote.max_multi_choices} вариант(ов)\n" if vote.vote_type == "multi_choice" else "")
        + f"```"
    )
    embed.add_field(name="── Параметры ──", value=params, inline=False)

    # ── Results (ANSI) ──
    if show_results and vote.result_data and "options" in vote.result_data:
        embed.add_field(
            name="── Результаты ──",
            value="```ansi\n" + _results_ansi(vote.result_data) + "\n```",
            inline=False,
        )
    elif vote.status in ("open", "paused"):
        if session is not None:
            from bot.services.voting import compute_live_tally

            tally = await compute_live_tally(session, vote)
            threshold = max(1, vote.min_votes_for_results or 0)
            if vote.show_results_immediately and tally["total_voted"] >= threshold:
                embed.add_field(
                    name="── Текущие итоги ──",
                    value="```ansi\n"
                    + _results_ansi(tally, show_percentages=bool(vote.show_percentages))
                    + "\n```",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="── Проголосовало ──",
                    value=f"```ansi\n  \x1b[32m{tally['total_voted']}\x1b[0m из {tally['total_eligible']} участников\n```",
                    inline=False,
                )
        else:
            voted_count = len([p for p in (vote.participants or []) if p.has_voted])
            embed.add_field(
                name="── Проголосовало ──",
                value=f"```ansi\n  \x1b[32m{voted_count}\x1b[0m из 0 участников\n```",
                inline=False,
            )

    # ── Author + deadline (normal text, not ANSI) ──
    meta_parts = []
    if vote.ends_at:
        meta_parts.append(f"**Срок:** {discord.utils.format_dt(vote.ends_at, 'f')} ({discord.utils.format_dt(vote.ends_at, 'R')})")
    if vote.anonymity_level != "full":
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


def _results_ansi(data: dict, show_winner: bool = False, show_percentages: bool = True) -> str:
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
        pct_part = f"  {pct:>5.1f}%" if show_percentages else ""
        count_txt = str(int(count)) if float(count).is_integer() else str(count)
        lines.append(
            f"\x1b[1m{label:<14}\x1b[0m "
            f"{bar}{pct_part}  {count_txt}{marker}"
        )

    total_voted = data.get("total_voted", 0)
    total_eligible = data.get("total_eligible", 0)
    turnout = data.get("turnout_percent", 0)
    lines.append("")
    if show_percentages:
        lines.append(
            f"\x1b[90mПроголосовало: {total_voted} из {total_eligible}"
            f"  │  Явка: {turnout:.1f}%\x1b[0m"
        )
    else:
        lines.append(f"\x1b[90mПроголосовало: {total_voted} из {total_eligible}\x1b[0m")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Completed vote embed
# ---------------------------------------------------------------------------


async def build_completed_embed(vote: "Vote", session: "AsyncSession | None" = None) -> discord.Embed:
    sym = _STATUS_SYMBOL.get(vote.status, "◆")
    stxt = _STATUS_TEXT.get(vote.status, "Завершено").upper()

    desc = []
    desc.append(f"{'━' * 48}")
    desc.append(f"  {sym}  ГОЛОСОВАНИЕ №{vote.vote_number}  ┃  {stxt}")
    desc.append(f"{'━' * 48}")
    desc.append("")
    desc.append(f"```text\n{vote.title}\n```")

    reason = (
        vote.cancel_reason
        if vote.status == "cancelled"
        else vote.completion_reason
    )
    if reason:
        desc.append(f"```ansi\n\x1b[37mПричина: {reason[:300]}\x1b[0m\n```")

    embed = discord.Embed(description="\n".join(desc), color=0x2B2D31)

    # ── Results (ANSI) ──
    if vote.result_data and "options" in vote.result_data:
        embed.add_field(
            name="── Результаты ──",
            value="```ansi\n" + _results_ansi(vote.result_data, show_winner=True) + "\n```",
            inline=False,
        )

    # ── Council table (ANSI) ──
    if vote.anonymity_level == "open" and vote.show_voter_list and session is not None:
        table = await _build_council_table(session, vote)
        if table:
            embed.add_field(
                name="── Совет ──",
                value="```ansi\n" + table + "\n```",
                inline=False,
            )

    # ── Mandatory members who did not vote ──
    if vote.is_mandatory and vote.anonymity_level == "open" and session is not None:
        from sqlalchemy import select as sa_select

        from bot.models import VoteMandatoryMember

        pend_result = await session.execute(
            sa_select(VoteMandatoryMember)
            .where(
                VoteMandatoryMember.vote_id == vote.id,
                VoteMandatoryMember.has_voted == False,
                VoteMandatoryMember.is_exempt == False,
            )
            .order_by(VoteMandatoryMember.user_name.asc())
        )
        pending = list(pend_result.scalars().all())
        if pending:
            names = ", ".join(m.user_name or f"<@{m.user_id}>" for m in pending[:25])
            if len(pending) > 25:
                names += f" и ещё {len(pending) - 25}"
            embed.add_field(
                name=f"── Не выполнили обязательное ({len(pending)}) ──",
                value=names,
                inline=False,
            )

    # ── Author + timestamp (normal text) ──
    meta_parts = []
    if vote.anonymity_level != "full":
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

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# Диапазоны декоративных символов, которые разные шрифты рисуют с разной
# шириной (ломают выравнивание моноширинной таблицы) — вырезаем их из ников.
_DROP_SYMBOL_RANGES = (
    (0x2500, 0x257F),   # Box Drawing
    (0x2580, 0x259F),   # Block Elements
    (0x25A0, 0x25FF),   # Geometric Shapes
    (0x2600, 0x26FF),   # Miscellaneous Symbols
    (0x2700, 0x27BF),   # Dingbats
    (0x2B00, 0x2BFF),   # Miscellaneous Symbols and Arrows
)

_ZERO_WIDTH = frozenset({0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF})


def _is_dropped_symbol(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _DROP_SYMBOL_RANGES)


def _char_width(ch: str) -> int:
    """Ширина символа в клетках моноширинного шрифта."""
    cp = ord(ch)
    if cp in _ZERO_WIDTH:
        return 0
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf", "Cc"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def _display_width(text: str) -> int:
    """Видимая ширина строки (ANSI-коды и zero-width не учитываются)."""
    return sum(_char_width(ch) for ch in _ANSI_RE.sub("", text))


def _truncate_width(text: str, limit: int) -> str:
    """Обрезает строку по видимой ширине, не разрывая комбинирующиеся символы."""
    if limit <= 0:
        return ""
    if _display_width(text) <= limit:
        return text
    budget = limit - 1
    out: list[str] = []
    width = 0
    for ch in text:
        w = _char_width(ch)
        if w == 0:
            out.append(ch)
            continue
        if width + w > budget:
            break
        out.append(ch)
        width += w
    return "".join(out).rstrip() + "…"


def _sanitize_name(text: str) -> str:
    """Нормализует отображаемое имя: убирает «фэнси»-шрифты, zalgo, служебные
    и разной ширины декоративные символы, чтобы ники не ломали моноширинную
    таблицу и не подделывали текст."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    kept: list[str] = []
    for ch in normalized:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf", "Cc", "Cs", "Co", "Cn"):
            continue
        if _is_dropped_symbol(ord(ch)):
            continue
        kept.append(ch)
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def _center_cell(text: str, width: int, color: str | None = None) -> str:
    text = _truncate_width(text, width)
    pad = max(0, width - _display_width(text))
    left = pad // 2
    right = pad - left
    if color:
        return " " * left + color + text + "\x1b[0m" + " " * right
    return " " * left + text + " " * right


def _box_table(headers: list[str], columns: list[list[str]], colors: list[str | None], max_chars: int = 1000) -> str:
    n = len(headers)
    # ANSI-коды невидимы при отрисовке, но входят в лимит символов поля Discord
    max_chars -= sum(len(c) + 4 for c in colors if c)
    rows = max((len(c) for c in columns), default=0)
    cols = [list(c) for c in columns]
    for c in cols:
        c.extend([""] * (rows - len(c)))

    min_w = [_display_width(h) + 2 for h in headers]

    def widths(cs: list[list[str]]) -> list[int]:
        return [
            max(min_w[i], max((_display_width(x) for x in cs[i]), default=0) + 2)
            for i in range(n)
        ]

    def total_chars(w: list[int], r: int) -> int:
        s = sum(w)
        return (r + 4) * (s + 4) + (r + 3)

    # ── 1) Вмещаем строки в бюджет (иначе обрезаем хвосты, оставляя "…+N") ──
    if rows:
        s_min = sum(min_w)
        capacity = (max_chars - (4 * s_min + 19)) // (s_min + 5)
        if capacity < 2:
            capacity = 2
        if rows > capacity:
            keep = capacity - 1
            for c in cols:
                if len(c) > keep:
                    c[:] = c[:keep] + [f"…+{len(c) - keep}"]
            rows = max(len(c) for c in cols)

    # ── 2) Сужаем самую широкую колонку до тех пор, пока таблица не влезет ──
    w = widths(cols)
    while total_chars(w, rows) > max_chars:
        deltas = [w[i] - min_w[i] for i in range(n)]
        if max(deltas) <= 0:
            break
        w[deltas.index(max(deltas))] -= 1

    # ── 3) Урезаем ячейки под итоговые ширины ──
    for i in range(n):
        limit = w[i] - 2
        cols[i] = [_truncate_width(s, limit) for s in cols[i]]

    top = "┌" + "┬".join("─" * x for x in w) + "┐"
    sep = "├" + "┼".join("─" * x for x in w) + "┤"
    bot = "└" + "┴".join("─" * x for x in w) + "┘"
    head = "│" + "│".join(_center_cell(headers[i], w[i], colors[i]) for i in range(n)) + "│"

    out = [top, head, sep]
    for r in range(rows):
        out.append("│" + "│".join(_center_cell(cols[i][r], w[i]) for i in range(n)) + "│")
    out.append(bot)
    return "\n".join(out)


async def _build_council_table(session: "AsyncSession", vote: "Vote") -> str:
    from sqlalchemy import select

    from bot.models import CouncilMember, VoteParticipant, VoteOption
    from bot.utils.council import parse_council_number

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

    options_result = await session.execute(
        select(VoteOption).where(VoteOption.vote_id == vote.id).order_by(VoteOption.position)
    )
    options = list(options_result.scalars().all())

    if options:
        headers = [_sanitize_name(o.label) or o.label for o in options]
        id_to_col = {o.id: i for i, o in enumerate(options)}
    else:
        headers = ["ЗА", "ПРОТИВ", "ВОЗДЕРЖАЛСЯ"]
        id_to_col = {}

    columns: list[list[str]] = [[] for _ in headers]

    for m in members:
        number = m.council_number
        if number is None:
            number = parse_council_number(m.display_name or "")
        label = f"О5-{number}" if number is not None else "О5-?"

        participant = votes_by_user.get(m.user_id)
        if participant and participant.has_voted:
            p_ids = participant.option_ids or (
                [participant.option_id] if participant.option_id is not None else []
            )
            for oid in p_ids:
                idx = id_to_col.get(oid)
                if idx is not None:
                    columns[idx].append(label)

    if all(not c for c in columns):
        columns = [["-" for _ in headers]]

    colors = [_A[_VOTE_COLOR.get(h.upper(), "d")] for h in headers]
    return _box_table(headers, columns, colors)


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


def build_vote_view(vote: "Vote") -> discord.ui.View | None:
    """Вью для опубликованного сообщения голосования.

    Кнопки ставятся только на primary-сообщение; копии в других каналах
    остаются embed-only (см. publish в bot.py и refresh_vote_messages).
    """
    if vote.status != "open":
        return None
    view = discord.ui.View(timeout=None)

    if vote.vote_type == "multi_choice":
        option_buttons = []
        for i, opt in enumerate((vote.options or [])[:15]):
            btn = discord.ui.Button(
                label=opt.label,
                custom_id=f"mv_{vote.id}_{opt.id}",
                style=discord.ButtonStyle.primary,
            )
            btn.row = i // 5
            option_buttons.append(btn)
        for btn in option_buttons:
            view.add_item(btn)
        next_row = (len(option_buttons) - 1) // 5 + 1 if option_buttons else 0
        confirm_btn = discord.ui.Button(
            label="Подтвердить выбор",
            custom_id=f"mvok_{vote.id}",
            style=discord.ButtonStyle.success,
            emoji="\u2705",
        )
        confirm_btn.row = next_row
        view.add_item(confirm_btn)
        utility_row = next_row + 1
    else:
        option_buttons = build_vote_buttons(vote)[:15]
        for i, btn in enumerate(option_buttons):
            btn.row = i // 5
            view.add_item(btn)
        next_row = (len(option_buttons) - 1) // 5 + 1 if option_buttons else 0
        utility_row = next_row

    if vote.change_mode == "revoke":
        revoke_btn = discord.ui.Button(
            label="Отозвать мой голос",
            custom_id=f"vrevoke_{vote.id}",
            style=discord.ButtonStyle.secondary,
            emoji="\U0001f5d1\ufe0f",
        )
        revoke_btn.row = utility_row
        view.add_item(revoke_btn)
    veto_btn = discord.ui.Button(
        label="ВЕТО",
        custom_id=f"veto_{vote.id}",
        style=discord.ButtonStyle.danger,
        emoji="\U0001f6d1",
    )
    veto_btn.row = utility_row
    view.add_item(veto_btn)
    return view

