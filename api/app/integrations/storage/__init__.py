"""Lưu trữ tệp: ảnh, chứng từ, ghi âm, bản sao lưu.

Quy ước khoá: `public/...` phục vụ công khai (ảnh sản phẩm), `private/...` chỉ người đăng nhập xem được
(chứng từ, ghi âm, sao lưu). Dùng `app.core.storage.get_storage()` để lấy driver theo env STORAGE_DRIVER."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class StoredFile:
    key: str
    size: int
    content_type: str
    url: str


class StorageDriver(abc.ABC):
    name: str

    @abc.abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredFile: ...

    @abc.abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None: ...

    @abc.abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abc.abstractmethod
    def url(self, key: str, *, expires_seconds: int = 3600) -> str:
        """Đường dẫn xem tệp (công khai hoặc có hạn)."""


def validate_key(key: str) -> str:
    key = key.strip().lstrip("/")
    if not key or ".." in key.split("/") or "\\" in key:
        raise ValueError("Khoá tệp không hợp lệ")
    return key
