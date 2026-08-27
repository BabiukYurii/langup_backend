"""Persist a shared, user-independent analysis of a song.

We cache the detected language and the set of content lemmas on the Song row —
never the copyrighted lyrics text. A per-user "unknown" count is then just this
set minus the user's vocabulary, computed at read time.
"""

import re
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Song
from app.repositories.playlist import SongRepository
from app.services.lyrics import fetch_lyrics
from app.services.songs.analysis import content_lemmas
from app.services.songs.language import detect_language


def make_match_key(title: str, artist: str) -> str:
    """Normalized "title|artist" key so one song is analysed once for everyone."""
    norm = lambda s: re.sub(r"\s+", " ", (s or "").strip().lower())  # noqa: E731
    return f"{norm(title)}|{norm(artist)}"


async def get_or_create_song(session: AsyncSession, title: str, artist: str, spotify_id: str | None = None) -> Song:
    repo = SongRepository(session)
    key = make_match_key(title, artist)
    song = await repo.get_by_match_key(key)
    if song:
        return song
    return await repo.create_one({"title": title, "artist": artist, "spotify_id": spotify_id, "match_key": key})


async def analyze_song(session: AsyncSession, song: Song) -> Song:
    """Fetch lyrics, detect language, cache content lemmas. Idempotent: an
    already-analysed song is returned untouched (shared across users/playlists)."""
    if song.analyzed_at is not None:
        return song
    repo = SongRepository(session)
    now = datetime.now(UTC).replace(tzinfo=None)
    lyrics = await fetch_lyrics(song.title, song.artist)
    if not lyrics:
        return await repo.update_one(song, {"lyrics_found": False, "analyzed_at": now})
    language = detect_language(lyrics)
    lemmas = content_lemmas(lyrics, language) if language else []
    return await repo.update_one(
        song, {"lyrics_found": True, "language": language, "lemmas": lemmas, "analyzed_at": now}
    )
