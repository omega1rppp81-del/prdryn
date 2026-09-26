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


def run_migrations(url: str | None = None) -> None:
    """Apply pending alembic migrations so the schema matches the code."""
    db_url = url or settings.db.url

    if "sqlite" in db_url:
        db_path = db_url.split("///")[-1]
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

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
            logger.exception("Ошибка применения миграций БД: %s", e)
            raise

    thread = threading.Thread(target=_upgrade, daemon=True)
    thread.start()
    thread.join()


def init_db(url: str | None = None) -> None:
    global engine, session_factory
    db_url = url or settings.db.url

    run_migrations(db_url)

    if "sqlite" in db_url:
        db_path = db_url.split("///")[-1]
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        engine = create_async_engine(db_url, echo=False)
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
