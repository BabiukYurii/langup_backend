from urllib.parse import urlsplit, urlunsplit

from pydantic import Field

from app.core.config.base import BaseConfig


class DbBaseConfig(BaseConfig):
    # Full connection string (e.g. the Neon URL). For sqlite tests, point this
    # at e.g. sqlite+aiosqlite:///./test.db via the DATABASE_URL env var.
    DATABASE_URL: str = Field(..., alias="DATABASE_URL")
    ECHO: bool = Field(False, alias="DB_ECHO")

    @property
    def url(self) -> str:
        """Async SQLAlchemy URL. Normalizes the scheme to an async driver and
        strips libpq-only query params (sslmode/channel_binding) that asyncpg
        does not accept in the URL (SSL is passed via connect_args instead)."""
        parts = urlsplit(self.DATABASE_URL)
        scheme = parts.scheme
        if scheme in ("postgres", "postgresql"):
            scheme = "postgresql+asyncpg"
        elif scheme == "sqlite":
            scheme = "sqlite+aiosqlite"
        return urlunsplit((scheme, parts.netloc, parts.path, "", ""))

    @property
    def connect_args(self) -> dict:
        # Neon (and other managed Postgres) require TLS; asyncpg takes ssl here.
        return {"ssl": True} if self.url.startswith("postgresql+asyncpg") else {}
