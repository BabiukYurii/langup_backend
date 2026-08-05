from app.core.security.password import hash_password, verify_password
from app.enums.user import RoleEnum
from app.repositories.user import UserRepository

NEW_USER = {
    "email": "alice@example.com",
    "password": "supersecret123",
    "full_name": "Alice",
    "native_language": "uk",
    "target_language": "en",
}


async def _login(client, session, email="alice@example.com", admin=False):
    """Create an account (public POST), optionally make it admin, and sign in."""
    await client.post("/api/users", json={**NEW_USER, "email": email})
    user = await UserRepository(session).get_by_email(email)
    if admin:
        await UserRepository(session).update_one(user, {"role": RoleEnum.ADMIN.value})
    login = await client.post("/api/auth/login", json={"email": email, "password": NEW_USER["password"]})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user.id


# ---------------- registration (public) ----------------


async def test_create_user(client):
    resp = await client.post("/api/users", json=NEW_USER)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == NEW_USER["email"]
    assert body["role"] == "USER" and body["status"] == "ACTIVE"
    assert "password" not in body and "hashed_password" not in body


async def test_create_duplicate_email_conflicts(client):
    await client.post("/api/users", json=NEW_USER)
    assert (await client.post("/api/users", json=NEW_USER)).status_code == 409


async def test_create_user_short_password_422(client):
    assert (await client.post("/api/users", json={**NEW_USER, "password": "short"})).status_code == 422


async def test_create_user_rejects_weak_passwords(client):
    for weak in ("12345678", "aaaaaaaa", "password", "qwerty123"):
        resp = await client.post("/api/users", json={**NEW_USER, "email": f"{weak}@x.com", "password": weak})
        assert resp.status_code == 422, weak


async def test_register_rejects_weak_password(client):
    resp = await client.post("/api/auth/register", json={"email": "w@x.com", "password": "12345678"})
    assert resp.status_code == 422


async def test_register_accepts_a_reasonable_password(client):
    resp = await client.post("/api/auth/register", json={"email": "ok@x.com", "password": "sunflower7"})
    assert resp.status_code == 201


# ---------------- authorization (the fixed access-control hole) ----------------


async def test_user_endpoints_reject_anonymous(client):
    # Before the fix these all worked without a token (data leak + deletion).
    assert (await client.get("/api/users")).status_code == 401
    assert (await client.get("/api/users/1")).status_code == 401
    assert (await client.patch("/api/users/1", json={"full_name": "x"})).status_code == 401
    assert (await client.delete("/api/users/1")).status_code == 401


async def test_list_users_is_admin_only(client, session):
    headers, _ = await _login(client, session, "plain@x.com")
    assert (await client.get("/api/users", headers=headers)).status_code == 403


async def test_user_cannot_touch_another_account(app, client, session):
    a_headers, _ = await _login(client, session, "a@x.com")
    _, b_id = await _login(client, session, "b@x.com")
    assert (await client.get(f"/api/users/{b_id}", headers=a_headers)).status_code == 403
    assert (await client.patch(f"/api/users/{b_id}", json={"full_name": "x"}, headers=a_headers)).status_code == 403
    assert (await client.delete(f"/api/users/{b_id}", headers=a_headers)).status_code == 403


# ---------------- self / admin access ----------------


async def test_self_can_read_and_update(client, session):
    headers, uid = await _login(client, session)
    assert (await client.get(f"/api/users/{uid}", headers=headers)).status_code == 200
    resp = await client.patch(f"/api/users/{uid}", json={"full_name": "Alice Smith"}, headers=headers)
    assert resp.status_code == 200 and resp.json()["full_name"] == "Alice Smith"


async def test_admin_can_manage_others(client, session):
    admin_h, _ = await _login(client, session, "admin@x.com", admin=True)
    _, target = await _login(client, session, "target@x.com")
    assert (await client.get(f"/api/users/{target}", headers=admin_h)).status_code == 200
    assert (await client.get("/api/users", headers=admin_h)).status_code == 200
    assert (await client.delete(f"/api/users/{target}", headers=admin_h)).status_code == 204
    assert (await client.get(f"/api/users/{target}", headers=admin_h)).status_code == 404


# ---------------- repository / unit tests ----------------


async def test_repository_get_by_email(session):
    repo = UserRepository(session)
    await repo.create_one({"email": "bob@example.com", "hashed_password": hash_password("x" * 10)})
    found = await repo.get_by_email("bob@example.com")
    assert found is not None and found.email == "bob@example.com"
    assert await repo.get_by_email("nobody@example.com") is None


def test_password_hashing_roundtrip():
    hashed = hash_password("supersecret123")
    assert hashed != "supersecret123"
    assert verify_password("supersecret123", hashed)
    assert not verify_password("wrong", hashed)
