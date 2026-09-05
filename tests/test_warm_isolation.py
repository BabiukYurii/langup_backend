"""Ф2 of the playlist warm-up: keeping background work out of a learner's way.

Two separate mechanisms, because they solve two different problems that look
alike: the queue keeps warming off the worker slot, the Redis mark keeps it off
the model. Neither substitutes for the other.
"""

import asyncio
import time

import pytest

from app.celery.config import celery_app
from app.services.learning import model_busy


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)


class _DeadRedis:
    async def set(self, *a, **k):
        raise ConnectionError("redis is down")

    async def get(self, *a, **k):
        raise ConnectionError("redis is down")


@pytest.fixture(autouse=True)
def _forget_past_failures():
    """The circuit breaker is module state; each test starts with it closed."""
    model_busy._reset_availability()
    yield
    model_busy._reset_availability()


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(model_busy, "get_redis", lambda: redis)
    return redis


@pytest.fixture
def dead_redis(monkeypatch):
    monkeypatch.setattr(model_busy, "get_redis", lambda: _DeadRedis())


# --- the queue -------------------------------------------------------------


def test_warm_tasks_are_routed_off_the_default_queue():
    """A song nobody opened yet must not sit in front of an exercise refill."""
    route = celery_app.conf.task_routes["warm.*"]
    assert route == {"queue": "warm"}


def test_user_facing_tasks_stay_on_the_default_queue():
    routes = celery_app.conf.task_routes
    assert not any(pattern.startswith("ai.") for pattern in routes)


# --- the mark --------------------------------------------------------------


async def test_nothing_is_busy_to_begin_with(fake_redis):
    assert await model_busy.model_is_busy() is False


async def test_user_work_makes_the_model_busy(fake_redis):
    await model_busy.mark_user_work()
    assert await model_busy.model_is_busy() is True


async def test_the_mark_expires_rather_than_sticking(fake_redis, monkeypatch):
    """A crashed request must not silence warming for the rest of the night."""
    seen = {}

    async def capture(key, value, ex=None):
        seen["ex"] = ex

    monkeypatch.setattr(fake_redis, "set", capture)
    await model_busy.mark_user_work()
    assert seen["ex"] > 0


async def test_an_unreachable_redis_does_not_stop_warming(dead_redis):
    """Losing politeness beats a background job that dies when a cache blinks."""
    await model_busy.mark_user_work()  # must not raise
    assert await model_busy.model_is_busy() is False


async def test_an_unreachable_redis_does_not_break_a_real_request(dead_redis):
    """The mark is best-effort in both directions: a learner never sees this."""
    await model_busy.mark_user_work()  # must not raise


async def test_a_slow_redis_is_abandoned_rather_than_waited_on(monkeypatch):
    """The mark sits in front of the model on the request path. A Redis that
    hangs must cost a rounding error, not the seconds a connect timeout takes."""

    class _Hanging:
        async def set(self, *a, **k):
            await asyncio.sleep(30)

        async def get(self, *a, **k):
            await asyncio.sleep(30)

    monkeypatch.setattr(model_busy, "get_redis", lambda: _Hanging())
    started = time.monotonic()
    await model_busy.mark_user_work()
    assert time.monotonic() - started < 1.0


async def test_a_failure_stops_further_attempts_for_a_while(monkeypatch):
    """Otherwise every request pays the timeout again while Redis is down."""
    attempts = {"n": 0}

    class _Counting:
        async def set(self, *a, **k):
            attempts["n"] += 1
            raise ConnectionError("down")

        async def get(self, *a, **k):
            attempts["n"] += 1
            raise ConnectionError("down")

    monkeypatch.setattr(model_busy, "get_redis", lambda: _Counting())
    await model_busy.mark_user_work()
    await model_busy.mark_user_work()
    assert await model_busy.model_is_busy() is False
    assert attempts["n"] == 1  # tried once, then left it alone
