from app.core.config.ai import AIConfig
from app.core.config.app import AppBaseConfig
from app.core.config.auth import AuthConfig
from app.core.config.base import BaseConfig
from app.core.config.celery import CeleryConfig
from app.core.config.db import DbBaseConfig
from app.core.config.exercises import ExerciseConfig
from app.core.config.jwt import JwtConfig
from app.core.config.redis import RedisConfig

__all__ = ["Settings", "settings"]


class Settings(BaseConfig):
    """Central settings aggregator. Add more sub-configs (redis, ai, ...) here
    as those domains are implemented."""

    app: AppBaseConfig = AppBaseConfig()
    db: DbBaseConfig = DbBaseConfig()
    jwt: JwtConfig = JwtConfig()
    auth: AuthConfig = AuthConfig()
    ai: AIConfig = AIConfig()
    exercises: ExerciseConfig = ExerciseConfig()
    redis: RedisConfig = RedisConfig()
    celery: CeleryConfig = CeleryConfig()


settings = Settings()
