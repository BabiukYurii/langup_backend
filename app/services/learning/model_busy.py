"""Keeping the warmer out of the model's way.

One llama.cpp server answers one inference at a time, so background warming and
a learner waiting on a tap compete for the same hardware. Separate Celery queues
cannot arbitrate that on their own — two workers on two queues still share one
model — so the two sides have to agree in Redis instead.

User-facing work leaves a mark with a short TTL; the warmer reads it between
words and yields. The grain is one inference: a request arriving while the
warmer is mid-word still waits for that word to finish. Anything finer would
need the model to be preemptible, which it is not.

Best-effort in the strongest sense. This is a politeness signal for a background
nicety, so it is never worth a millisecond of a learner's time: every call is
capped by a short timeout, and once Redis fails the module stops calling it at
all for a while. Both directions degrade to "not busy" — warming carries on and
requests are untouched.
"""

import asyncio
import logging
import time

from app.core import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_BUSY_KEY = "llm:user_work"

# The mark sits on the request path, in front of the model. A Redis that is
# merely slow must cost a rounding error, never the 2s it takes to time out a
# connection — that would be a latency bug in exchange for a hint.
_TIMEOUT_SECONDS = 0.2

# And once it has failed, stop asking. Otherwise every request pays the timeout
# again for as long as Redis is down.
_RETRY_AFTER_SECONDS = 30.0

_unavailable_until = 0.0


def _reset_availability() -> None:
    """Forget a past failure. For tests, which swap the client underneath us."""
    global _unavailable_until
    _unavailable_until = 0.0


def _note_failure() -> None:
    global _unavailable_until
    _unavailable_until = time.monotonic() + _RETRY_AFTER_SECONDS


def _giving_redis_a_rest() -> bool:
    return time.monotonic() < _unavailable_until


async def mark_user_work() -> None:
    """Record that a learner is waiting on the model right now."""
    if _giving_redis_a_rest():
        return
    try:
        await asyncio.wait_for(
            get_redis().set(_BUSY_KEY, "1", ex=settings.warm.WARM_BUSY_TTL_SECONDS),
            _TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 — politeness must never fail a real request
        _note_failure()
        logger.debug("Could not mark user work", exc_info=True)


async def model_is_busy() -> bool:
    """Whether user-facing work has touched the model recently."""
    if _giving_redis_a_rest():
        return False
    try:
        return await asyncio.wait_for(get_redis().get(_BUSY_KEY), _TIMEOUT_SECONDS) is not None
    except Exception:  # noqa: BLE001 — an unreadable mark means carry on
        _note_failure()
        logger.debug("Could not read the user-work mark", exc_info=True)
        return False
