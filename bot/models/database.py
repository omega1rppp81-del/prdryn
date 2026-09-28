from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings

logger = logging.getLogger(__name__)

engine: AsyncEngine | None = None
session_factory: async_sessionmaker[AsyncSession] | None = None

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_MIGRATION_TIMEOUT_SECONDS = 60
_migration_lock = threading.Lock()
_migrations_applied = False


def run_migrations(url: str | None = None) -> bool:
    """Применяет ожидающие alembic-миграции до head.

    Возвращает True, если миграции применены (или уже актуальны).
    Гарантированно не блокирует запуск дольше _MIGRATION_TIMEOUT_SECONDS:
    при зависании (блокировка БД другим процессом) возвращает False,
    бот продолжает старт.
    """
    global _migrations_applied

    db_url = url or settings.db.url

    if _migrations_applied:
        return True

    with _migration_lock:
        if _migrations_applied:
            return True

        if "sqlite" in db_url:
            db_path = db_url.split("///")[-1]
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        state: dict[str, BaseException | None] = {"error": None}

        def _upgrade() -> None:
            try:
                import alembic.command
                import alembic.config

                os.environ["DATABASE_URL"] = db_url
                cfg = alembic.config.Config(str(_BASE_DIR / "alembic.ini"))
                cfg.set_main_option("script_location", str(_BASE_DIR / "alembic"))
                cfg.set_main_option("prepend_sys_path", str(_BASE_DIR))
                alembic.command.upgrade(cfg, "head")
                logger.info("Миграции БД применены до head")
            except Exception as e:
                state["error"] = e
                logger.exception("Ошибка применения миграций БД: %s", e)

        thread = threading.Thread(target=_upgrade, daemon=True, name="alembic-upgrade")
        thread.start()
        thread.join(_MIGRATION_TIMEOUT_SECONDS)

        if thread.is_alive():
            logger.error(
                "Миграции БД (%s) не завершились за %d с. Бот продолжит запуск. "
                "Проверьте, что файл БД не заблокирован другим процессом "
                "(старый процесс бота, редактор БД, антивирус).",
                db_url,
                _MIGRATION_TIMEOUT_SECONDS,
            )
            return False

        if state["error"] is not None:
            logger.error(
                "Миграции БД (%s) завершились с ошибкой: %s. "
                "Запуск продолжается со старой схемой.",
                db_url,
                state["error"],
            )
            return False

        _migrations_applied = True
        return True


def init_db(url: str | None = None) -> None:
    global engine, session_factory
    db_url = url or settings.db.url

    if engine is not None and session_factory is not None:
        return

    if run_migrations(db_url):
        logger.info("Схема БД актуальна")
    else:
        logger.warning("Схема БД может быть не актуальна (миграции не применены)")

    if "sqlite" in db_url:
        db_path = db_url.split("///")[-1]
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        engine = create_async_engine(db_url, echo=False, connect_args={"timeout": 30})
    else:
        engine = create_async_engine(db_url, echo=False, pool_size=20, max_overflow=10)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    global engine, session_factory
    if engine:
        await engine.dispose()
        engine = None
        session_factory = None
