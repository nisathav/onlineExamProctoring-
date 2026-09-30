"""MinIO evidence storage. Bucket stays private; staff get short-lived presigned URLs."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import Settings

log = logging.getLogger(__name__)


def evidence_key(username: str, exam_id: int, when: datetime) -> str:
    """`{username}/{exam_id}/{timestamp}.jpg` (thesis naming, plus exam id)."""
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{username}/{exam_id}/{stamp}.jpg"


class EvidenceStorage:
    def __init__(self, settings: Settings):
        import urllib3
        from minio import Minio

        self.bucket = settings.minio_bucket
        self.expiry = timedelta(seconds=settings.presigned_url_expiry_seconds)
        # Short timeouts and one retry: an outage must not stall the 3 s frame loop.
        http = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=2, read=5),
            retries=urllib3.Retry(total=1, backoff_factor=0.2),
            maxsize=20,
        )
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            http_client=http,
        )
        # Separate client for URL signing so the host in the URL is browser-reachable.
        # region is set so presigning never makes a network call.
        self.public_client = Minio(
            settings.minio_public_endpoint or settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_public_secure,
            region="us-east-1",
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        # No bucket policy is set, so objects are private by default.

    def put_jpeg(self, key: str, data: bytes) -> str:
        self.client.put_object(
            self.bucket, key, io.BytesIO(data), length=len(data), content_type="image/jpeg"
        )
        return key

    def presigned_url(self, key: str) -> str:
        return self.public_client.presigned_get_object(self.bucket, key, expires=self.expiry)

    def delete(self, key: str) -> None:
        self.client.remove_object(self.bucket, key)

    def delete_older_than(self, cutoff: datetime) -> int:
        removed = 0
        for obj in self.client.list_objects(self.bucket, recursive=True):
            if obj.last_modified and obj.last_modified < cutoff:
                self.client.remove_object(self.bucket, obj.object_name)
                removed += 1
        return removed
