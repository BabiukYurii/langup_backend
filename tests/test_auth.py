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


async def test_google_login_is_idempotent_for_same_account(app, client):
    _use_fake_verifier(app, GOOGLE_PROFILE)

    await client.post("/api/auth/google", json={"id_token": "fake"})
    await client.post("/api/auth/google", json={"id_token": "fake"})

    users = await client.get("/api/users")
    assert users.json()["total"] == 1  # no duplicate user created


async def test_google_login_links_to_existing_email(app, client):
    # user pre-exists (e.g. created via the users endpoint), then signs in with Google
    created = await client.post(
        "/api/users",
        json={"email": "newbie@gmail.com", "password": "supersecret123"},
    )
    assert created.status_code == 201

    _use_fake_verifier(app, GOOGLE_PROFILE)
    resp = await client.post("/api/auth/google", json={"id_token": "fake"})
    assert resp.status_code == 200

    users = await client.get("/api/users")
    assert users.json()["total"] == 1  # linked, not duplicated


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


async def test_refresh_rejects_access_token(app, client):
    _use_fake_verifier(app, GOOGLE_PROFILE)
    tokens = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()
    # passing an access token where a refresh token is expected must fail
    resp = await client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401
