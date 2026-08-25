"""Lyrics lookup: try each provider in order, return the first hit (or None)."""

import logging

from app.services.lyrics.base import LyricsProvider
from app.services.lyrics.lrclib import LrclibProvider

logger = logging.getLogger(__name__)

# Ordered by preference. Add a licensed provider (e.g. Musixmatch) ahead of
# LRCLIB here when one is configured.
_PROVIDERS: list[LyricsProvider] = [LrclibProvider()]


async def fetch_lyrics(title: str, artist: str) -> str | None:
    """Plain lyrics for a track from the first provider that has them."""
    for provider in _PROVIDERS:
        lyrics = await provider.fetch(title, artist)
        if lyrics:
            logger.info("Lyrics for %r by %r via %s", title, artist, provider.name)
            return lyrics
    return None
