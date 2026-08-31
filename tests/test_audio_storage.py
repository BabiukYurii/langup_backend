"""AudioStorage against a real S3 server.

The rest of the audio tests use an in-memory FakeStorage, which proves the
service's logic but never exercises aioboto3, the bucket bootstrap, or the way
a missing key surfaces. moto serves the actual S3 protocol over HTTP, so this
covers the code path that talks to MinIO in production.
"""

import socket
from uuid import uuid4

import pytest

from app.core import settings
from app.services.audio.keys import clip_hash, object_key
from app.services.audio.storage import AudioStorage

moto_server = pytest.importorskip("moto.server", reason="moto is a dev-only dependency")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def s3(monkeypatch):
    """A throwaway S3 endpoint, with settings pointed at it.

    The bucket name is unique per test: moto keeps its backends in process-level
    globals, so a fresh server still sees objects the previous test wrote, and a
    listing would pick them up.
    """
    port = _free_port()
    server = moto_server.ThreadedMotoServer(port=port, verbose=False)
    server.start()
    monkeypatch.setattr(settings.audio, "S3_ENDPOINT_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(settings.audio, "S3_ACCESS_KEY", "test")
    monkeypatch.setattr(settings.audio, "S3_SECRET_KEY", "test")
    monkeypatch.setattr(settings.audio, "S3_BUCKET", f"langup-test-{uuid4().hex[:12]}")
    yield AudioStorage()
    server.stop()


async def test_bucket_is_created_on_first_use(s3):
    """A fresh MinIO needs no manual setup step."""
    await s3.put(object_key(clip_hash("apple", "en", "M1")), b"ID3x")
    assert s3._bucket_ready


async def test_put_then_get_round_trips(s3):
    key = object_key(clip_hash("apple", "en", "M1"))
    await s3.put(key, b"ID3-the-bytes")
    assert await s3.get(key) == b"ID3-the-bytes"


async def test_missing_key_is_none_not_an_error(s3):
    """Storage can be wiped independently of the database; the caller re-synthesizes."""
    assert await s3.get(object_key("0" * 64)) is None


async def test_delete_removes_the_object(s3):
    key = object_key(clip_hash("apple", "en", "M1"))
    await s3.put(key, b"ID3x")
    await s3.delete(key)
    assert await s3.get(key) is None


async def test_sharded_keys_survive_the_round_trip(s3):
    """The "clips/ab/<hash>.mp3" prefix must not be mangled by the client."""
    hash_ = clip_hash("shard me", "en", "M1")
    key = object_key(hash_)
    await s3.put(key, b"ID3x")
    assert key == f"clips/{hash_[:2]}/{hash_}.mp3"
    assert await s3.get(key) == b"ID3x"


async def test_list_keys_returns_what_was_stored(s3):
    keys = [object_key(clip_hash(f"word {i}", "en", "M1")) for i in range(3)]
    for key in keys:
        await s3.put(key, b"ID3x")
    assert sorted(await s3.list_keys()) == sorted(keys)


async def test_listing_an_empty_bucket_is_not_an_error(s3):
    assert await s3.list_keys() == []
