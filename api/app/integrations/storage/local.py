"""Lưu tệp trên đĩa (`STORAGE_LOCAL_DIR`), phục vụ qua `/api/files/<key>`."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import settings
from app.integrations.storage import StorageDriver, StoredFile, validate_key


class Driver(StorageDriver):
    name = "local"

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.storage_local_dir)

    def path(self, key: str) -> Path:
        p = (self.root / validate_key(key)).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("Khoá tệp không hợp lệ")
        return p

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredFile:
        p = self.path(key)

        def _write() -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            p.with_name(p.name + ".type").write_text(content_type)

        await asyncio.to_thread(_write)
        return StoredFile(key=validate_key(key), size=len(data), content_type=content_type, url=self.url(key))

    async def get(self, key: str) -> bytes:
        p = self.path(key)
        if not p.is_file():
            raise FileNotFoundError(key)
        return await asyncio.to_thread(p.read_bytes)

    def content_type(self, key: str) -> str:
        t = self.path(key).with_name(self.path(key).name + ".type")
        return t.read_text() if t.is_file() else "application/octet-stream"

    async def delete(self, key: str) -> None:
        p = self.path(key)
        for f in (p, p.with_name(p.name + ".type")):
            f.unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def url(self, key: str, *, expires_seconds: int = 3600) -> str:
        return f"{settings.storage_public_base_url.rstrip('/')}/{validate_key(key)}"
