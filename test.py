"""Тестовый лаунчер бота: in-memory БД, логи с префиксом [TEST], консольные команды.

Команды:
    start                    запустить бота (TEST_TOKEN из .env, иначе DISCORD_BOT_TOKEN)
    shutdown                 остановить бота (консоль и in-memory БД продолжают жить)
    restart                  перезапустить бота (in-memory БД сохраняется)
    clear                    очистить in-memory БД (таблицы пересозданы), бот продолжает работу
    simulate <id> [ВАРИАНТ|МЕТКА=N ...]  голоса совета: по кругу / все за вариант / точные счётчики
    exit                     стоп бота + очистка памяти + выход
    help                     эта справка
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from contextlib import suppress
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
MEM_URL = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"
FAKE_MEMBER_BASE = 9_000_000_000_000_000_000

os.environ["DATABASE_URL"] = MEM_URL
os.environ["LOG_LEVEL"] = "DEBUG"

for _stream in (sys.stdout, sys.stderr):
    with suppress(Exception):
        _stream.reconfigure(encoding="utf-8", errors="replace")
with suppress(Exception):
    sys.stdin.reconfigure(encoding="utf-8")


class TestFormatter(logging.Formatter):
    """Ставит [TEST] перед каждой строкой, включая строки traceback."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        return "\n".join("[TEST] " + line for line in text.splitlines())


def _setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        TestFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    root.addHandler(handler)
    for name, level in (
        ("discord", logging.DEBUG),
        ("sqlalchemy", logging.WARNING),
        ("sqlalchemy.engine", logging.INFO),
        ("sqlalchemy.engine.Pool", logging.INFO),
        ("aiosqlite", logging.INFO),
    ):
        logging.getLogger(name).setLevel(level)


_setup_logging()
log = logging.getLogger("test")

from discord.utils import MISSING  # noqa: E402
from dotenv import dotenv_values  # noqa: E402
from sqlalchemy import select as sa_select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from bot.models import database as db  # noqa: E402
from bot.models.models import Base, CouncilMember, VoteParticipant  # noqa: E402
from bot.services import audit, voting  # noqa: E402

import bot.bot as bb  # noqa: E402

HELP = """\
Команды тестового режима:
  start                    запустить бота (TEST_TOKEN из .env, иначе DISCORD_BOT_TOKEN)
  shutdown                 остановить бота (консоль и in-memory БД продолжают жить)
  restart                  перезапустить бота (in-memory БД сохраняется)
  clear                    очистить in-memory БД (таблицы пересозданы), бот продолжает работу
  simulate <id> [ВАРИАНТ|МЕТКА=N ...]
                           имитировать голоса совета: без аргументов — распределение по кругу,
                           ВАРИАНТ — все голосуют за него (подпись или позиция 1..N),
                           МЕТКА=N — точные счётчики, напр.: simulate 1 ЗА=3 ПРОТИВ=9
  exit                     стоп бота, очистка памяти и выход
  help                     показать эту справку"""

cmd_q: asyncio.Queue[str] = asyncio.Queue()
loop_ref: asyncio.AbstractEventLoop | None = None
anchor_engine = None
anchor_conn = None
bot_task: asyncio.Task | None = None
ever_started = False


def _read_token() -> tuple[str, str]:
    """Читает токен при каждом start: env TEST_TOKEN -> .env TEST_TOKEN -> DISCORD_BOT_TOKEN."""
    vals = dotenv_values(ENV_PATH) or {}
    candidates = (
        ("TEST_TOKEN (переменная окружения)", (os.environ.get("TEST_TOKEN") or "").strip()),
        ("TEST_TOKEN (.env)", (vals.get("TEST_TOKEN") or "").strip()),
        ("DISCORD_BOT_TOKEN (.env)", (vals.get("DISCORD_BOT_TOKEN") or "").strip()),
        ("DISCORD_BOT_TOKEN (переменная окружения)", (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()),
    )
    for label, token in candidates:
        if token:
            return token, label
    return "", ""


async def _init_test_db() -> None:
    global anchor_engine, anchor_conn

    engine = create_async_engine(
        MEM_URL,
        echo=False,
        pool_size=1,
        max_overflow=0,
        pool_timeout=600,
        connect_args={"timeout": 30, "check_same_thread": False},
    )
    db.engine = engine
    db.session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    db._migrations_applied = True

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    anchor_engine = create_async_engine(
        MEM_URL,
        echo=False,
        pool_size=1,
        max_overflow=0,
        pool_timeout=600,
        connect_args={"timeout": 30, "check_same_thread": False},
    )
    anchor_conn = await anchor_engine.connect()

    log.info(
        "in-memory БД готова: %d таблиц, shared-cache, pool=1, anchor-коннект держит память.",
        len(Base.metadata.tables),
    )


def _on_bot_done(task: asyncio.Task) -> None:
    if task.cancelled():
        log.info("Задача бота отменена.")
        return
    exc = task.exception()
    if exc is not None:
        log.error("Бот завершился с ошибкой: %s: %s", type(exc).__name__, exc)
    else:
        log.info("Бот остановлен.")


async def _launch() -> None:
    global bot_task, ever_started

    if bot_task is not None and not bot_task.done():
        log.warning("Бот уже запущен.")
        return

    token, source = _read_token()
    if not token:
        log.error("Токен не найден: заполните TEST_TOKEN в .env и повторите start.")
        return

    if ever_started:
        b = bb.bot
        with suppress(Exception):
            await b.http.close()
        b.clear()
        b.http.connector = MISSING
        await b._async_setup_hook()
        b.tree.interaction_check = bb._tree_interaction_check
        bb._patch_view_store_gate()
    ever_started = True

    log.info("Запуск бота… (токен из %s)", source)
    bot_task = asyncio.create_task(bb.bot.start(token), name="test.bot.start")
    bot_task.add_done_callback(_on_bot_done)


async def _shutdown(quiet: bool = False) -> bool:
    global bot_task

    if bot_task is None or bot_task.done():
        if not quiet:
            log.warning("Бот не запущен.")
        return False

    if not quiet:
        log.info("Остановка бота…")

    for loop_obj in (bb.auto_close_task, bb.reminder_task, bb.auto_sync_council_task):
        with suppress(Exception):
            if loop_obj.is_running():
                loop_obj.cancel()
                inner = getattr(loop_obj, "_task", None)
                if inner is not None:
                    with suppress(asyncio.CancelledError, Exception):
                        await inner

    with suppress(Exception):
        await bb.bot.close()

    try:
        await asyncio.wait_for(bot_task, 15)
    except asyncio.TimeoutError:
        log.error("Бот не остановился за 15 с — принудительная отмена.")
        bot_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await bot_task
    except asyncio.CancelledError:
        if bot_task.done():
            log.debug("Задача бота завершилась отменой (закрытие соединения).")
        else:
            raise
    except Exception as exc:
        log.debug("Задача бота завершилась: %r", exc)

    if not quiet:
        log.info("Бот остановлен, in-memory БД сохраняется.")
    return True


async def _cmd_clear() -> None:
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            async with db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
            bb._isolation_cache.clear()
            log.info(
                "Память очищена: таблицы пересозданы, кэш изоляции сброшен. Бот продолжает работу."
            )
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.5)
    log.error("Не удалось очистить in-memory БД: %r", last_error)


def _pick_option(options, force: str):
    wanted = force.casefold()
    for opt in options:
        if opt.label.casefold() == wanted:
            return opt
    if force.isdigit():
        index = int(force)
        if 1 <= index <= len(options):
            return options[index - 1]
    return None


async def _cmd_simulate(args: list[str]) -> None:
    if not args:
        log.warning("Формат: simulate <vote_id> [ВАРИАНТ|позиция 1..N | МЕТКА=N ...]")
        return
    try:
        vote_id = int(args[0])
    except ValueError:
        log.warning("ID голосования должен быть числом, получено: %r", args[0])
        return

    # разбор аргументов: "МЕТКА=N" (или "МЕТКА:N") — точные счётчики, иначе — форс-вариант
    count_specs: list[str] = []
    force_args: list[str] = []
    for token in args[1:]:
        sep = "=" if "=" in token else (":" if ":" in token else None)
        if sep and token.rsplit(sep, 1)[1].strip().isdigit():
            count_specs.append(token)
        else:
            force_args.append(token)

    if len(force_args) > 1:
        log.warning("Укажите не более одного варианта: %r", force_args)
        return
    if force_args and count_specs:
        log.warning("ВАРИАНТ и МЕТКА=N одновременно не используются — выберите одно.")
        return

    force = force_args[0] if force_args else None
    counts: list[tuple[str, int]] = []
    for token in count_specs:
        sep = "=" if "=" in token else ":"
        label, _, num = token.rpartition(sep)
        counts.append((label.strip(), int(num)))

    async with db.get_session() as session:
        vote = await voting.get_vote_by_id(session, vote_id)
        if vote is None:
            log.warning("Голосование %s не найдено.", vote_id)
            return

        options = list(vote.options)
        if not options:
            log.warning("У голосования %s нет вариантов ответа.", vote_id)
            return

        forced_option = None
        if force is not None:
            forced_option = _pick_option(options, force)
            if forced_option is None:
                labels = ", ".join(o.label for o in options)
                log.warning("Вариант %r не найден. Есть: %s (или позиция 1..%d)", force, labels, len(options))
                return

        planned: list[tuple] = []  # [(option, count)]
        if counts:
            for label, num in counts:
                if num < 1:
                    log.warning("Счётчик должен быть не меньше 1: %r", label)
                    return
                option = _pick_option(options, label)
                if option is None:
                    labels = ", ".join(o.label for o in options)
                    log.warning("Метка %r не найдена. Есть: %s (или позиция 1..%d)", label, labels, len(options))
                    return
                planned.append((option, num))

        result = await session.execute(
            sa_select(CouncilMember)
            .where(CouncilMember.guild_id == vote.guild_id, CouncilMember.is_active == True)
            .order_by(CouncilMember.council_number)
        )
        members = list(result.scalars().all())

        needed = sum(n for _, n in planned) if planned else (5 if not members else len(members))
        if len(members) < needed:
            next_num = (max((m.council_number or 0) for m in members) + 1) if members else 1
            added = 0
            while len(members) < needed:
                num = next_num + added
                member = CouncilMember(
                    guild_id=vote.guild_id,
                    user_id=FAKE_MEMBER_BASE + num,
                    display_name=f"Тест-советник {num}",
                    council_number=num,
                    is_active=True,
                    weight=1.0,
                )
                session.add(member)
                members.append(member)
                added += 1
            await session.flush()
            log.info("Совет: добавлено %d фейковых членов (всего %d).", added, len(members))

        async def cast_one(member, option) -> None:
            participant = await voting.cast_vote(
                session,
                vote,
                member.user_id,
                option.id,
                user_name=member.display_name or str(member.user_id),
                weight=member.weight or 1.0,
            )
            await audit.log_action(
                session,
                action="vote_cast",
                guild_id=vote.guild_id,
                vote_id=vote.id,
                user_id=member.user_id,
                user_name=member.display_name,
                details={"option": option.label},
                source="test",
            )
            note = "изменён" if participant.change_count > 0 else "новый"
            log.info("   %s → %s (%s)", member.display_name or member.user_id, option.label, note)

        if planned:
            log.info(
                "Голосование #%s «%s» (id=%s, статус=%s) — точное распределение: %s",
                vote.vote_number,
                vote.title,
                vote.id,
                vote.status,
                ", ".join(f"{o.label}×{n}" for o, n in planned),
            )
            plan: dict[int, object] = {}
            idx = 0
            for option, num in planned:
                for _ in range(num):
                    plan[members[idx].user_id] = option
                    idx += 1

            existing = await session.execute(
                sa_select(VoteParticipant).where(
                    VoteParticipant.vote_id == vote.id,
                    VoteParticipant.has_voted == True,
                )
            )
            for participant in existing.scalars().all():
                if participant.user_id not in plan:
                    await voting.revoke_vote(session, vote, participant.user_id)
                    log.info("   снят голос: user_id=%s", participant.user_id)

            for member in members:
                option = plan.get(member.user_id)
                if option is not None:
                    await cast_one(member, option)
        else:
            log.info(
                "Голосование #%s «%s» (id=%s, статус=%s) — симуляция %d голосов…",
                vote.vote_number,
                vote.title,
                vote.id,
                vote.status,
                len(members),
            )
            for index, member in enumerate(members):
                option = forced_option if forced_option is not None else options[index % len(options)]
                await cast_one(member, option)

        tally = await session.execute(
            sa_select(VoteParticipant).where(
                VoteParticipant.vote_id == vote.id,
                VoteParticipant.has_voted == True,
            )
        )
        counts: dict[int, float] = {}
        for participant in tally.scalars().all():
            counts[participant.option_id] = counts.get(participant.option_id, 0.0) + (
                participant.weight or 0.0
            )
        total = sum(counts.values())
        for option in options:
            count = counts.get(option.id, 0.0)
            percent = (count / total * 100) if total else 0.0
            log.info("   Итог %s: %s (%.1f%%)", option.label, count, percent)
        log.info("Всего голосов: %s", total)

    if not bb.bot.is_ready():
        log.info("Бот офлайн — опубликованные сообщения не обновлены.")
        return

    try:
        async with db.get_session() as session:
            fresh = await voting.get_vote_by_id(session, vote_id)
            if fresh is None:
                return
            updated = await voting.refresh_vote_messages(session, fresh, bb.bot)
            log.info("Обновлено сообщений: %d.", updated)
    except Exception:
        log.exception("Ошибка обновления опубликованных сообщений.")


async def _dispatch(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    parts = text.split()
    command, args = parts[0].casefold(), parts[1:]

    if command in ("exit", "quit", "q"):
        if bot_task is not None and not bot_task.done():
            await _shutdown()
        log.info("Выход из тестового режима.")
        return False
    if command == "start":
        await _launch()
    elif command == "shutdown":
        await _shutdown()
    elif command == "restart":
        await _shutdown()
        await _launch()
    elif command == "clear":
        await _cmd_clear()
    elif command == "simulate":
        await _cmd_simulate(args)
    elif command in ("help", "h", "?"):
        log.info(HELP)
    else:
        log.warning("Неизвестная команда %r. Наберите help — список команд.", parts[0])
    return True


def _reader() -> None:
    while True:
        try:
            line = input("[TEST] > ")
        except (EOFError, KeyboardInterrupt, OSError):
            if loop_ref is not None:
                with suppress(RuntimeError):
                    loop_ref.call_soon_threadsafe(cmd_q.put_nowait, "exit")
            return
        if loop_ref is not None:
            with suppress(RuntimeError):
                loop_ref.call_soon_threadsafe(cmd_q.put_nowait, line)


async def _main() -> None:
    global loop_ref, anchor_engine, anchor_conn

    loop_ref = asyncio.get_running_loop()
    await _init_test_db()
    audit.set_client(bb.bot)

    threading.Thread(target=_reader, daemon=True, name="test-console").start()

    log.info("=== ТЕСТОВЫЙ РЕЖИМ ===")
    log.info("БД: in-memory SQLite (shared-cache, pool=1); логи — с префиксом [TEST].")
    log.info(HELP)
    await _launch()

    try:
        while True:
            line = await cmd_q.get()
            try:
                if not await _dispatch(line):
                    break
            except Exception:
                log.exception("Ошибка выполнения команды %r", line.strip())
    finally:
        log.info("Завершение работы…")
        with suppress(Exception):
            if bot_task is not None and not bot_task.done():
                await _shutdown(quiet=True)
        with suppress(Exception):
            if db.engine is not None:
                await db.close_db()
        with suppress(Exception):
            if anchor_conn is not None:
                await anchor_conn.close()
        with suppress(Exception):
            if anchor_engine is not None:
                await anchor_engine.dispose()
        log.info("Память освобождена. До встречи!")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
