from app.core.security.password import hash_password, verify_password
from app.repositories.user import UserRepository

NEW_USER = {
    "email": "alice@example.com",
    "password": "supersecret123",
    "full_name": "Alice",
    "native_language": "uk",
    "target_language": "en",
}


# ---------------- endpoint tests ----------------


async def test_create_user(client):
    resp = await client.post("/api/users", json=NEW_USER)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == NEW_USER["email"]
    assert body["role"] == "USER"
    assert body["status"] == "ACTIVE"
    assert "password" not in body and "hashed_password" not in body


async def test_create_duplicate_email_conflicts(client):
    await client.post("/api/users", json=NEW_USER)
    resp = await client.post("/api/users", json=NEW_USER)
    assert resp.status_code == 409


async def test_get_user(client):
    created = (await client.post("/api/users", json=NEW_USER)).json()
    resp = await client.get(f"/api/users/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["email"] == NEW_USER["email"]


async def test_get_missing_user_404(client):
    resp = await client.get("/api/users/999999")
    assert resp.status_code == 404


async def test_list_users_paginated(client):
    for i in range(3):
        await client.post("/api/users", json={**NEW_USER, "email": f"u{i}@example.com"})
    resp = await client.get("/api/users", params={"page": 1, "limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1 and body["limit"] == 2


async def test_update_user(client):
    created = (await client.post("/api/users", json=NEW_USER)).json()
    resp = await client.patch(f"/api/users/{created['id']}", json={"full_name": "Alice Smith"})
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Alice Smith"


async def test_delete_user(client):
    created = (await client.post("/api/users", json=NEW_USER)).json()
    resp = await client.delete(f"/api/users/{created['id']}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/users/{created['id']}")).status_code == 404


async def test_create_user_short_password_422(client):
    resp = await client.post("/api/users", json={**NEW_USER, "password": "short"})
    assert resp.status_code == 422


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
