import pytest

from app.enums.user import RoleEnum, UserStatus
from app.models import Exercise, User, UserWord, Word
from app.repositories.user import UserRepository

pytestmark = pytest.mark.asyncio


async def _make_user(session, email, role=RoleEnum.USER, status=UserStatus.ACTIVE):
    user = User(email=email, role=role.value, status=status.value)
    session.add(user)
    await session.flush()
    return user


async def _token_for(app, client, session, email, role):
    """Register via the normal flow, then elevate the row to the wanted role."""
    await client.post("/api/users", json={"email": email, "password": "supersecret123"})
    user = await UserRepository(session).get_by_email(email)
    await UserRepository(session).update_one(user, {"role": role.value})
    login = await client.post("/api/auth/login", json={"email": email, "password": "supersecret123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user


# --- authorization ---------------------------------------------------------


async def test_admin_endpoints_reject_anonymous(client):
    assert (await client.get("/api/admin/users")).status_code == 401


async def test_admin_endpoints_reject_plain_user(app, client, session):
    headers, _ = await _token_for(app, client, session, "plain@x.com", RoleEnum.USER)
    assert (await client.get("/api/admin/users", headers=headers)).status_code == 403


async def test_admin_can_list_users(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    await _make_user(session, "someone@x.com")
    resp = await client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()["items"]}
    assert {"admin@x.com", "someone@x.com"} <= emails


async def test_admin_can_search_users(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    await _make_user(session, "findme@x.com")
    resp = await client.get("/api/admin/users", params={"query": "findme"}, headers=headers)
    assert [u["email"] for u in resp.json()["items"]] == ["findme@x.com"]


# --- moderation ------------------------------------------------------------


async def test_admin_can_suspend_a_user(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "target@x.com")
    resp = await client.patch(f"/api/admin/users/{target.id}", json={"status": "SUSPENDED"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUSPENDED"


async def test_admin_cannot_edit_self(app, client, session):
    headers, admin = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    resp = await client.patch(f"/api/admin/users/{admin.id}", json={"status": "SUSPENDED"}, headers=headers)
    assert resp.status_code == 400


async def test_admin_cannot_manage_another_admin(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    other_admin = await _make_user(session, "other-admin@x.com", role=RoleEnum.ADMIN)
    resp = await client.patch(f"/api/admin/users/{other_admin.id}", json={"status": "SUSPENDED"}, headers=headers)
    assert resp.status_code == 403


async def test_admin_cannot_grant_super_admin(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "target@x.com")
    resp = await client.patch(f"/api/admin/users/{target.id}", json={"role": "SUPER_ADMIN"}, headers=headers)
    assert resp.status_code == 403


async def test_super_admin_can_manage_an_admin(app, client, session):
    headers, _ = await _token_for(app, client, session, "super@x.com", RoleEnum.SUPER_ADMIN)
    admin = await _make_user(session, "admin@x.com", role=RoleEnum.ADMIN)
    resp = await client.patch(f"/api/admin/users/{admin.id}", json={"status": "SUSPENDED"}, headers=headers)
    assert resp.status_code == 200


# --- viewing a user's learning data ----------------------------------------


async def test_admin_sees_a_users_vocabulary(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "learner@x.com")
    word = Word(lemma="resilient", language="en")
    session.add(word)
    await session.flush()
    session.add(UserWord(user_id=target.id, word_uuid=word.uuid))
    await session.flush()

    resp = await client.get(f"/api/admin/users/{target.id}/vocabulary", headers=headers)
    assert resp.status_code == 200
    assert [w["lemma"] for w in resp.json()["items"]] == ["resilient"]


async def test_admin_sees_a_users_exercises_with_answers(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "learner@x.com")
    session.add(
        Exercise(
            user_id=target.id,
            exercise_type="TYPING",
            status="READY",
            prompt="Type it",
            payload={"text": "___1___"},
            answer={"1": "occurs"},
        )
    )
    await session.flush()

    resp = await client.get(f"/api/admin/users/{target.id}/exercises", headers=headers)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["exercise_type"] == "TYPING"
    assert item["answer"] == {"1": "occurs"}  # admin view reveals the key


async def test_admin_vocabulary_404_for_missing_user(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    assert (await client.get("/api/admin/users/999999/vocabulary", headers=headers)).status_code == 404
