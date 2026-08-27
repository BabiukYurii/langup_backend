import pytest

from app.services.songs import store
from app.services.songs.store import analyze_song, get_or_create_song, make_match_key

pytestmark = pytest.mark.asyncio


async def test_match_key_normalizes():
    assert make_match_key("  The  Kid ", "Arrested Youth") == "the kid|arrested youth"
    assert make_match_key("Song", "A") == make_match_key("song", "a")


async def test_get_or_create_song_dedups(session):
    a = await get_or_create_song(session, "Undead", "Hollywood Undead")
    b = await get_or_create_song(session, "undead", "hollywood undead")  # same after normalize
    assert a.uuid == b.uuid


async def test_analyze_song_caches_language_and_lemmas(session, monkeypatch):
    async def fake(title, artist):
        return "The cat and the dog run in the park every morning together"

    monkeypatch.setattr(store, "fetch_lyrics", fake)
    song = await get_or_create_song(session, "Song", "Artist")
    analyzed = await analyze_song(session, song)
    assert analyzed.lyrics_found is True
    assert analyzed.language == "en"
    assert "cat" in analyzed.lemmas and "dog" in analyzed.lemmas
    assert "the" not in analyzed.lemmas  # stopword dropped
    assert analyzed.analyzed_at is not None

    # second call is a no-op (already analysed) even if lyrics would change
    monkeypatch.setattr(store, "fetch_lyrics", lambda t, a: (_ for _ in ()).throw(AssertionError("refetched")))
    again = await analyze_song(session, analyzed)
    assert again.language == "en"


async def test_analyze_song_without_lyrics(session, monkeypatch):
    async def none(title, artist):
        return None

    monkeypatch.setattr(store, "fetch_lyrics", none)
    song = await get_or_create_song(session, "Obscure", "Nobody")
    analyzed = await analyze_song(session, song)
    assert analyzed.lyrics_found is False
    assert analyzed.analyzed_at is not None
