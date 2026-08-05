from contextlib import contextmanager

from app.core import settings
from app.services.auth.oauth_google import get_google_verifier

GOOGLE_PROFILE = {
    "sub": "google-sub-123",
    "email": "newbie@gmail.com",
    "email_verified": True,
    "name": "New Bie",
}


def _use_fake_verifier(app, profile: dict) -> None:
    # Override the Google verifier dependency so no network call is made.
    app.dependency_overrides[get_google_verifier] = lambda: lambda _token: profile


async def test_google_login_creates_new_user(app, client):
    _use_fake_verifier(app, GOOGLE_PROFILE)

    resp = await client.post("/api/auth/google", json={"id_token": "fake"})
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]

    # the access token resolves to the freshly created user
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "newbie@gmail.com"
    assert body["is_email_verified"] is True


async def _user_count(session) -> int:
    from app.repositories.user import UserRepository

    _, total = await UserRepository(session).get_many(limit=100)
    return total


async def test_google_login_is_idempotent_for_same_account(app, client, session):
    _use_fake_verifier(app, GOOGLE_PROFILE)

    await client.post("/api/auth/google", json={"id_token": "fake"})
    await client.post("/api/auth/google", json={"id_token": "fake"})

    assert await _user_count(session) == 1  # no duplicate user created


async def test_google_login_links_to_existing_email(app, client, session):
    # user pre-exists (e.g. created via the users endpoint), then signs in with Google
    created = await client.post(
        "/api/users",
        json={"email": "newbie@gmail.com", "password": "supersecret123"},
    )
    assert created.status_code == 201

    _use_fake_verifier(app, GOOGLE_PROFILE)
    resp = await client.post("/api/auth/google", json={"id_token": "fake"})
    assert resp.status_code == 200

    assert await _user_count(session) == 1  # linked, not duplicated


async def test_refresh_returns_new_tokens(app, client):
    _use_fake_verifier(app, GOOGLE_PROFILE)
    tokens = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()

    resp = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_me_requires_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_rejects_invalid_token(client):
    resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


REGISTER_BODY = {"email": "pass@example.com", "password": "supersecret123", "full_name": "Pass User"}


async def test_register_creates_user_and_returns_tokens(client):
    resp = await client.post("/api/auth/register", json=REGISTER_BODY)
    assert resp.status_code == 201
    tokens = resp.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "pass@example.com"
    assert body["is_email_verified"] is False


async def test_register_rejects_duplicate_email(client):
    assert (await client.post("/api/auth/register", json=REGISTER_BODY)).status_code == 201
    assert (await client.post("/api/auth/register", json=REGISTER_BODY)).status_code == 409


async def test_register_rejects_short_password(client):
    resp = await client.post("/api/auth/register", json={"email": "x@example.com", "password": "short"})
    assert resp.status_code == 422


async def test_login_with_correct_password(client):
    await client.post("/api/auth/register", json=REGISTER_BODY)
    resp = await client.post("/api/auth/login", json={"email": "pass@example.com", "password": "supersecret123"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_rejects_wrong_password(client):
    await client.post("/api/auth/register", json=REGISTER_BODY)
    resp = await client.post("/api/auth/login", json={"email": "pass@example.com", "password": "wrongpassword"})
    assert resp.status_code == 401


async def test_login_rejects_unknown_email(client):
    resp = await client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "whatever123"})
    assert resp.status_code == 401


async def test_login_rejects_oauth_only_account(app, client):
    # a Google-created user has no password; password login must not work
    _use_fake_verifier(app, GOOGLE_PROFILE)
    await client.post("/api/auth/google", json={"id_token": "fake"})

    resp = await client.post("/api/auth/login", json={"email": "newbie@gmail.com", "password": "whatever123"})
    assert resp.status_code == 401


async def test_refresh_rejects_access_token(app, client):
    _use_fake_verifier(app, GOOGLE_PROFILE)
    tokens = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()
    # passing an access token where a refresh token is expected must fail
    resp = await client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


# --- refresh token lifecycle -------------------------------------------------
#
# A signature alone must not be enough: without a server-side record a stolen
# refresh token stays valid for its full 30 days and logout cannot stop it.


@contextmanager
def _no_grace_window():
    """Make a replay look old, without making the test sleep."""
    original = settings.auth.REFRESH_REUSE_GRACE_SECONDS
    settings.auth.REFRESH_REUSE_GRACE_SECONDS = -1
    try:
        yield
    finally:
        settings.auth.REFRESH_REUSE_GRACE_SECONDS = original


async def _register(client, email: str = "rt@gmail.com") -> dict:
    resp = await client.post("/api/auth/register", json={"email": email, "password": "rt-password-123"})
    return resp.json()


async def test_refresh_rotates_and_retires_the_old_token(client):
    tokens = await _register(client)

    refreshed = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != tokens["refresh_token"]

    # once the concurrency window has passed, the spent token is dead even
    # though its signature is still perfectly valid
    with _no_grace_window():
        replayed = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replayed.status_code == 401


async def test_two_clients_refreshing_at_once_stay_signed_in(client):
    """The popup, its service worker and each cabinet tab cannot coordinate.

    Two of them refreshing within a moment of each other is routine, and used
    to end every session of a perfectly innocent user.
    """
    tokens = await _register(client, "race@gmail.com")

    first = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    second = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert first.status_code == second.status_code == 200
    # and the session each of them ended up with still works
    for resp in (first, second):
        again = await client.post("/api/auth/refresh", json={"refresh_token": resp.json()["refresh_token"]})
        assert again.status_code == 200


async def test_replaying_a_spent_token_later_kills_every_session(client):
    # long after rotation a replay means the token leaked, and which copy is
    # the thief's is unknowable — so every session of that user ends
    tokens = await _register(client, "reuse@gmail.com")
    current = (await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).json()

    with _no_grace_window():
        await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})  # replay

    assert (await client.post("/api/auth/refresh", json={"refresh_token": current["refresh_token"]})).status_code == 401


async def test_logout_makes_the_refresh_token_unusable(client):
    tokens = await _register(client, "logout@gmail.com")

    assert (await client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})).status_code == 204
    assert (await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401


async def test_logout_of_an_unknown_token_is_not_an_error(client):
    # the caller wanted it gone, and it is
    resp = await client.post("/api/auth/logout", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 204


async def test_logout_everywhere_ends_all_sessions(client):
    first = await _register(client, "everywhere@gmail.com")
    second = (
        await client.post("/api/auth/login", json={"email": "everywhere@gmail.com", "password": "rt-password-123"})
    ).json()

    headers = {"Authorization": f"Bearer {first['access_token']}"}
    assert (await client.post("/api/auth/logout-all", headers=headers)).status_code == 204

    for tokens in (first, second):
        assert (
            await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        ).status_code == 401


async def test_a_forged_but_unknown_token_is_rejected(client):
    # correctly signed for a real user, but never issued by us
    from app.core.security.tokens import create_refresh_token

    await _register(client, "forged@gmail.com")
    resp = await client.post("/api/auth/refresh", json={"refresh_token": create_refresh_token(1)})
    assert resp.status_code == 401


async def test_two_logins_in_the_same_second_both_work(client):
    # tokens used to be byte-identical within one second, and the second login
    # collided on the stored hash
    await _register(client, "same-second@gmail.com")
    body = {"email": "same-second@gmail.com", "password": "rt-password-123"}

    first = await client.post("/api/auth/login", json=body)
    second = await client.post("/api/auth/login", json=body)

    assert first.status_code == second.status_code == 200
    assert first.json()["refresh_token"] != second.json()["refresh_token"]
