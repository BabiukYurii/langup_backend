"""Sweeping blobs no row points at any more."""

import pytest

from app.repositories.audio_clip import AudioClipRepository
from app.services.audio.service import AudioService
from tests.test_audio_cache import FakeAI, FakeStorage


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    async def fake_encode(wav: bytes) -> bytes:
        return b"ID3" + wav[:64]

    async def fake_duration(mp3: bytes) -> int:
        return 1000

    monkeypatch.setattr("app.services.audio.service.transcode", fake_encode)
    monkeypatch.setattr("app.services.audio.service.clip_duration_ms", fake_duration)


class ListableStorage(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.list_calls = 0

    async def list_keys(self, prefix: str = "clips/") -> list[str]:
        self.list_calls += 1
        return [k for k in self.objects if k.startswith(prefix)]


@pytest.fixture
def audio(session):
    storage, ai = ListableStorage(), FakeAI()
    return AudioService(AudioClipRepository(session), storage, ai), storage


async def test_a_clean_cache_has_no_orphans(audio):
    service, _ = audio
    await service.get_or_create("apple", "en")
    orphans, removed = await service.sweep_orphans()
    assert (orphans, removed) == ([], 0)


async def test_a_blob_without_a_row_is_reported(audio):
    service, storage = audio
    await service.get_or_create("apple", "en")
    storage.objects["clips/ab/deadbeef.mp3"] = b"ID3 left over"

    orphans, removed = await service.sweep_orphans()
    assert orphans == ["clips/ab/deadbeef.mp3"]
    assert removed == 0  # reporting only


async def test_reporting_does_not_delete(audio):
    """The default must never destroy anything: the two systems can disagree
    innocently, e.g. a blob written before its row commits."""
    service, storage = audio
    storage.objects["clips/ab/deadbeef.mp3"] = b"ID3"
    await service.sweep_orphans()
    assert "clips/ab/deadbeef.mp3" in storage.objects


async def test_delete_removes_only_the_orphans(audio):
    service, storage = audio
    clip, _ = await service.get_or_create("apple", "en")
    storage.objects["clips/ab/deadbeef.mp3"] = b"ID3"

    orphans, removed = await service.sweep_orphans(delete=True)
    assert removed == 1
    assert "clips/ab/deadbeef.mp3" not in storage.objects
    assert clip.object_key in storage.objects  # the live clip is untouched


async def test_a_stale_cache_version_leaves_the_old_blob_behind(audio, monkeypatch):
    """The case this exists for: bumping the version re-keys every clip, and
    the blobs under the old keys become unreachable."""
    import app.services.audio.keys as keys

    service, storage = audio
    old, _ = await service.get_or_create("apple", "en")
    await service.repo.delete_one(old)  # the old row is gone with the version bump

    monkeypatch.setattr(keys, "CACHE_VERSION", "v2")
    new, _ = await service.get_or_create("apple", "en")
    assert new.object_key != old.object_key

    orphans, removed = await service.sweep_orphans(delete=True)
    assert orphans == [old.object_key]
    assert removed == 1
    assert new.object_key in storage.objects


async def test_a_failed_delete_does_not_stop_the_sweep(audio, monkeypatch):
    service, storage = audio
    storage.objects["clips/aa/one.mp3"] = b"ID3"
    storage.objects["clips/bb/two.mp3"] = b"ID3"

    from app.services.audio.storage import AudioStorageError

    async def flaky(key: str) -> None:
        if key.endswith("one.mp3"):
            raise AudioStorageError("nope")
        storage.objects.pop(key, None)

    monkeypatch.setattr(storage, "delete", flaky)
    orphans, removed = await service.sweep_orphans(delete=True)
    assert len(orphans) == 2
    assert removed == 1  # the other one still went


# --- listing pagination ----------------------------------------------------
# Exercised with a stub rather than by uploading 1000+ objects to a real S3:
# what matters is that the continuation token is followed, and proving that
# against a live server costs minutes of sequential PUTs for no extra coverage.


class _PagedClient:
    """An S3 client that answers a listing in two truncated pages."""

    def __init__(self, pages):
        self.pages = pages
        self.tokens_seen = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def list_objects_v2(self, **kwargs):
        self.tokens_seen.append(kwargs.get("ContinuationToken"))
        return self.pages[len(self.tokens_seen) - 1]


async def test_list_keys_follows_the_continuation_token(monkeypatch):
    """S3 truncates a listing at 1000 keys. Without following the token the
    sweep would treat everything past the first page as still referenced —
    i.e. silently stop collecting once the cache grows."""
    from app.services.audio.storage import AudioStorage

    client = _PagedClient(
        [
            {"Contents": [{"Key": "clips/aa/1.mp3"}], "IsTruncated": True, "NextContinuationToken": "tok"},
            {"Contents": [{"Key": "clips/bb/2.mp3"}], "IsTruncated": False},
        ]
    )
    storage = AudioStorage()
    monkeypatch.setattr(storage, "_client", lambda: client)

    assert await storage.list_keys() == ["clips/aa/1.mp3", "clips/bb/2.mp3"]
    assert client.tokens_seen == [None, "tok"]  # second call carried the token
