from __future__ import annotations

import os
import secrets
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = field(default_factory=lambda: _get("DATABASE_URL", "sqlite+aiosqlite:///data/council_votes.db"))


@dataclass(frozen=True)
class DiscordConfig:
    token: str = field(default_factory=lambda: _get("DISCORD_BOT_TOKEN"))
    client_id: str = field(default_factory=lambda: _get("DISCORD_CLIENT_ID"))
    client_secret: str = field(default_factory=lambda: _get("DISCORD_CLIENT_SECRET"))
    redirect_uri: str = field(default_factory=lambda: _get("DISCORD_REDIRECT_URI", "http://localhost:8000/api/auth/callback"))


@dataclass(frozen=True)
class Settings:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    log_level: str = field(default_factory=lambda: _get("LOG_LEVEL", "INFO"))
    timezone: str = field(default_factory=lambda: _get("TZ", "Europe/Moscow"))
    secret_key: str = field(default_factory=lambda: secrets.token_hex(32))


settings = Settings()
