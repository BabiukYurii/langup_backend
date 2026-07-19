"""Request quotas.

These guard the two things that hurt: password guessing, and abuse of a
CPU-bound model where one call costs tens of seconds of the only core we have.
"""

import pytest
from fastapi import Request

from app.core import settings
from app.core.exc import RateLimitedException
from app.core.security import rate_limit


class FakeRedis:
    """Counts like Redis does, and can be told to fall over."""

    def __init__(self, broken: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.broken = broken

    async def incr(self, key: str) -> int:
        if self.broken:
            raise ConnectionError("redis is down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def get(self, key: str) -> int | None:
        if self.broken:
            raise ConnectionError("redis is down")
        return self.counts.get(key)

    async def expire(self, key: str, seconds: int) -> None:
        self.expiries[key] = seconds


@pytest.fixture
def limiter_on(monkeypatch):
    original = settings.rate_limit.RATE_LIMIT_ENABLED
    settings.rate_limit.RATE_LIMIT_ENABLED = True
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "_redis", lambda: fake)
    yield fake
    settings.rate_limit.RATE_LIMIT_ENABLED = original


def _request(ip: str = "1.2.3.4", forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (ip, 1234)})


async def test_requests_pass_until_the_quota_is_spent(limiter_on):
    limiter = rate_limit.RateLimiter("test", limit=3, window_seconds=60)
    for _ in range(3):
        await limiter(_request())

    with pytest.raises(RateLimitedException):
        await limiter(_request())


async def test_the_window_is_set_once_not_on_every_hit(limiter_on):
    # re-arming the expiry each time would make the window slide forever
    limiter = rate_limit.RateLimiter("test", limit=5, window_seconds=60)
    for _ in range(3):
        await limiter(_request())

    assert list(limiter_on.expiries.values()) == [60]


async def test_quotas_are_per_client(limiter_on):
    limiter = rate_limit.RateLimiter("test", limit=1, window_seconds=60)
    await limiter(_request(ip="1.1.1.1"))

    await limiter(_request(ip="2.2.2.2"))  # a different caller is unaffected
    with pytest.raises(RateLimitedException):
        await limiter(_request(ip="1.1.1.1"))


async def test_the_proxy_header_identifies_the_real_client(limiter_on):
    # we sit behind Cloudflare, so request.client is the tunnel, not the user
    limiter = rate_limit.RateLimiter("test", limit=1, window_seconds=60)
    await limiter(_request(forwarded="9.9.9.9, 10.0.0.1"))

    with pytest.raises(RateLimitedException):
        await limiter(_request(forwarded="9.9.9.9"))


def test_cloudflares_header_wins_over_x_forwarded_for():
    # CF-Connecting-IP is the un-spoofable one; XFF is a chain a caller controls
    req = Request(
        {
            "type": "http",
            "headers": [
                (b"cf-connecting-ip", b"5.5.5.5"),
                (b"x-forwarded-for", b"1.2.3.4, 9.9.9.9"),
            ],
            "client": ("10.0.0.1", 1),
        }
    )
    assert rate_limit.client_ip(req) == "5.5.5.5"


async def test_quotas_are_ignored_while_disabled(monkeypatch):
    settings.rate_limit.RATE_LIMIT_ENABLED = False
    monkeypatch.setattr(rate_limit, "_redis", lambda: FakeRedis())
    limiter = rate_limit.RateLimiter("test", limit=1, window_seconds=60)

    for _ in range(5):
        await limiter(_request())


async def test_a_redis_outage_lets_requests_through(monkeypatch):
    # losing the counter must not lock every user out of the app
    original = settings.rate_limit.RATE_LIMIT_ENABLED
    settings.rate_limit.RATE_LIMIT_ENABLED = True
    monkeypatch.setattr(rate_limit, "_redis", lambda: FakeRedis(broken=True))
    try:
        limiter = rate_limit.RateLimiter("test", limit=1, window_seconds=60)
        for _ in range(3):
            await limiter(_request())
    finally:
        settings.rate_limit.RATE_LIMIT_ENABLED = original


async def test_repeated_failures_lock_one_account_regardless_of_ip(limiter_on, monkeypatch):
    # the distributed-guess case: only failures count, and they count by email
    monkeypatch.setattr(settings.rate_limit, "RATE_LIMIT_LOGIN_PER_ACCOUNT_ATTEMPTS", 3)
    email = "victim@gmail.com"

    assert await rate_limit.login_locked(email) is False
    for _ in range(3):
        await rate_limit.record_login_failure(email)

    assert await rate_limit.login_locked(email) is True
    assert await rate_limit.login_locked("someone-else@gmail.com") is False  # only that account


async def test_a_locked_account_gets_429_even_with_the_right_password(app, client, limiter_on, monkeypatch):
    monkeypatch.setattr(settings.rate_limit, "RATE_LIMIT_LOGIN_PER_ACCOUNT_ATTEMPTS", 2)
    await client.post("/api/auth/register", json={"email": "locked@gmail.com", "password": "right-password-1"})

    for _ in range(2):
        await client.post("/api/auth/login", json={"email": "locked@gmail.com", "password": "wrong"})

    # even the correct password is refused while the account is locked
    blocked = await client.post("/api/auth/login", json={"email": "locked@gmail.com", "password": "right-password-1"})
    assert blocked.status_code == 429


async def test_a_successful_login_does_not_count_against_the_account(limiter_on):
    # a legitimate user signing in normally must never approach the lock
    for _ in range(50):
        assert await rate_limit.login_locked("regular@gmail.com") is False


async def test_login_answers_429_once_the_quota_is_spent(client, limiter_on, monkeypatch):
    monkeypatch.setattr(
        rate_limit.auth_rate_limit, "limit", 2
    )  # keep the test short; the real quota is larger
    body = {"email": "nobody@gmail.com", "password": "wrong-password-1"}

    for _ in range(2):
        assert (await client.post("/api/auth/login", json=body)).status_code == 401

    blocked = await client.post("/api/auth/login", json=body)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]  # tells a client how long to back off
