"""Email verification: token issue/consume and the practice/capture gate."""

from app.repositories.auth import EmailVerificationTokenRepository
from app.repositories.user import UserRepository
from app.services.auth.email_verification import EmailVerificationService

REGISTER = {"email": "verify-me@example.com", "password": "sunflower7"}


async def _register(client):
    resp = await client.post("/api/auth/register", json=REGISTER)
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------- issuing ----------------


async def test_register_creates_unverified_user_and_token(client, session):
    await _register(client)
    user = await UserRepository(session).get_by_email(REGISTER["email"])
    assert user is not None and user.is_email_verified is False
    tokens, total = await EmailVerificationTokenRepository(session).get_many(user_id=user.id)
    assert total == 1 and tokens[0].used_at is None


# ---------------- verifying ----------------


async def test_verify_link_marks_user_verified(client, session):
    headers = await _register(client)
    user = await UserRepository(session).get_by_email(REGISTER["email"])
    raw = await EmailVerificationService(session)._issue_token(user.id)

    resp = await client.get(f"/api/auth/verify-email?token={raw}", follow_redirects=False)
    assert resp.status_code == 303 and "verified=1" in resp.headers["location"]

    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["is_email_verified"] is True


async def test_verify_rejects_unknown_token(client, session):
    await _register(client)
    resp = await client.get("/api/auth/verify-email?token=not-a-real-token", follow_redirects=False)
    assert resp.status_code == 303 and "verified=0" in resp.headers["location"]
    user = await UserRepository(session).get_by_email(REGISTER["email"])
    assert user.is_email_verified is False


async def test_token_is_single_use(client, session):
    await _register(client)
    user = await UserRepository(session).get_by_email(REGISTER["email"])
    raw = await EmailVerificationService(session)._issue_token(user.id)
    assert "verified=1" in (await client.get(f"/api/auth/verify-email?token={raw}", follow_redirects=False)).headers["location"]
    # Second use of the same link fails.
    assert "verified=0" in (await client.get(f"/api/auth/verify-email?token={raw}", follow_redirects=False)).headers["location"]


async def test_resend_reports_status(client, session):
    headers = await _register(client)
    assert (await client.post("/api/auth/verify-email/resend", headers=headers)).json()["status"] == "sent"

    user = await UserRepository(session).get_by_email(REGISTER["email"])
    await UserRepository(session).update_one(user, {"is_email_verified": True})
    assert (await client.post("/api/auth/verify-email/resend", headers=headers)).json()["status"] == "already_verified"


# ---------------- enforcement (medium: block practice + saving) ----------------


async def test_unverified_cannot_capture(client, session):
    headers = await _register(client)
    user = await UserRepository(session).get_by_email(REGISTER["email"])
    await client.patch(f"/api/users/{user.id}", json={"native_language": "uk"}, headers=headers)

    resp = await client.post("/api/vocabulary", json={"word": "hello", "language": "en"}, headers=headers)
    assert resp.status_code == 400 and resp.json()["detail"] == "email_not_verified"


async def test_unverified_cannot_practise(client):
    headers = await _register(client)
    assert (await client.get("/api/exercises/next", headers=headers)).status_code == 403
    assert (await client.post("/api/exercises/refill", headers=headers)).status_code == 403


async def test_verified_user_passes_the_gate(client, session):
    headers = await _register(client)
    user = await UserRepository(session).get_by_email(REGISTER["email"])
    raw = await EmailVerificationService(session)._issue_token(user.id)
    await client.get(f"/api/auth/verify-email?token={raw}", follow_redirects=False)
    await client.patch(f"/api/users/{user.id}", json={"native_language": "uk"}, headers=headers)

    resp = await client.post("/api/vocabulary", json={"word": "hello", "language": "en"}, headers=headers)
    assert resp.status_code == 201
    # Practice endpoint no longer 403s (404 = empty pool, which is fine here).
    assert (await client.get("/api/exercises/next", headers=headers)).status_code in (200, 404)
