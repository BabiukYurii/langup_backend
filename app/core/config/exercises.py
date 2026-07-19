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

    # Language pairs are translated into, when the user has no native_language set.
    EXERCISE_FALLBACK_TRANSLATION_LANGUAGE: str = "uk"

    # Translate a word in the background as soon as it is captured, so building
    # a match-pairs round later needs no inference at all. Off by default so
    # tests and CI never reach the AI gateway; enabled in deployments.
    TRANSLATE_ON_CAPTURE: bool = False

    # Match-pairs: how many pairs are on screen, how many the round holds in
    # total, and how many wrong taps end it.
    MATCH_PAIRS_VISIBLE: int = 4
    MATCH_PAIRS_TOTAL: int = 10
    MATCH_PAIRS_MAX_MISTAKES: int = 3
