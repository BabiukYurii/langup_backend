"""Lyrics provider abstraction.

A provider turns a (title, artist) into plain-text lyrics, or None when it has
no match. Keeping this behind an interface lets us try several free sources and
later add a licensed one (Musixmatch) without touching callers.
"""

from typing import Protocol


class LyricsProvider(Protocol):
    name: str

    async def fetch(self, title: str, artist: str) -> str | None:
        """Plain lyrics for the track, or None if not found."""
        ...
