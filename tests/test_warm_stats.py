"""Ф5 of the playlist warm-up: making the feature visible, and safe to leave on.

The warmer spends the model at night, where nobody watches. Without a way to
read what it has done, there is no way to tell whether the glosses it leaves are
ever looked at — and no way to notice it has quietly stopped.
"""

from uuid import uuid4

import pytest

from app.celery.tasks import warm_tasks
from app.core import settings
from app.enums.user import RoleEnum
from app.models import Playlist, PlaylistSong, Song, User
from app.repositories.song_warm_state import SongWarmStateRepository
from app.repositories.user import UserRepository
from app.services.songs.warm_scheduler import warm_stats


async def _token_for(client, session, email, role):
    await client.post("/api/users", json={"email": email, "password": "supersecret123"})
    user = await UserRepository(session).get_by_email(email)
    await UserRepository(session).update_one(user, {"role": role.value})
    login = await client.post("/api/auth/login", json={"email": email, "password": "supersecret123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _one_pending_song(session) -> Song:
    user = User(email=f"{uuid4().hex[:8]}@x.io", hashed_password="x", native_language="uk")
    session.add(user)
    await session.flush()
    song = Song(title="Song", artist="A", match_key=f"{uuid4().hex}|a", language="en", lyrics_found=True, lemmas=["x"])
    session.add(song)
    await session.flush()
    playlist = Playlist(user_id=user.id, spotify_id=uuid4().hex[:8], name="P", status="ready")
    session.add(playlist)
    await session.flush()
    session.add(PlaylistSong(playlist_uuid=playlist.uuid, song_uuid=song.uuid, position=0))
    await session.flush()
    return song


# --- the numbers -----------------------------------------------------------


async def test_an_empty_system_reports_nothing_rather_than_failing(sessionmaker):
    async with sessionmaker() as session:
        stats = await warm_stats(session)
    assert stats.pairs_completed == 0
    assert stats.pairs_pending == 0
    assert stats.words_warmed == 0


async def test_pending_counts_what_the_scheduler_would_pick(sessionmaker):
    """The two walk the same joins, so they cannot disagree about what is work."""
    from app.services.songs.warm_scheduler import next_candidate

    async with sessionmaker() as session:
        await _one_pending_song(session)
        await session.commit()

        assert (await warm_stats(session)).pairs_pending == 1
        assert await next_candidate(session) is not None


async def test_finishing_a_song_moves_it_from_pending_to_done(sessionmaker):
    async with sessionmaker() as session:
        song = await _one_pending_song(session)
        await session.commit()

        await SongWarmStateRepository(session).mark_completed(song.uuid, "uk", words_warmed=7)
        stats = await warm_stats(session)

    assert stats.pairs_pending == 0
    assert stats.pairs_completed == 1
    assert stats.words_warmed == 7
    assert stats.last_attempt is not None


# --- the endpoint ----------------------------------------------------------


async def test_warm_progress_is_admin_only(client):
    assert (await client.get("/api/admin/warm")).status_code == 401


async def test_a_plain_user_cannot_read_it(client, session):
    headers = await _token_for(client, session, "plain-warm@x.io", RoleEnum.USER)
    assert (await client.get("/api/admin/warm", headers=headers)).status_code == 403


async def test_an_admin_sees_the_progress(client, session):
    headers = await _token_for(client, session, "admin-warm@x.io", RoleEnum.ADMIN)
    resp = await client.get("/api/admin/warm", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "pairs_completed",
        "pairs_pending",
        "words_warmed",
        "translations_cached",
        "last_attempt",
        "enabled",
    }
    # Reports the switch honestly, so "nothing is happening" is explainable.
    assert body["enabled"] is settings.warm.WARM_ENABLED


# --- the switch ------------------------------------------------------------


async def test_a_tick_does_nothing_while_the_feature_is_off(monkeypatch):
    """Off by default: a deployment with no spare capacity never opts in."""
    monkeypatch.setattr(settings.warm, "WARM_ENABLED", False)
    result = await warm_tasks.run_tick()
    assert result.reason == "disabled"


async def test_a_tick_stands_aside_before_it_even_queries(monkeypatch):
    """The cheapest possible politeness: if a learner is mid-request, do not
    spend a query deciding what we would have warmed."""

    async def busy():
        return True

    monkeypatch.setattr(settings.warm, "WARM_ENABLED", True)
    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", busy)
    result = await warm_tasks.run_tick()
    assert result.reason == "yielded"


def test_beat_hands_out_one_song_at_a_time():
    from app.celery.config import celery_app

    entry = celery_app.conf.beat_schedule["warm-one-playlist-song"]
    assert entry["task"] == "warm.tick"
    # A tick arriving while the last is still running is pointless; it must
    # expire rather than build a backlog.
    assert entry["options"]["expires"] > 0


@pytest.mark.parametrize(
    "setting, minimum",
    [("WARM_RUN_BUDGET_SECONDS", 1), ("WARM_WORDS_PER_RUN", 1), ("WARM_TICK_SECONDS", 1)],
)
def test_every_ceiling_is_actually_set(setting, minimum):
    """A missing cap here means one song could hold the model all night."""
    assert getattr(settings.warm, setting) >= minimum
