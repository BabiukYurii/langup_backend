# Request quotas. Backed by Redis so limits hold across worker processes.
from app.core.config.base import BaseConfig


class RateLimitConfig(BaseConfig):
    # Off by default so tests and local runs need no Redis; on in deployments.
    RATE_LIMIT_ENABLED: bool = False

    # Sign-in and sign-up: tight, because this is what gets brute-forced. Keyed
    # by client IP, since there is no account yet to key by.
    RATE_LIMIT_AUTH_ATTEMPTS: int = 10
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = 300

    # Generating exercises costs tens of seconds of the only CPU we have, so
    # this guards the model rather than the database.
    RATE_LIMIT_GENERATION_ATTEMPTS: int = 20
    RATE_LIMIT_GENERATION_WINDOW_SECONDS: int = 3600
