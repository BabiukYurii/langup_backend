from app.core.config.app import AppBaseConfig
from app.core.config.base import BaseConfig
from app.core.config.db import DbBaseConfig

__all__ = ["Settings", "settings"]


class Settings(BaseConfig):
    """Central settings aggregator. Add more sub-configs (redis, jwt, ai, ...)
    here as those domains are implemented."""

    app: AppBaseConfig = AppBaseConfig()
    db: DbBaseConfig = DbBaseConfig()


settings = Settings()
