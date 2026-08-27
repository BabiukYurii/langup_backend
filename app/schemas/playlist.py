from typing import Literal

from pydantic import BaseModel, Field


class PlaylistTrackOut(BaseModel):
    # One track from a playlist. No audio or lyrics — just what identifies the
    # song so lyrics can be looked up later by title + artist.
    title: str
    artist: str
    spotify_id: str | None = None  # track id, when the embed exposes it


class PlaylistPreviewRequest(BaseModel):
    # A public Spotify playlist link or URI.
    url: str = Field(min_length=1, max_length=512)


class PlaylistPreviewOut(BaseModel):
    name: str | None
    # Tracks we will actually process (already capped at PLAYLIST_MAX_TRACKS).
    tracks: list[PlaylistTrackOut]
    # How many tracks the playlist really has (before the cap).
    total: int
    # True when total > cap, so the client can warn that some tracks were skipped.
    truncated: bool
    # How many tracks we process at most (the cap), for the warning message.
    limit: int


# --- lyrics analysis (green = known, red = unknown, plain = junk/punctuation) ---


class AnalyzedToken(BaseModel):
    # One chunk of a lyric line. `status`:
    #   known    -> mastered word (render green)
    #   learning -> in the user's vocabulary but not mastered yet (render amber)
    #   unknown  -> a real word they don't have yet (render red, clickable)
    #   skip     -> stopword / punctuation / whitespace (render plain)
    surface: str
    lemma: str | None = None
    status: Literal["known", "learning", "unknown", "skip"]


class AnalyzedLine(BaseModel):
    tokens: list[AnalyzedToken]


class UnknownWord(BaseModel):
    lemma: str
    example: str  # the line the word first appeared in (context for translation)
    translation: str | None = None  # filled by the AI step, in the song's context


class AnalyzedLyrics(BaseModel):
    language: str
    lines: list[AnalyzedLine]
    unknown: list[UnknownWord]


class SongAnalyzeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    artist: str = Field(default="", max_length=256)


class SongTranslateRequest(BaseModel):
    lemma: str = Field(min_length=1, max_length=128)
    line: str = Field(default="", max_length=512)  # the song line, for context
    language: str = Field(min_length=2, max_length=8)


class SongTranslateOut(BaseModel):
    lemma: str
    translation: str | None


class SongAddWordRequest(BaseModel):
    lemma: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=2, max_length=8)
    # True = "I already know this word" (mark mastered, no exercises).
    # False = "add to learning" (new word; exercises get generated).
    known: bool = False


class SongAddWordOut(BaseModel):
    added: bool  # False when the word was already in the dictionary
    known: bool
