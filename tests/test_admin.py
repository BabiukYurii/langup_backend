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


# --- creating / deleting users ---------------------------------------------


async def test_admin_creates_a_user(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    resp = await client.post(
        "/api/admin/users",
        json={"email": "fresh@x.com", "password": "supersecret123", "full_name": "Fresh"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "fresh@x.com"


async def test_admin_cannot_create_privileged_user(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    resp = await client.post(
        "/api/admin/users",
        json={"email": "new-admin@x.com", "password": "supersecret123", "role": "ADMIN"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_super_admin_creates_an_admin(app, client, session):
    headers, _ = await _token_for(app, client, session, "super@x.com", RoleEnum.SUPER_ADMIN)
    resp = await client.post(
        "/api/admin/users",
        json={"email": "made-admin@x.com", "password": "supersecret123", "role": "ADMIN"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "ADMIN"


async def test_admin_deletes_a_user(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "doomed@x.com")
    assert (await client.delete(f"/api/admin/users/{target.id}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/admin/users/{target.id}", headers=headers)).status_code == 404


async def test_admin_cannot_delete_self(app, client, session):
    headers, admin = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    assert (await client.delete(f"/api/admin/users/{admin.id}", headers=headers)).status_code == 400


async def test_admin_cannot_delete_another_admin(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    other = await _make_user(session, "peer@x.com", role=RoleEnum.ADMIN)
    assert (await client.delete(f"/api/admin/users/{other.id}", headers=headers)).status_code == 403


# --- editing a user's vocabulary -------------------------------------------


async def test_admin_adds_and_removes_vocabulary(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "learner@x.com")

    add = await client.post(
        f"/api/admin/users/{target.id}/vocabulary",
        json={"word": "Occurs", "language": "en"},
        headers=headers,
    )
    assert add.status_code == 201
    assert add.json()["lemma"] == "occur"  # lemmatized on the way in
    uw_uuid = add.json()["uuid"]

    # duplicate is rejected
    dup = await client.post(
        f"/api/admin/users/{target.id}/vocabulary",
        json={"word": "occur", "language": "en"},
        headers=headers,
    )
    assert dup.status_code == 409

    rm = await client.delete(f"/api/admin/users/{target.id}/vocabulary/{uw_uuid}", headers=headers)
    assert rm.status_code == 204
    listing = await client.get(f"/api/admin/users/{target.id}/vocabulary", headers=headers)
    assert listing.json()["total"] == 0


# --- editing the shared dictionary -----------------------------------------


async def test_admin_edits_shared_word(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    word = Word(lemma="ocurr", language="en")  # a typo to fix
    session.add(word)
    await session.flush()

    resp = await client.patch(
        f"/api/admin/words/{word.uuid}",
        json={"lemma": "occur", "translation": "ставатися"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["lemma"] == "occur"
    assert body["definitions"] == [{"lang": "uk", "translation": "ставатися"}]


async def test_admin_word_edit_rejects_lemma_collision(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    session.add(Word(lemma="occur", language="en"))
    dupe = Word(lemma="occurs", language="en")
    session.add(dupe)
    await session.flush()

    resp = await client.patch(f"/api/admin/words/{dupe.uuid}", json={"lemma": "occur"}, headers=headers)
    assert resp.status_code == 409  # would collide with the existing lemma


# --- editing / deleting exercises ------------------------------------------


async def _seed_exercise(session, user_id):
    ex = Exercise(
        user_id=user_id,
        exercise_type="TYPING",
        status="READY",
        prompt="Type it",
        payload={"text": "___1___"},
        answer={"1": "occurs"},
    )
    session.add(ex)
    await session.flush()
    return ex


async def test_admin_changes_exercise_status(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "learner@x.com")
    ex = await _seed_exercise(session, target.id)

    resp = await client.patch(f"/api/admin/exercises/{ex.uuid}", json={"status": "COMPLETED"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


async def test_admin_deletes_exercise(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    target = await _make_user(session, "learner@x.com")
    ex = await _seed_exercise(session, target.id)

    assert (await client.delete(f"/api/admin/exercises/{ex.uuid}", headers=headers)).status_code == 204
    listing = await client.get(f"/api/admin/users/{target.id}/exercises", headers=headers)
    assert listing.json()["total"] == 0


async def test_admin_delete_missing_exercise_404(app, client, session):
    headers, _ = await _token_for(app, client, session, "admin@x.com", RoleEnum.ADMIN)
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.delete(f"/api/admin/exercises/{missing}", headers=headers)).status_code == 404


async def test_dictionary_import_returns_task_id_and_status_is_admin_only(app, client, session, monkeypatch):
    import app.routers.admin as admin_router

    # Avoid touching the real DB / Celery: stub the scheduler + status.
    monkeypatch.setattr(admin_router, "schedule_dictionary_import", lambda *a, **k: "task-123")
    headers, _ = await _token_for(app, client, session, "adm-imp@x.com", RoleEnum.ADMIN)

    resp = await client.post(
        "/api/admin/dictionary/import",
        json={"source_language": "en", "target_language": "uk", "raw_text": "able\tздатний\nrun\tбігти"},
        headers=headers,
    )
    assert resp.status_code == 202
    assert resp.json()["queued"] == 2 and resp.json()["task_id"] == "task-123"

    monkeypatch.setattr(admin_router, "import_task_status", lambda tid: {"status": "done", "created": 2, "updated": 0})
    ok = await client.get("/api/admin/dictionary/import/task-123", headers=headers)
    assert ok.status_code == 200 and ok.json() == {"status": "done", "created": 2, "updated": 0}

    plain, _ = await _token_for(app, client, session, "plain-imp@x.com", RoleEnum.USER)
    assert (await client.get("/api/admin/dictionary/import/task-123", headers=plain)).status_code == 403
