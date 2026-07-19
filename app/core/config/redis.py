# Redis connection settings (Celery broker and result backend for now).
from urllib.parse import quote

from app.core.config.base import BaseConfig


class RedisConfig(BaseConfig):
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    @property
    def url(self) -> str:
        # The password is generated and may contain URL-unsafe characters.
        auth = f":{quote(self.REDIS_PASSWORD, safe='')}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
