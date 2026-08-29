from sqlalchemy import Column, Integer, String, Text, UniqueConstraint

from app.models.base import Base, TimestampMixin, UUIDMixin


class AudioClip(Base, UUIDMixin, TimestampMixin):
    # One synthesized clip, cached so the same text is never spoken twice.
    #
    # Deliberately user-independent: the row is keyed by what was said and how,
    # not by who asked. "apple" in English with voice M1 is byte-identical for
    # every learner, so the first user to hear it pays the synthesis cost and
    # everyone after that gets a cache hit. That is what makes audio affordable
    # in song lyrics, where a chorus repeats the same words dozens of times.
    #
    # This table holds only metadata; the MP3 itself lives in object storage
    # under `object_key`. Deleting a row therefore orphans a blob — prefer
    # re-synthesis over deletion, and sweep storage separately if it ever
    # matters.
    __tablename__ = "audio_clips"
    __table_args__ = (UniqueConstraint("hash", name="uq_audio_clip_hash"),)

    # sha256 of "text|language|voice" — the cache key, and the public URL path
    # segment. Deterministic, so /api/audio/{hash}.mp3 can be cached forever.
    hash = Column(String(64), nullable=False, index=True)
    # Kept for debugging and for regenerating the cache after a voice change;
    # Text (not String) because a sentence has no useful length bound here.
    text = Column(Text, nullable=False)
    language = Column(String(8), nullable=False, index=True)
    voice = Column(String(32), nullable=False)
    object_key = Column(String(256), nullable=False)
    duration_ms = Column(Integer, nullable=True)
    size_bytes = Column(Integer, nullable=True)
