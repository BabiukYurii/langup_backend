"""Ф3 of the playlist warm-up: whose song gets warmed next.

The rule under test is fairness: WIDE before deep. Every learner's first song is
prepared before anyone's second one, so nobody ends up with a fully warmed
playlist while the next person has nothing.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models import Playlist, PlaylistSong, Song, User
from app.repositories.song_warm_state import SongWarmStateRepository
from app.services.songs.warm_scheduler import next_candidate, voices_for_song


async def _user(session, email: str, native: str = "uk", preferences: dict | None = None) -> User:
    user = User(email=email, hashed_password="x", native_language=native, preferences=preferences)
    session.add(user)
    await session.flush()
    return user


async def _song(session, title: str, language: str = "en", lyrics_found: bool = True) -> Song:
    song = Song(
        title=title,
        artist="Artist",
        match_key=f"{title}|artist".lower(),
        language=language,
        lyrics_found=lyrics_found,
        lemmas=["one", "two"],
    )
    session.add(song)
    await session.flush()
    return song


async def _playlist(session, user: User, songs: list[Song], status: str = "ready") -> Playlist:
    playlist = Playlist(user_id=user.id, spotify_id=str(uuid4())[:8], name="P", status=status)
    session.add(playlist)
    await session.flush()
    for position, song in enumerate(songs):
        session.add(PlaylistSong(playlist_uuid=playlist.uuid, song_uuid=song.uuid, position=position))
    await session.flush()
    return playlist


# --- fairness --------------------------------------------------------------


async def test_every_first_song_comes_before_any_second_song(sessionmaker):
    """The heart of it: one learner must not take the whole night."""
    async with sessionmaker() as session:
        alice, bob = await _user(session, "a@x.io"), await _user(session, "b@x.io")
        a1, a2 = await _song(session, "A1"), await _song(session, "A2")
        b1, b2 = await _song(session, "B1"), await _song(session, "B2")
        await _playlist(session, alice, [a1, a2])
        await _playlist(session, bob, [b1, b2])
        await session.commit()

        states = SongWarmStateRepository(session)
        picked = []
        for _ in range(4):
            candidate = await next_candidate(session)
            assert candidate is not None
            picked.append(candidate)
            await states.mark_completed(candidate.song_uuid, candidate.target_language)

        # Both first songs are taken before either second song is touched.
        assert [c.position for c in picked] == [0, 0, 1, 1]
        assert {c.title for c in picked[:2]} == {"A1", "B1"}
        assert {c.title for c in picked[2:]} == {"A2", "B2"}


async def test_nothing_left_to_do_is_none_not_an_error(sessionmaker):
    async with sessionmaker() as session:
        assert await next_candidate(session) is None


async def test_a_completed_pair_is_not_picked_again(sessionmaker):
    async with sessionmaker() as session:
        user = await _user(session, "c@x.io")
        song = await _song(session, "Only")
        await _playlist(session, user, [song])
        await session.commit()

        first = await next_candidate(session)
        assert first is not None
        await SongWarmStateRepository(session).mark_completed(song.uuid, "uk")
        assert await next_candidate(session) is None


async def test_a_long_finished_pair_is_eventually_rechecked(sessionmaker):
    """Songs are static, but a re-import or a cache purge should not be permanent."""
    async with sessionmaker() as session:
        user = await _user(session, "d@x.io")
        song = await _song(session, "Old")
        await _playlist(session, user, [song])
        await session.commit()

        states = SongWarmStateRepository(session)
        state = await states.mark_completed(song.uuid, "uk")
        assert await next_candidate(session) is None

        long_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=365)
        await states.update_one(state, {"completed_at": long_ago})
        assert await next_candidate(session) is not None


async def test_a_stubborn_song_does_not_hold_up_the_rotation(sessionmaker):
    """Attempted (not completed) sorts last, so the next tick tries its neighbour."""
    async with sessionmaker() as session:
        user = await _user(session, "e@x.io")
        first, second = await _song(session, "S1"), await _song(session, "S2")
        await _playlist(session, user, [first])
        await _playlist(session, user, [second])
        await session.commit()

        one = await next_candidate(session)
        await SongWarmStateRepository(session).mark_attempted(one.song_uuid, one.target_language)

        two = await next_candidate(session)
        assert two.song_uuid != one.song_uuid


# --- what is out of scope --------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, playlist_status",
    [
        ({"lyrics_found": False}, "ready"),  # nothing to read
        ({"language": None}, "ready"),  # nothing to analyse
        ({}, "parsing"),  # the import is not finished
    ],
)
async def test_songs_with_nothing_to_do_are_skipped(sessionmaker, kwargs, playlist_status):
    async with sessionmaker() as session:
        user = await _user(session, f"f{playlist_status}{kwargs}@x.io")
        song = await _song(session, "Skip", **kwargs)
        await _playlist(session, user, [song], status=playlist_status)
        await session.commit()

        assert await next_candidate(session) is None


async def test_a_song_already_in_the_readers_language_is_skipped(sessionmaker):
    """Nobody needs English glossed into English."""
    async with sessionmaker() as session:
        user = await _user(session, "g@x.io", native="en")
        song = await _song(session, "Same", language="en")
        await _playlist(session, user, [song])
        await session.commit()

        assert await next_candidate(session) is None


# --- voices ----------------------------------------------------------------


async def test_only_voices_someone_actually_chose_are_collected(sessionmaker):
    """Warming a voice nobody selected caches a clip no request will look up."""
    voices = list(__import__("app.core", fromlist=["settings"]).settings.audio.available_voices)
    chosen = voices[0]

    async with sessionmaker() as session:
        listener = await _user(session, "h@x.io", preferences={"tts_voices": {"en": chosen}})
        silent = await _user(session, "i@x.io")  # never touched the setting
        song = await _song(session, "Shared")
        await _playlist(session, listener, [song])
        await _playlist(session, silent, [song])
        await session.commit()

        assert await voices_for_song(session, song.uuid) == [chosen]
