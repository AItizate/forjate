"""The artifact store over the S3 API. Object keys start with the scope tag: the key-prefix isolation of the Crawl record."""

from __future__ import annotations

import io
import json
from typing import Protocol

from .config import Settings

INBOX, PARSED, LABELS = "inbox", "parsed", "labels"
BUCKETS = (INBOX, PARSED, LABELS)


class ObjectStore(Protocol):
    def ensure_buckets(self) -> None: ...
    def put(self, bucket: str, key: str, data: bytes) -> None: ...
    def get(self, bucket: str, key: str) -> bytes | None: ...
    def list_keys(self, bucket: str, prefix: str) -> list[str]: ...
    def delete_prefix(self, bucket: str, prefix: str) -> None: ...


class MinioObjects:
    def __init__(self, settings: Settings) -> None:
        from minio import Minio  # the client loads only where a real object store is used
        self._client = Minio(settings.minio_endpoint, access_key=settings.minio_user, secret_key=settings.minio_password, secure=False)

    def ensure_buckets(self) -> None:
        for bucket in BUCKETS:
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)

    def put(self, bucket: str, key: str, data: bytes) -> None:
        self._client.put_object(bucket, key, io.BytesIO(data), length=len(data))

    def get(self, bucket: str, key: str) -> bytes | None:
        from minio.error import S3Error
        try:
            response = self._client.get_object(bucket, key)
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchObject"):
                return None
            raise
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def list_keys(self, bucket: str, prefix: str) -> list[str]:
        return sorted(o.object_name for o in self._client.list_objects(bucket, prefix=prefix, recursive=True))

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        for key in self.list_keys(bucket, prefix):
            self._client.remove_object(bucket, key)


class MemoryObjects:
    """The same contract in memory, for tests without a cluster."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], bytes] = {}

    def ensure_buckets(self) -> None:
        return None

    def put(self, bucket: str, key: str, data: bytes) -> None:
        self.data[(bucket, key)] = data

    def get(self, bucket: str, key: str) -> bytes | None:
        return self.data.get((bucket, key))

    def list_keys(self, bucket: str, prefix: str) -> list[str]:
        return sorted(k for b, k in self.data if b == bucket and k.startswith(prefix))

    def delete_prefix(self, bucket: str, prefix: str) -> None:
        for key in self.list_keys(bucket, prefix):
            del self.data[(bucket, key)]


def label_key(scope: str, sha256: str) -> str:
    return f"{scope}/{sha256}.json"


def read_label(objects: ObjectStore, scope: str, sha256: str) -> dict | None:
    raw = objects.get(LABELS, label_key(scope, sha256))
    return json.loads(raw) if raw else None
