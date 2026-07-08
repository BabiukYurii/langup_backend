# AI service (langup_ai inference gateway on the mini-PC) connection settings.
from app.core.config.base import BaseConfig


class AIConfig(BaseConfig):
    AI_SERVICE_URL: str = "http://localhost:8100"
    AI_SERVICE_API_KEY: str = "change-me"
    # CPU inference is slow (tens of seconds on the mini-PC) — generous timeout.
    AI_SERVICE_TIMEOUT_SECONDS: float = 120.0
