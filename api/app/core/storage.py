"""Cửa lưu trữ tệp cho module nghiệp vụ.

from app.core.storage import get_storage, new_key
f = await get_storage().put(new_key("public/products", "jpg"), data, "image/jpeg")
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.integrations.base import get_driver
from app.integrations.storage import StorageDriver, StoredFile

__all__ = ["StorageDriver", "StoredFile", "get_storage", "is_public_key", "new_key"]


def get_storage() -> StorageDriver:
    return get_driver("storage")


def new_key(prefix: str, ext: str) -> str:
    """Khoá duy nhất: `<prefix>/<yyyy>/<mm>/<uuid>.<ext>`. prefix nên bắt đầu bằng `public/` hoặc `private/`."""
    now = datetime.now(UTC)
    return f"{prefix.strip('/')}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}.{ext.lstrip('.').lower()}"


def is_public_key(key: str) -> bool:
    return key.lstrip("/").startswith("public/")
