# Pre-warming playlist songs: translations and audio prepared before anyone asks.
from app.core.config.base import BaseConfig


class WarmConfig(BaseConfig):
    # Off by default. The whole point is to spend idle capacity, so a
    # deployment without spare capacity should simply never turn it on.
    WARM_ENABLED: bool = False

    # How long a mark left by user-facing work keeps the warmer away. Long
    # enough to cover a refill of several exercises, short enough that a crashed
    # request cannot silence warming for the rest of the night.
    WARM_BUSY_TTL_SECONDS: int = 120

    # A run stops after this and lets the next tick continue. Keeps every task
    # short, so nothing sits in front of a learner's request for long. The cache
    # is the cursor, so stopping early costs nothing but one lyrics fetch.
    WARM_RUN_BUDGET_SECONDS: int = 90

    # Ceiling per run, so one long song cannot take the night. What is left goes
    # to the next round — which is what keeps the rotation fair.
    WARM_WORDS_PER_RUN: int = 40

    # How often the scheduler hands out one song. Deliberately not aggressive:
    # the model is shared with the people actually using the app.
    WARM_TICK_SECONDS: int = 300

    # A pair whose full pass found nothing missing is not re-fetched for this
    # long — songs are static, so re-checking often would be pure waste.
    WARM_RECHECK_DAYS: int = 30
