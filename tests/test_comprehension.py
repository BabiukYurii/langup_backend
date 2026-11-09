"""How much of a song the learner already understands.

The number nobody else can show them: it is built from their own vocabulary
against the songs they chose, and it climbs on its own every time they save a
word that happens to appear in one.
"""

from uuid import uuid4

import pytest

from app.models import Playlist, PlaylistSong, Song, User, UserWord, Word
from app.services.songs.service import comprehension_percent

# --- the arithmetic --------------------------------------------------------


@pytest.mark.parametrize(
    "total, unknown, expected",
    [
        (10, 0, 100),
        (10, 10, 0),
        (10, 5, 50),
        (4, 1, 75),
        (3, 1, 66),  # rounded DOWN
    ],
)
def test_the_percentage(total, unknown, expected):
    assert comprehension_percent(total, unknown) == expected


def test_rounding_never_claims_a_finished_song():
    """199 of 200 is 99, not 100: the last word still matters."""
    assert comprehension_percent(200, 1) == 99


@pytest.mark.parametrize("total, unknown", [(None, None), (0, 0), (10, None)])
def test_nothing_to_measure_is_none_not_zero(total, unknown):
    """An unanalysed song is unknown, not fully misunderstood — 0% would read
    as a verdict the data cannot support."""
    assert comprehension_percent(total, unknown) is None


# --- through the playlist ---------------------------------------------------


async def _learner_with_song(session, lemmas: list[str], known: list[str]) -> tuple[User, Playlist]:
    user = User(email=f"{uuid4().hex[:8]}@x.io", hashed_password="x", native_language="uk", target_language="en")
    session.add(user)
    await session.flush()

    for lemma in known:
        word = Word(lemma=lemma, language="en")
        session.add(word)
        await session.flush()
        session.add(UserWord(user_id=user.id, word_uuid=word.uuid))

    song = Song(
        title="Song",
        artist="A",
        match_key=uuid4().hex,
        language="en",
        lyrics_found=True,
        lemmas=lemmas,
        analyzed_at=None,
    )
    session.add(song)
    await session.flush()
    playlist = Playlist(user_id=user.id, spotify_id=uuid4().hex[:8], name="P", status="ready")
    session.add(playlist)
    await session.flush()
    session.add(PlaylistSong(playlist_uuid=playlist.uuid, song_uuid=song.uuid, position=0))
    await session.commit()
    return user, playlist


async def _detail(session, user: User, playlist: Playlist):
    from app.services.songs.service import SongService

    class _NoGen:
        pass

    return await SongService(session, _NoGen()).playlist_detail(user.id, playlist.uuid)


async def test_a_song_reports_what_share_is_already_known(sessionmaker):
    async with sessionmaker() as session:
        user, playlist = await _learner_with_song(session, lemmas=["one", "two", "three", "four"], known=["one", "two"])
        detail = await _detail(session, user, playlist)

        song = detail.songs[0]
        assert song.total_lemmas == 4
        assert song.unknown_count == 2
        assert song.comprehension == 50


async def test_saving_a_word_from_the_song_raises_it(sessionmaker):
    """The whole point: progress moves without practising the song itself."""
    async with sessionmaker() as session:
        user, playlist = await _learner_with_song(session, lemmas=["a", "b", "c", "d"], known=["a"])
        assert (await _detail(session, user, playlist)).songs[0].comprehension == 25

        word = Word(lemma="b", language="en")
        session.add(word)
        await session.flush()
        session.add(UserWord(user_id=user.id, word_uuid=word.uuid))
        await session.commit()

        assert (await _detail(session, user, playlist)).songs[0].comprehension == 50


async def test_an_unanalysed_song_reports_nothing(sessionmaker):
    async with sessionmaker() as session:
        user, playlist = await _learner_with_song(session, lemmas=["x"], known=[])
        song_row = (await session.execute(__import__("sqlalchemy").select(Song))).scalar_one()
        song_row.lemmas = None
        await session.commit()

        song = (await _detail(session, user, playlist)).songs[0]
        assert song.comprehension is None
        assert song.total_lemmas is None


async def test_the_playlist_figure_is_weighted_by_length(sessionmaker):
    """A mean of percentages would let a two-line interlude count as much as a
    verse-heavy song; the playlist number is over the words themselves."""
    async with sessionmaker() as session:
        user, playlist = await _learner_with_song(session, lemmas=["a", "b"], known=["a"])  # 1 of 2

        long_song = Song(
            title="Long",
            artist="A",
            match_key=uuid4().hex,
            language="en",
            lyrics_found=True,
            lemmas=[f"w{i}" for i in range(8)],  # 0 of 8 known
        )
        session.add(long_song)
        await session.flush()
        session.add(PlaylistSong(playlist_uuid=playlist.uuid, song_uuid=long_song.uuid, position=1))
        await session.commit()

        detail = await _detail(session, user, playlist)
        # 1 known of 10 words, not the average of 50% and 0%.
        assert detail.comprehension == 10
