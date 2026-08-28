from app.services.spotify.playlist_browser import rows_to_tracks


def test_rows_to_tracks_orders_by_index_and_caps():
    collected = {
        3: {"title": "Third", "artist": "C", "track_id": "t3"},
        1: {"title": "First", "artist": "A", "track_id": "t1"},
        2: {"title": "Second", "artist": "B", "track_id": "t2"},
    }
    tracks = rows_to_tracks(collected, limit=2)
    assert [t.title for t in tracks] == ["First", "Second"]  # ordered by rowindex, capped
    assert tracks[0].artist == "A" and tracks[0].spotify_id == "t1"


def test_rows_to_tracks_skips_empty_titles():
    collected = {1: {"title": "", "artist": "A", "track_id": None}, 2: {"title": "Real", "artist": "B"}}
    tracks = rows_to_tracks(collected, limit=10)
    assert [t.title for t in tracks] == ["Real"]
