# Spotify playlist feature: how playlists are read and how much we process.
from app.core.config.base import BaseConfig


class PlaylistConfig(BaseConfig):
    # We read a public playlist's track list from Spotify's embed payload
    # (open.spotify.com/embed/playlist/{id}) — no API key or user login needed.
    # The official /playlists/{id}/tracks endpoint is blocked for new apps
    # (Spotify's Nov-2024 restriction), and the embed is the working path.
    PLAYLIST_EMBED_URL: str = "https://open.spotify.com/embed/playlist/{id}"

    # Cap how many tracks we analyse per playlist. The embed itself returns up to
    # ~100; we process fewer to keep AI/lyrics work bounded, and warn the user
    # when their playlist is longer so it's clear some tracks were skipped.
    PLAYLIST_MAX_TRACKS: int = 50

    # Network timeout for fetching the embed page.
    PLAYLIST_FETCH_TIMEOUT_SECONDS: float = 15.0
