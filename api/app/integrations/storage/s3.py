"""Lưu tệp trên dịch vụ tương thích S3 (S3, R2, MinIO). Dùng boto3 trong luồng phụ.

Chưa kiểm chứng với dịch vụ thật — bật khi có tài khoản (S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.integrations.base import IntegrationNotConfigured
from app.integrations.storage import StorageDriver, StoredFile, validate_key


class Driver(StorageDriver):
    name = "s3"

    def __init__(self) -> None:
        self._client: Any = None

    @property
    def client(self) -> Any:
        if not (settings.s3_bucket and settings.s3_access_key and settings.s3_secret_key):
            raise IntegrationNotConfigured("Chưa cấu hình lưu trữ S3 (S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY).")
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
            )
        return self._client

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredFile:
        key = validate_key(key)
        await asyncio.to_thread(
            self.client.put_object, Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
        )
        return StoredFile(key=key, size=len(data), content_type=content_type, url=self.url(key))

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=settings.s3_bucket, Key=validate_key(key))
        return await asyncio.to_thread(obj["Body"].read)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=settings.s3_bucket, Key=validate_key(key))

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=settings.s3_bucket, Key=validate_key(key))
            return True
        except Exception:
            return False

    def url(self, key: str, *, expires_seconds: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": settings.s3_bucket, "Key": validate_key(key)}, ExpiresIn=expires_seconds
        )
