import pytest

from app.models import Word
from app.repositories.word import WordRepository
from app.schemas.dictionary import DictionaryImportRequest
from app.services.vocabulary.dictionary_service import DictionaryImportService

# --- parsing ---------------------------------------------------------------


def test_parse_detects_separators():
    raw = "occurs\tстається\ndemand - вимога\nrun,бігти\n# a comment\n\nprovide = надавати"
    entries = DictionaryImportService.parse(DictionaryImportRequest(source_language="en", raw_text=raw))
    pairs = {(e.word, e.translation) for e in entries}
    assert pairs == {
        ("occurs", "стається"),
        ("demand", "вимога"),
        ("run", "бігти"),
        ("provide", "надавати"),
    }


def test_parse_skips_unparseable_lines():
    entries = DictionaryImportService.parse(
        DictionaryImportRequest(source_language="en", raw_text="justoneword\nword\tok")
    )
    assert [(e.word, e.translation) for e in entries] == [("word", "ok")]


def test_request_requires_a_source():
    with pytest.raises(ValueError):
        DictionaryImportRequest(source_language="en")


# --- import ----------------------------------------------------------------


async def _import(session, raw, source="en", target="uk"):
    req = DictionaryImportRequest(source_language=source, target_language=target, raw_text=raw)
    entries = DictionaryImportService.parse(req)
    return await DictionaryImportService(session).import_entries(source, target, entries)


async def test_import_creates_lemmatized_words(session):
    # "Occurs" and "Demands" lemmatize to occur/demand.
    res = await _import(session, "Occurs\tстається\nDemands\tвимоги")
    assert res == {"created": 2, "updated": 0}
    rows, _ = await WordRepository(session).search(limit=100, language="en")
    got = {w.lemma: w.definitions for w in rows}
    assert got["occur"] == [{"lang": "uk", "translation": "стається"}]
    assert got["demand"] == [{"lang": "uk", "translation": "вимоги"}]


async def test_import_merges_translation_into_existing_word(session):
    session.add(Word(lemma="occur", language="en", definitions=[{"lang": "pl", "translation": "wystąpić"}]))
    await session.flush()

    res = await _import(session, "occur\tстається")
    assert res == {"created": 0, "updated": 1}
    word = await WordRepository(session).get_by_lemma_language("occur", "en")
    # keeps the Polish sense, adds the Ukrainian one
    assert {d["lang"] for d in word.definitions} == {"pl", "uk"}


async def test_import_dedupes_within_a_batch(session):
    res = await _import(session, "occurs\tперший\noccur\tостанній")
    assert res == {"created": 1, "updated": 0}  # both map to lemma "occur"
    word = await WordRepository(session).get_by_lemma_language("occur", "en")
    assert word.definitions == [{"lang": "uk", "translation": "останній"}]  # later line wins


# --- LLM normalization -----------------------------------------------------


class _FakeAI:
    """Stands in for the AI gateway: returns a fixed JSON object per chunk."""

    def __init__(self, content: str):
        self._content = content
        self.calls = 0

    async def chat_json(self, system, user, temperature=0.7):
        self.calls += 1
        return {"content": self._content, "model": "fake"}


async def test_normalize_via_llm_builds_entries(session):
    ai = _FakeAI(
        '{"entries": [{"word": "occur", "translation": "стається"}, {"word": "demand", "translation": "вимога"}]}'
    )
    service = DictionaryImportService(session)
    entries = await service.normalize_via_llm("en", "uk", "occurs... стається\ndemand — вимога", ai)
    assert [(e.word, e.translation) for e in entries] == [("occur", "стається"), ("demand", "вимога")]
    assert ai.calls == 1


async def test_normalize_then_import_upserts(session):
    ai = _FakeAI('{"entries": [{"word": "Occurs", "translation": "стається"}]}')
    service = DictionaryImportService(session)
    entries = await service.normalize_via_llm("en", "uk", "junk line occurs = стається", ai)
    res = await service.import_entries("en", "uk", entries)
    assert res == {"created": 1, "updated": 0}
    word = await WordRepository(session).get_by_lemma_language("occur", "en")  # lemmatized
    assert word.definitions == [{"lang": "uk", "translation": "стається"}]


async def test_normalize_skips_bad_chunk(session):
    ai = _FakeAI("not json at all")
    service = DictionaryImportService(session)
    entries = await service.normalize_via_llm("en", "uk", "a\nb", ai)
    assert entries == []  # bad LLM output is skipped, not raised


# --- endpoint --------------------------------------------------------------


async def test_import_endpoint_requires_admin(app, client):
    await client.post("/api/users", json={"email": "plain@x.com", "password": "supersecret123"})
    tok = (await client.post("/api/auth/login", json={"email": "plain@x.com", "password": "supersecret123"})).json()[
        "access_token"
    ]
    resp = await client.post(
        "/api/admin/dictionary/import",
        json={"source_language": "en", "raw_text": "occur\tстається"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403


async def test_import_endpoint_queues_and_imports(app, client, session):
    from app.enums.user import RoleEnum
    from app.repositories.user import UserRepository

    await client.post("/api/users", json={"email": "adm@x.com", "password": "supersecret123"})
    user = await UserRepository(session).get_by_email("adm@x.com")
    await UserRepository(session).update_one(user, {"role": RoleEnum.ADMIN.value})
    tok = (await client.post("/api/auth/login", json={"email": "adm@x.com", "password": "supersecret123"})).json()[
        "access_token"
    ]

    resp = await client.post(
        "/api/admin/dictionary/import",
        json={"source_language": "en", "target_language": "uk", "raw_text": "occur\tстається\ndemand\tвимога"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 202
    assert resp.json()["queued"] == 2
    # The actual upsert runs in a background session that bypasses the test DB
    # (see conftest); import correctness is covered by the service tests above.


async def test_import_endpoint_normalize_mode_queues(app, client, session):
    from app.enums.user import RoleEnum
    from app.repositories.user import UserRepository

    await client.post("/api/users", json={"email": "adm2@x.com", "password": "supersecret123"})
    user = await UserRepository(session).get_by_email("adm2@x.com")
    await UserRepository(session).update_one(user, {"role": RoleEnum.ADMIN.value})
    tok = (await client.post("/api/auth/login", json={"email": "adm2@x.com", "password": "supersecret123"})).json()[
        "access_token"
    ]

    # normalize=True counts non-empty, non-comment lines; the LLM runs in the bg.
    resp = await client.post(
        "/api/admin/dictionary/import",
        json={
            "source_language": "en",
            "target_language": "uk",
            "normalize": True,
            "raw_text": "messy 1\n# c\nmessy 2\n",
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 202
    assert resp.json()["queued"] == 2
