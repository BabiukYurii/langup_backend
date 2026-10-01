"""One pasted song, straight to the front of the queue.

The same field takes a playlist link or a single track link. A track is saved
inline — somebody who pasted one song means to read that song now, not poll a
task — and it outranks every playlist track for warming.
"""

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exc import BadRequestException
from app.models import Playlist, PlaylistSong, Song, User
from app.services.songs import import_service
from app.services.songs.import_service import SINGLES_MARKER, run_track_import
from app.services.songs.warm_scheduler import next_candidate
from app.services.spotify import playlist_parser
from app.services.spotify.playlist_parser import extract_track_id, fetch_track, link_kind

# The link the feature was asked for, query string and all.
TRACK_URL = "https://open.spotify.com/track/0OZQ0HLug7pmpqYXXe7aYp?si=KNtzH07MSSuYUGkijuAqvA&utm_source=copy-link"
PLAYLIST_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc123"


def _embed_html(title="Pimpin' - S.L.A.B.ed", artists=("Trae Tha Truth",)) -> str:
    """The shape a track's embed page really has — captured from Spotify.

    Note what it does NOT have: a trackList, and a subtitle. Both are there for
    a playlist, which is why a track needed its own reader.
    """
    payload = {
        "props": {
            "pageProps": {
                "state": {
                    "data": {
                        "entity": {
                            "type": "track",
                            "title": title,
                            "name": title,
                            "subtitle": None,
                            "uri": "spotify:track:0OZQ0HLug7pmpqYXXe7aYp",
                            "artists": [{"name": a, "uri": f"spotify:artist:{i}"} for i, a in enumerate(artists)],
                        }
                    }
                }
            }
        }
    }
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'


@pytest.fixture
def spotify(monkeypatch):
    """Answer the embed fetch without going to Spotify."""

    async def fake_fetch(url, what):
        return _embed_html()

    monkeypatch.setattr(playlist_parser, "_fetch_embed", fake_fetch)


# --- telling the two links apart -------------------------------------------


def test_a_track_link_is_recognised():
    assert link_kind(TRACK_URL) == "track"
    assert extract_track_id(TRACK_URL) == "0OZQ0HLug7pmpqYXXe7aYp"


def test_a_playlist_link_still_reads_as_a_playlist():
    """The `si` parameter is 22 base62 characters too, so the id patterns have
    to key off what precedes them rather than the shape alone."""
    assert link_kind(PLAYLIST_URL) == "playlist"


@pytest.mark.parametrize(
    "url", ["spotify:track:0OZQ0HLug7pmpqYXXe7aYp", "open.spotify.com/embed/track/0OZQ0HLug7pmpqYXXe7aYp"]
)
def test_the_other_track_link_shapes(url):
    assert link_kind(url) == "track"


@pytest.mark.parametrize(
    "url", ["", "https://example.com/song", "https://open.spotify.com/album/0OZQ0HLug7pmpqYXXe7aYp"]
)
def test_anything_else_is_a_readable_refusal(url):
    with pytest.raises(BadRequestException):
        link_kind(url)


# --- reading the track -----------------------------------------------------


async def test_the_artist_comes_from_the_artists_list(spotify):
    """A track entity has no subtitle; the performer is in `artists`."""
    track = await fetch_track(TRACK_URL)

    assert track.title == "Pimpin' - S.L.A.B.ed"
    assert track.artist == "Trae Tha Truth"
    assert track.spotify_id == "0OZQ0HLug7pmpqYXXe7aYp"


async def test_several_artists_are_joined(monkeypatch):
    async def fake_fetch(url, what):
        return _embed_html(artists=("Queen", "David Bowie"))

    monkeypatch.setattr(playlist_parser, "_fetch_embed", fake_fetch)
    assert (await fetch_track(TRACK_URL)).artist == "Queen, David Bowie"


# --- saving it -------------------------------------------------------------


async def _user(session, email: str) -> User:
    user = User(email=email, hashed_password="x", native_language="uk")
    session.add(user)
    await session.flush()
    return user


@pytest.fixture(autouse=True)
def _no_lyrics(monkeypatch):
    """Analysis is cached on the shared Song row and not what these test."""

    async def nothing(session, song):
        return song

    monkeypatch.setattr(import_service, "analyze_song", nothing)


async def test_a_pasted_track_lands_in_a_singles_playlist(sessionmaker, spotify):
    async with sessionmaker() as session:
        user = await _user(session, "single@x.io")
        result = await run_track_import(session, user.id, TRACK_URL)

        playlist = (await session.execute(select(Playlist).where(Playlist.user_id == user.id))).scalar_one()
        assert playlist.spotify_id == SINGLES_MARKER
        assert str(playlist.uuid) == result["playlist_uuid"]
        assert result["title"] == "Pimpin' - S.L.A.B.ed"

        song = (await session.execute(select(Song))).scalar_one()
        assert str(song.uuid) == result["song_uuid"]


async def test_a_second_single_joins_the_same_playlist(sessionmaker, monkeypatch):
    async with sessionmaker() as session:
        user = await _user(session, "two@x.io")

        async def first(url, what):
            return _embed_html(title="One")

        monkeypatch.setattr(playlist_parser, "_fetch_embed", first)
        await run_track_import(session, user.id, TRACK_URL)

        async def second(url, what):
            return _embed_html(title="Two")

        monkeypatch.setattr(playlist_parser, "_fetch_embed", second)
        await run_track_import(session, user.id, TRACK_URL)

        playlists = (await session.execute(select(Playlist).where(Playlist.user_id == user.id))).scalars().all()
        links = (await session.execute(select(PlaylistSong))).scalars().all()
        assert len(playlists) == 1  # one bucket, not one playlist per song
        assert len(links) == 2


async def test_re_pasting_the_same_track_moves_it_back_to_the_front(sessionmaker, spotify):
    async with sessionmaker() as session:
        user = await _user(session, "again@x.io")
        await run_track_import(session, user.id, TRACK_URL)
        link = (await session.execute(select(PlaylistSong))).scalar_one()
        await session.execute(PlaylistSong.__table__.update().where(PlaylistSong.uuid == link.uuid).values(priority=1))
        await session.flush()

        await run_track_import(session, user.id, TRACK_URL)

        links = (await session.execute(select(PlaylistSong))).scalars().all()
        assert len(links) == 1  # not duplicated
        await session.refresh(links[0])
        assert links[0].priority > 1  # bumped


# --- and it is warmed first ------------------------------------------------


async def _playlist_with_song(session, user: User, title: str, position: int = 0) -> Song:
    song = Song(
        title=title,
        artist="A",
        match_key=f"{uuid4().hex}|a",
        language="en",
        lyrics_found=True,
        lemmas=["x"],
    )
    session.add(song)
    await session.flush()
    playlist = Playlist(user_id=user.id, spotify_id=uuid4().hex[:8], name="P", status="ready")
    session.add(playlist)
    await session.flush()
    session.add(PlaylistSong(playlist_uuid=playlist.uuid, song_uuid=song.uuid, position=position))
    await session.flush()
    return song


async def test_a_pasted_single_is_warmed_before_any_playlist_track(sessionmaker, spotify):
    """The point of the priority: a playlist track at position 0 normally wins,
    and a pasted song has to beat it."""
    async with sessionmaker() as session:
        user = await _user(session, "priority@x.io")
        await _playlist_with_song(session, user, "From A Playlist")

        result = await run_track_import(session, user.id, TRACK_URL)
        # The imported song needs lyrics for the scheduler to consider it.
        await session.execute(
            Song.__table__.update()
            .where(Song.uuid == uuid4().__class__(result["song_uuid"]))
            .values(language="en", lyrics_found=True, lemmas=["x"])
        )
        await session.commit()

        candidate = await next_candidate(session)
        assert candidate is not None
        assert str(candidate.song_uuid) == result["song_uuid"]


async def test_playlist_tracks_keep_their_old_order_among_themselves(sessionmaker):
    """Every playlist row sits at priority 0, so position still decides."""
    async with sessionmaker() as session:
        user = await _user(session, "unchanged@x.io")
        first = await _playlist_with_song(session, user, "First", position=0)
        await _playlist_with_song(session, user, "Second", position=1)
        await session.commit()

        candidate = await next_candidate(session)
        assert candidate is not None
        assert candidate.song_uuid == first.uuid


async def test_each_single_outranks_the_one_before_it(sessionmaker, monkeypatch):
    """Ordinal, not clock-based. Seconds cannot order two tracks pasted inside
    the same second, and that is exactly how somebody adds a few songs at once."""
    async with sessionmaker() as session:
        user = await _user(session, "order@x.io")

        for title in ("One", "Two", "Three"):

            async def fake(url, what, title=title):
                return _embed_html(title=title)

            monkeypatch.setattr(playlist_parser, "_fetch_embed", fake)
            await run_track_import(session, user.id, TRACK_URL)

        rows = (await session.execute(select(PlaylistSong))).scalars().all()
        assert sorted(r.priority for r in rows) == [1, 2, 3]


async def test_a_playlist_track_is_never_given_a_priority(sessionmaker):
    """Playlist rows stay at zero, which is what leaves their fairness rule —
    every first song before any second song — exactly as it was."""
    async with sessionmaker() as session:
        user = await _user(session, "zero@x.io")
        await _playlist_with_song(session, user, "Ordinary")

        row = (await session.execute(select(PlaylistSong))).scalar_one()
        assert row.priority == 0
