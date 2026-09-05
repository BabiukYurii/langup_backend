from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.models.base import Base, TimestampMixin, UUIDMixin, UUIDType


class SongWarmState(Base, UUIDMixin, TimestampMixin):
    # How far the warmer has got with one (song, target language) pair.
    #
    # Deliberately thin. The translation cache is the real cursor — a run
    # re-reads the song and skips what is already stored — so this table does
    # not track words, only two facts the cache cannot answer:
    #
    #   completed_at — a full pass found nothing missing. Without it the
    #     scheduler would re-fetch finished songs forever just to learn there
    #     is nothing to do.
    #   attempted_at — when it was last picked, so the rotation moves on
    #     instead of retrying one stubborn song over and over.
    #
    # Keyed by song and language, never by user: what a word means in a line
    # does not depend on who is reading it.
    __tablename__ = "song_warm_states"
    __table_args__ = (UniqueConstraint("song_uuid", "target_language", name="uq_song_warm_state"),)

    song_uuid = Column(UUIDType, ForeignKey("songs.uuid", ondelete="CASCADE"), index=True, nullable=False)
    target_language = Column(String(8), nullable=False, index=True)
    attempted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True, index=True)
    # Cumulative, for the admin view: is this feature earning its electricity?
    words_warmed = Column(Integer, nullable=False, server_default="0")
