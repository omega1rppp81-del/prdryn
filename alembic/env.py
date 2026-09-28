import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import event, pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from bot.models import Base

config = context.config

db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://council:council@localhost:5432/council_votes")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _apply_connect_settings(dbapi_connection, _connection_record) -> None:
    """Никогда не позволяем миграциям висеть вечно на блокировках БД."""
    cursor = dbapi_connection.cursor()
    try:
        if db_url.startswith("sqlite"):
            cursor.execute("PRAGMA busy_timeout=20000")
        elif db_url.startswith("postgresql"):
            cursor.execute("SET lock_timeout = 30000")
            cursor.execute("SET statement_timeout = 120000")
    finally:
        cursor.close()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connect_args = {"timeout": 20} if db_url.startswith("sqlite") else {}

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    if db_url.startswith("sqlite") or db_url.startswith("postgresql"):
        event.listen(connectable.sync_engine, "connect", _apply_connect_settings)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
