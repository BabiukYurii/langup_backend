from app.services.auth.oauth_google import get_google_verifier

PROFILE = {"sub": "rev-sub-1", "email": "rev@gmail.com", "email_verified": True, "name": "Rev"}


async def _login(app, client) -> dict:
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    token = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _capture(client, headers, word) -> str:
    resp = await client.post("/api/vocabulary", json={"word": word, "language": "en"}, headers=headers)
    return resp.json()["uuid"]


async def test_review_requires_auth(client):
    assert (await client.get("/api/review/next")).status_code == 401
    assert (await client.post("/api/review/x", json={"quality": 5})).status_code in (401, 422)


async def test_new_word_is_due(app, client):
    headers = await _login(app, client)
    uuid = await _capture(client, headers, "serendipity")

    due = await client.get("/api/review/next", headers=headers)
    assert due.status_code == 200
    assert any(item["uuid"] == uuid for item in due.json())


async def test_first_correct_review_schedules_next_day(app, client):
    headers = await _login(app, client)
    uuid = await _capture(client, headers, "apple")

    resp = await client.post(f"/api/review/{uuid}", json={"quality": 5}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["repetitions"] == 1
    assert body["interval_days"] == 1
    assert body["due_at"] is not None

    # once scheduled for tomorrow it is no longer in the "due now" queue
    due = await client.get("/api/review/next", headers=headers)
    assert all(item["uuid"] != uuid for item in due.json())


async def test_second_correct_review_grows_interval(app, client):
    headers = await _login(app, client)
    uuid = await _capture(client, headers, "banana")

    await client.post(f"/api/review/{uuid}", json={"quality": 5}, headers=headers)
    body = (await client.post(f"/api/review/{uuid}", json={"quality": 5}, headers=headers)).json()
    assert body["repetitions"] == 2
    assert body["interval_days"] == 6
    assert body["mastery_level"] == "REVIEW"


async def test_failed_review_resets(app, client):
    headers = await _login(app, client)
    uuid = await _capture(client, headers, "cherry")

    await client.post(f"/api/review/{uuid}", json={"quality": 5}, headers=headers)  # reps -> 1
    body = (await client.post(f"/api/review/{uuid}", json={"quality": 1}, headers=headers)).json()
    assert body["repetitions"] == 0
    assert body["interval_days"] == 1
    assert body["mastery_level"] == "LEARNING"


async def test_review_unknown_word_404(app, client):
    headers = await _login(app, client)
    resp = await client.post(
        "/api/review/00000000-0000-0000-0000-000000000000",
        json={"quality": 5},
        headers=headers,
    )
    assert resp.status_code == 404
