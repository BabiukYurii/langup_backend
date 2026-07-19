# Background worker settings.
from app.core.config.base import BaseConfig


class CeleryConfig(BaseConfig):
    # Off by default so tests and CI never enqueue anything; deployments with a
    # running worker turn it on. When off, background work falls back to
    # FastAPI BackgroundTasks, which is fine for a single small instance.
    CELERY_ENABLED: bool = False

    # Generating one exercise on CPU takes tens of seconds and a refill does
    # several, so the ceiling is generous.
    CELERY_TASK_TIME_LIMIT: int = 900
    CELERY_TASK_SOFT_TIME_LIMIT: int = 840

    # A word the model failed to turn into an exercise is usually fine on a
    # second try — the model is not deterministic.
    CELERY_TASK_MAX_RETRIES: int = 2
    CELERY_RETRY_BACKOFF_SECONDS: int = 30

    # How long a finished task's result stays queryable by the UI.
    CELERY_RESULT_EXPIRES_SECONDS: int = 3600
