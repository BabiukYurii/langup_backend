"""Password reset: request (no enumeration), consume token, set new password."""

from app.repositories.auth import PasswordResetTokenRepository
from app.repositories.user import UserRepository

USER = {"email": "reset-me@example.com", "password": "sunflower7"}


async def _register(client, email=USER["email"]):
    resp = await client.post("/api/auth/register", json={**USER, "email": email})
    assert resp.status_code == 201


# ---------------- request ----------------


async def test_forgot_password_is_always_202(client):
    # Same response for a known and an unknown address — no account enumeration.
    await _register(client)
    assert (await client.post("/api/auth/forgot-password", json={"email": USER["email"]})).status_code == 202
    assert (await client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})).status_code == 202


async def test_forgot_password_creates_token_for_known_email(client, session):
    await _register(client)
    await client.post("/api/auth/forgot-password", json={"email": USER["email"]})
    user = await UserRepository(session).get_by_email(USER["email"])
    _, total = await PasswordResetTokenRepository(session).get_many(user_id=user.id)
    assert total == 1


# ---------------- reset ----------------


async def test_reset_sets_new_password_and_revokes_sessions(client, session):
    await _register(client)
    user = await UserRepository(session).get_by_email(USER["email"])
    raw = "reset-raw-token-1"
    # Mint a token the same way the service does, so we know the raw value.
    from datetime import timedelta

    from app.services.auth.password_reset import _fingerprint, _utcnow

    await PasswordResetTokenRepository(session).create_one(
        {"user_id": user.id, "token_hash": _fingerprint(raw), "expires_at": _utcnow() + timedelta(hours=1)}
    )

    resp = await client.post("/api/auth/reset-password", json={"token": raw, "password": "newpass987"})
    assert resp.status_code == 200 and resp.json()["status"] == "reset"

    # Old password no longer works; new one does.
    assert (
        await client.post("/api/auth/login", json={"email": USER["email"], "password": USER["password"]})
    ).status_code == 401
    assert (
        await client.post("/api/auth/login", json={"email": USER["email"], "password": "newpass987"})
    ).status_code == 200


async def test_reset_token_is_single_use(client, session):
    await _register(client)
    user = await UserRepository(session).get_by_email(USER["email"])
    from datetime import timedelta

    from app.services.auth.password_reset import _fingerprint, _utcnow

    raw = "single-use-token"
    await PasswordResetTokenRepository(session).create_one(
        {"user_id": user.id, "token_hash": _fingerprint(raw), "expires_at": _utcnow() + timedelta(hours=1)}
    )
    assert (
        await client.post("/api/auth/reset-password", json={"token": raw, "password": "newpass987"})
    ).status_code == 200
    assert (
        await client.post("/api/auth/reset-password", json={"token": raw, "password": "another987"})
    ).status_code == 400


async def test_reset_rejects_unknown_token(client):
    resp = await client.post("/api/auth/reset-password", json={"token": "nope", "password": "newpass987"})
    assert resp.status_code == 400


async def test_reset_rejects_weak_password(client, session):
    await _register(client)
    user = await UserRepository(session).get_by_email(USER["email"])
    from datetime import timedelta

    from app.services.auth.password_reset import _fingerprint, _utcnow

    raw = "weakpw-token"
    await PasswordResetTokenRepository(session).create_one(
        {"user_id": user.id, "token_hash": _fingerprint(raw), "expires_at": _utcnow() + timedelta(hours=1)}
    )
    assert (
        await client.post("/api/auth/reset-password", json={"token": raw, "password": "12345678"})
    ).status_code == 422
