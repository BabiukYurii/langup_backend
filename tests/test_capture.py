from app.services.auth.oauth_google import get_google_verifier

PROFILE = {"sub": "cap-sub-1", "email": "cap@gmail.com", "email_verified": True, "name": "Cap"}


async def _login(app, client, native_language: str | None = "uk") -> dict:
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    resp = await client.post("/api/auth/google", json={"id_token": "fake"})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Capturing now requires a native language; set it unless a test wants the
    # bare, just-created account (to exercise the guard).
    if native_language:
        me = (await client.get("/api/auth/me", headers=headers)).json()
        await client.patch(f"/api/users/{me['id']}", json={"native_language": native_language}, headers=headers)
    return headers


async def test_capture_requires_auth(client):
    resp = await client.post("/api/vocabulary", json={"word": "hello", "language": "en"})
    assert resp.status_code == 401


async def test_capture_requires_native_language(app, client):
    # A brand-new account has no native language yet: saving is refused with a
    # marker the client uses to prompt for the language.
    headers = await _login(app, client, native_language=None)
    resp = await client.post("/api/vocabulary", json={"word": "hello", "language": "en"}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "native_language_required"


async def test_capture_allowed_after_setting_native_language(app, client):
    headers = await _login(app, client)  # default sets native_language
    resp = await client.post("/api/vocabulary", json={"word": "hello", "language": "en"}, headers=headers)
    assert resp.status_code == 201


async def test_capture_sets_learning_language_once(app, client):
    # "I'm learning" starts empty and is filled from the first captured word.
    headers = await _login(app, client)
    assert (await client.get("/api/auth/me", headers=headers)).json()["target_language"] is None
    await client.post("/api/vocabulary", json={"word": "hello", "language": "en"}, headers=headers)
    assert (await client.get("/api/auth/me", headers=headers)).json()["target_language"] == "en"
    # A later capture in another language must not overwrite the choice.
    await client.post("/api/vocabulary", json={"word": "bonjour", "language": "fr"}, headers=headers)
    assert (await client.get("/api/auth/me", headers=headers)).json()["target_language"] == "en"


async def test_capture_creates_personal_word(app, client):
    headers = await _login(app, client)
    resp = await client.post(
        "/api/vocabulary",
        json={
            "word": "serendipity",
            "language": "en",
            "sentence": "What a serendipity to meet you.",
            "source_url": "https://example.com/article",
            "source_title": "Article",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["lemma"] == "serendipity"
    assert body["mastery_level"] == "NEW"
    assert "uuid" in body

    listing = await client.get("/api/vocabulary", headers=headers)
    assert listing.json()["total"] == 1


async def test_capture_lemmatizes_the_word(app, client):
    headers = await _login(app, client)
    resp = await client.post(
        "/api/vocabulary",
        json={"word": "Occurs", "language": "en", "sentence": "It occurs at night."},
        headers=headers,
    )
    assert resp.json()["lemma"] == "occur"  # dictionary form, lowercased


async def test_capture_inflections_share_one_word(app, client):
    headers = await _login(app, client)
    await client.post("/api/vocabulary", json={"word": "demands", "language": "en"}, headers=headers)
    await client.post("/api/vocabulary", json={"word": "demanded", "language": "en"}, headers=headers)

    listing = await client.get("/api/vocabulary", headers=headers)
    assert listing.json()["total"] == 1  # both inflections -> lemma "demand"


async def test_capture_is_idempotent_per_word(app, client):
    headers = await _login(app, client)
    payload = {"word": "apple", "language": "en"}
    await client.post("/api/vocabulary", json=payload, headers=headers)
    await client.post("/api/vocabulary", json=payload, headers=headers)

    listing = await client.get("/api/vocabulary", headers=headers)
    assert listing.json()["total"] == 1  # same word -> one vocabulary entry


async def test_vocabulary_is_per_user(app, client):
    # user A saves a word
    headers_a = await _login(app, client)
    await client.post("/api/vocabulary", json={"word": "alpha", "language": "en"}, headers=headers_a)

    # user B (different Google account) sees an empty vocabulary
    other = {"sub": "cap-sub-2", "email": "other@gmail.com", "email_verified": True, "name": "Other"}
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: other
    tok_b = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {tok_b}"}

    listing_b = await client.get("/api/vocabulary", headers=headers_b)
    assert listing_b.json()["total"] == 0


async def test_vocabulary_search(app, client):
    headers = await _login(app, client)
    for word in ["apple", "apricot", "banana"]:
        await client.post("/api/vocabulary", json={"word": word, "language": "en"}, headers=headers)

    resp = await client.get("/api/vocabulary", params={"query": "ap"}, headers=headers)
    lemmas = sorted(item["lemma"] for item in resp.json()["items"])
    assert lemmas == ["apple", "apricot"]
