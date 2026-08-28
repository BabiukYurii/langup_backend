from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin, UUIDType


class Song(Base, UUIDMixin, TimestampMixin):
    # A shared, user-independent cache of one song's analysis. We store only the
    # detected language and the set of content lemmas (junk/stopwords removed) —
    # NOT the copyrighted lyrics text. Per-user "unknown" counts are derived by
    # diffing `lemmas` against the user's vocabulary at read time.
    #
    # Invalidating this cache after an analysis change: reset the rows
    # (UPDATE songs SET analyzed_at = NULL) — never DELETE FROM songs, which
    # cascades playlist_songs and empties everyone's saved playlists.
    __tablename__ = "songs"
    __table_args__ = (UniqueConstraint("match_key", name="uq_song_match_key"),)

    title = Column(String(256), nullable=False)
    artist = Column(String(256), nullable=False, server_default="")
    spotify_id = Column(String(64), nullable=True)
    # Normalized "title|artist" for cross-user dedup (one analysis per song).
    match_key = Column(String(600), nullable=False, index=True)
    language = Column(String(8), nullable=True, index=True)  # detected lyrics language
    lemmas = Column(JSONType, nullable=True)  # list[str] of content lemmas
    lyrics_found = Column(Boolean, nullable=False, server_default="false")
    analyzed_at = Column(DateTime, nullable=True)


class Playlist(Base, UUIDMixin, TimestampMixin):
    # A Spotify playlist a user imported. Owns its ordered track links.
    __tablename__ = "playlists"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    spotify_id = Column(String(64), nullable=False)
    name = Column(String(256), nullable=True)
    # pending | parsing | ready | failed
    status = Column(String(16), nullable=False, server_default="pending")


class PlaylistSong(Base, UUIDMixin, TimestampMixin):
    # Ordered link between a playlist and a (shared) song.
    __tablename__ = "playlist_songs"
    __table_args__ = (UniqueConstraint("playlist_uuid", "song_uuid", name="uq_playlist_song"),)

    playlist_uuid = Column(UUIDType, ForeignKey("playlists.uuid", ondelete="CASCADE"), index=True, nullable=False)
    song_uuid = Column(UUIDType, ForeignKey("songs.uuid", ondelete="CASCADE"), index=True, nullable=False)
    position = Column(Integer, nullable=False, server_default="0")
