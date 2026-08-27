from __future__ import annotations

import os
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

engine: AsyncEngine | None = None
session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(url: str | None = None) -> None:
    global engine, session_factory
    db_url = url or settings.db.url

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
