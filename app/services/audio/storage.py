"""Object storage for audio clips (MinIO in compose, any S3 API elsewhere).

Clips are blobs: they never need querying, they are written once and read many
times, and they would bloat both the database and its backups. So Postgres holds
only the metadata row and the bytes live here, addressed by the same hash.

A session is opened per call rather than kept on the instance: aioboto3 clients
are bound to the running event loop, and a long-lived one would break the moment
a Celery worker runs its own loop.
"""

import logging

import aioboto3
from botocore.exceptions import ClientError

from app.core import settings

logger = logging.getLogger(__name__)


class AudioStorageError(RuntimeError):
    """Object storage was unreachable or refused the operation."""


class AudioStorage:
    """Put and get audio blobs by object key."""

    def __init__(self) -> None:
        self._session = aioboto3.Session()
        self._bucket_ready = False

    def _client(self):
        cfg = settings.audio
        return self._session.client(
            "s3",
            endpoint_url=cfg.S3_ENDPOINT_URL,
            aws_access_key_id=cfg.S3_ACCESS_KEY,
            aws_secret_access_key=cfg.S3_SECRET_KEY,
            region_name=cfg.S3_REGION,
        )

    async def ensure_bucket(self) -> None:
        """Create the bucket on first use so a fresh MinIO needs no setup step."""
        if self._bucket_ready:
            return
        bucket = settings.audio.S3_BUCKET
        try:
            async with self._client() as s3:
                try:
                    await s3.head_bucket(Bucket=bucket)
                except ClientError:
                    await s3.create_bucket(Bucket=bucket)
                    logger.info("Created audio bucket %s", bucket)
        except Exception as e:  # noqa: BLE001 — surface one storage error type
            raise AudioStorageError(f"Could not reach object storage: {e}") from e
        self._bucket_ready = True

    async def put(self, key: str, data: bytes, content_type: str = "audio/mpeg") -> None:
        await self.ensure_bucket()
        try:
            async with self._client() as s3:
                await s3.put_object(Bucket=settings.audio.S3_BUCKET, Key=key, Body=data, ContentType=content_type)
        except Exception as e:  # noqa: BLE001
            raise AudioStorageError(f"Could not store {key}: {e}") from e

    async def get(self, key: str) -> bytes | None:
        """The blob, or None when it is not there.

        A missing object is a normal outcome, not an error: storage can be
        wiped independently of the database, and the caller re-synthesizes.
        """
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=settings.audio.S3_BUCKET, Key=key)
                async with response["Body"] as stream:
                    return await stream.read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NoSuchBucket"}:
                return None
            raise AudioStorageError(f"Could not read {key}: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise AudioStorageError(f"Could not read {key}: {e}") from e

    async def list_keys(self, prefix: str = "clips/") -> list[str]:
        """Every object key under `prefix`.

        Paginated explicitly: S3 caps a listing at 1000 keys per call and
        silently truncates, so a one-shot list would quietly under-report once
        the cache outgrows that — and a sweep built on it would then think
        nothing is orphaned.
        """
        keys: list[str] = []
        try:
            async with self._client() as s3:
                token: str | None = None
                while True:
                    kwargs = {"Bucket": settings.audio.S3_BUCKET, "Prefix": prefix}
                    if token:
                        kwargs["ContinuationToken"] = token
                    page = await s3.list_objects_v2(**kwargs)
                    keys.extend(item["Key"] for item in page.get("Contents", []))
                    if not page.get("IsTruncated"):
                        break
                    token = page.get("NextContinuationToken")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchBucket":
                return []
            raise AudioStorageError(f"Could not list {prefix}: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise AudioStorageError(f"Could not list {prefix}: {e}") from e
        return keys

    async def delete(self, key: str) -> None:
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=settings.audio.S3_BUCKET, Key=key)
        except Exception as e:  # noqa: BLE001
            raise AudioStorageError(f"Could not delete {key}: {e}") from e


_storage = AudioStorage()


def get_audio_storage() -> AudioStorage:
    return _storage
