from app.repositories.word import WordRepository

NEW_WORD = {
    "lemma": "serendipity",
    "language": "en",
    "part_of_speech": "NOUN",
    "phonetic": "ˌsɛrənˈdɪpɪti",
    "definitions": [{"sense": "a fortunate accident", "translation": "випадкова удача"}],
    "frequency_rank": 25000,
    "base_difficulty": 7.5,
}


# ---------------- endpoint tests ----------------


async def test_create_word(client):
    resp = await client.post("/api/words", json=NEW_WORD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["lemma"] == "serendipity"
    assert body["language"] == "en"
    assert body["part_of_speech"] == "NOUN"
    assert body["base_difficulty"] == 7.5
    assert "uuid" in body


async def test_create_duplicate_lemma_language_conflicts(client):
    await client.post("/api/words", json=NEW_WORD)
    resp = await client.post("/api/words", json=NEW_WORD)
    assert resp.status_code == 409


async def test_same_lemma_different_language_allowed(client):
    await client.post("/api/words", json=NEW_WORD)
    resp = await client.post("/api/words", json={**NEW_WORD, "language": "de"})
    assert resp.status_code == 201


async def test_get_word(client):
    created = (await client.post("/api/words", json=NEW_WORD)).json()
    resp = await client.get(f"/api/words/{created['uuid']}")
    assert resp.status_code == 200
    assert resp.json()["lemma"] == "serendipity"


async def test_get_missing_word_404(client):
    resp = await client.get("/api/words/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_list_and_search_words(client):
    for lemma in ["apple", "apricot", "banana"]:
        await client.post("/api/words", json={**NEW_WORD, "lemma": lemma})
    await client.post("/api/words", json={**NEW_WORD, "lemma": "apfel", "language": "de"})

    # language filter
    resp = await client.get("/api/words", params={"language": "en"})
    assert resp.json()["total"] == 3

    # prefix search within a language
    resp = await client.get("/api/words", params={"language": "en", "query": "ap"})
    lemmas = sorted(w["lemma"] for w in resp.json()["items"])
    assert lemmas == ["apple", "apricot"]


async def test_update_word(client):
    created = (await client.post("/api/words", json=NEW_WORD)).json()
    resp = await client.patch(f"/api/words/{created['uuid']}", json={"base_difficulty": 3.0})
    assert resp.status_code == 200
    assert resp.json()["base_difficulty"] == 3.0


async def test_delete_word(client):
    created = (await client.post("/api/words", json=NEW_WORD)).json()
    assert (await client.delete(f"/api/words/{created['uuid']}")).status_code == 204
    assert (await client.get(f"/api/words/{created['uuid']}")).status_code == 404


async def test_invalid_base_difficulty_422(client):
    resp = await client.post("/api/words", json={**NEW_WORD, "base_difficulty": 99})
    assert resp.status_code == 422


# ---------------- repository test ----------------


async def test_repository_get_by_lemma_language(session):
    repo = WordRepository(session)
    await repo.create_one({"lemma": "house", "language": "en"})
    found = await repo.get_by_lemma_language("house", "en")
    assert found is not None and found.lemma == "house"
    assert await repo.get_by_lemma_language("house", "de") is None
