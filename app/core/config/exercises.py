# Exercise pool settings: how many exercises to keep pre-generated per user.
from app.core.config.base import BaseConfig


class ExerciseConfig(BaseConfig):
    # Desired number of READY exercises to keep in each user's pool.
    EXERCISE_POOL_TARGET: int = 5
    # Auto-refill the pool in a background task after a word is captured.
    # Off by default so tests/CI never reach the AI gateway; enabled in production.
    EXERCISE_POOL_AUTOFILL: bool = False
    # CEFR level used for generated exercises until per-user levels exist.
    EXERCISE_DEFAULT_LEVEL: str = "B1"
