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

    # How many runs IN A ROW may translate nothing before the rotation gives up
    # on a pair. Consecutive and fruitless, not total: a long song legitimately
    # needs several runs to get through its words, and any run that translates
    # even one word clears the count. So this only ever fires on a pair that is
    # genuinely going nowhere.
    #
    # A safety net, not an optimisation, and it exists because the absence of
    # one froze the whole feature: three songs containing words the model will
    # never translate (DJ, TVP — proper nouns it echoes back, which the response
    # guard rejects) stayed incomplete forever, and since the rotation goes
    # strictly by playlist position, nothing beyond position 1 was ever reached.
    # Five days, seven songs out of three hundred.
    #
    # A pair that exhausts this keeps every translation it did manage; only the
    # re-checking stops.
    WARM_MAX_FRUITLESS_ATTEMPTS: int = 2
