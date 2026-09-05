"""Choosing which song to warm next, fairly.

The rule the whole feature turns on: go WIDE before deep. Round one takes the
first song of every playlist of every learner; only when none of those are left
does round two start on the second songs. Otherwise the learner whose playlist
happens to sort first would be fully warmed while the next one waited for hours.

That ordering needs no cursor. "Which round are we in" is simply the lowest
`position` that still has unwarmed pairs, which the query below reads straight
out of the data — so nothing can drift, and nothing has to be reset when a
learner adds or removes a playlist.

The unit is a (song, target language) pair, not a (song, user) one. A hundred
learners sharing one song and one native language are one job, not a hundred.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.models import Playlist, PlaylistSong, Song, SongWarmState, User

# Older than every real timestamp: lets "never attempted" sort first without
# NULLS FIRST, which the two dialects disagree about.
_NEVER = datetime(1970, 1, 1)


class WarmCandidate(BaseModel):
    """One song to prepare, in one language."""

    song_uuid: UUID
    source_language: str
    target_language: str
    position: int
    title: str
    artist: str


def _target_language():
    """The language a playlist's owner reads translations in."""
    return func.lower(func.coalesce(User.native_language, settings.exercises.EXERCISE_FALLBACK_TRANSLATION_LANGUAGE))


async def next_candidate(session: AsyncSession) -> WarmCandidate | None:
    """The next pair to warm, or None when everything reachable is done."""
    target = _target_language()
    stale_before = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=settings.warm.WARM_RECHECK_DAYS)

    stmt = (
        select(
            PlaylistSong.song_uuid,
            Song.language,
            target.label("target_language"),
            PlaylistSong.position,
            Song.title,
            Song.artist,
        )
        .join(Playlist, Playlist.uuid == PlaylistSong.playlist_uuid)
        .join(User, User.id == Playlist.user_id)
        .join(Song, Song.uuid == PlaylistSong.song_uuid)
        .outerjoin(
            SongWarmState,
            and_(
                SongWarmState.song_uuid == PlaylistSong.song_uuid,
                SongWarmState.target_language == target,
            ),
        )
        # Only songs there is anything to do with: an imported playlist that
        # finished parsing, lyrics that were actually found, a language we know.
        .where(Playlist.status == "ready")
        .where(Song.lyrics_found.is_(True))
        .where(Song.language.isnot(None))
        # Nobody needs English glossed into English.
        .where(func.lower(Song.language) != target)
        .where(or_(SongWarmState.completed_at.is_(None), SongWarmState.completed_at < stale_before))
        .order_by(
            # 1. the round: every first song before any second song
            PlaylistSong.position.asc(),
            # 2. within a round, whatever was left alone longest — so a song
            #    that keeps failing cannot hold the rotation up
            func.coalesce(SongWarmState.attempted_at, _NEVER).asc(),
            # 3. a stable tiebreak, so the choice is reproducible
            PlaylistSong.song_uuid.asc(),
        )
        .limit(1)
    )

    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return WarmCandidate(
        song_uuid=row.song_uuid,
        source_language=row.language,
        target_language=row.target_language,
        position=row.position,
        title=row.title,
        artist=row.artist or "",
    )


async def voices_for_song(session: AsyncSession, song_uuid: UUID) -> list[str]:
    """Every voice actually chosen by someone who has this song.

    Audio is keyed by voice, so warming one nobody selected caches a clip no
    request will ever look up. The learners who never touched the setting are
    covered by the language default, which is added by the caller.
    """
    from app.services.audio.keys import LEGACY_VOICE_PREF_KEY, VOICES_PREF_KEY

    stmt = (
        select(User.preferences, Song.language)
        .join(Playlist, Playlist.user_id == User.id)
        .join(PlaylistSong, PlaylistSong.playlist_uuid == Playlist.uuid)
        .join(Song, Song.uuid == PlaylistSong.song_uuid)
        .where(PlaylistSong.song_uuid == song_uuid)
    )
    available = settings.audio.available_voices
    voices: list[str] = []
    for preferences, language in (await session.execute(stmt)).all():
        prefs = preferences or {}
        chosen = prefs.get(VOICES_PREF_KEY)
        voice = None
        if isinstance(chosen, dict):
            voice = chosen.get((language or "").lower()[:2])
        # Continuity with the first cut, which stored one voice per account.
        voice = voice or prefs.get(LEGACY_VOICE_PREF_KEY)
        if voice in available and voice not in voices:
            voices.append(voice)
    return voices


class WarmStats(BaseModel):
    """Whether the warmer is earning its electricity."""

    pairs_completed: int
    pairs_pending: int
    words_warmed: int
    translations_cached: int
    last_attempt: datetime | None
    enabled: bool


async def warm_stats(session: AsyncSession) -> WarmStats:
    """A count of what has been prepared and what is still queued.

    `pairs_pending` walks the same joins the scheduler picks from, so the two
    can never disagree about what counts as work.
    """
    from app.models import WordTranslation

    completed = await session.scalar(
        select(func.count()).select_from(SongWarmState).where(SongWarmState.completed_at.isnot(None))
    )
    words = await session.scalar(select(func.coalesce(func.sum(SongWarmState.words_warmed), 0)))
    cached = await session.scalar(select(func.count()).select_from(WordTranslation))
    last = await session.scalar(select(func.max(SongWarmState.attempted_at)))

    target = _target_language()
    stale_before = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=settings.warm.WARM_RECHECK_DAYS)
    pending = await session.scalar(
        select(func.count(func.distinct(PlaylistSong.song_uuid)))
        .select_from(PlaylistSong)
        .join(Playlist, Playlist.uuid == PlaylistSong.playlist_uuid)
        .join(User, User.id == Playlist.user_id)
        .join(Song, Song.uuid == PlaylistSong.song_uuid)
        .outerjoin(
            SongWarmState,
            and_(
                SongWarmState.song_uuid == PlaylistSong.song_uuid,
                SongWarmState.target_language == target,
            ),
        )
        .where(Playlist.status == "ready")
        .where(Song.lyrics_found.is_(True))
        .where(Song.language.isnot(None))
        .where(func.lower(Song.language) != target)
        .where(or_(SongWarmState.completed_at.is_(None), SongWarmState.completed_at < stale_before))
    )

    return WarmStats(
        pairs_completed=completed or 0,
        pairs_pending=pending or 0,
        words_warmed=words or 0,
        translations_cached=cached or 0,
        last_attempt=last,
        enabled=settings.warm.WARM_ENABLED,
    )
