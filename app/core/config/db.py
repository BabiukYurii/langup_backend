from urllib.parse import urlsplit, urlunsplit

from pydantic import Field

from app.core.config.base import BaseConfig


class DbBaseConfig(BaseConfig):
    # Full connection string (e.g. the Neon URL). For sqlite (tests/CI) point
    # this at e.g. sqlite+aiosqlite:///:memory: via the DATABASE_URL env var.
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")
    ECHO: bool = Field(False, alias="DB_ECHO")

    @property
    def url(self) -> str:
        """Async SQLAlchemy URL.

        Postgres URLs are switched to the asyncpg driver and stripped of
        libpq-only query params (sslmode/channel_binding) that asyncpg does not
        accept in the URL (SSL is passed via connect_args instead). sqlite URLs
        are passed through untouched (only ensuring the aiosqlite driver)."""
        raw = self.DATABASE_URL
        if raw.startswith(("postgres://", "postgresql://")):
            parts = urlsplit(raw)
            return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, "", ""))
        if raw.startswith("sqlite://") and "+aiosqlite" not in raw:
            return raw.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return raw

    @property
    def connect_args(self) -> dict:
        # Neon (and other managed Postgres) require TLS; asyncpg takes ssl here.
        return {"ssl": True} if self.url.startswith("postgresql+asyncpg") else {}
