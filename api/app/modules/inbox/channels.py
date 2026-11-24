"""Chọn driver nhắn tin cho từng tài khoản kênh.

Một cấu hình chung với module nội dung: `SOCIAL_CHANNEL_DRIVERS` / `SOCIAL_DRIVER` (xem `app.integrations.social`).
Tài khoản kênh có `channel_accounts.driver` khác `mock` thì dùng driver đó; không thì theo cấu hình của kênh.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import Channel
from app.integrations import get_driver
from app.integrations.social import canonical_driver, driver_name_for

# webhook /api/hooks/social/<kênh> → driver
HOOK_DRIVERS = {"facebook": "meta", "instagram": "meta", "meta": "meta", "zalo_oa": "zalo_oa", "mock": "mock"}


def messaging_driver(name: str | None, channel: Channel | str | None = None) -> Any:
    name = canonical_driver(name)
    if name == "mock" and channel is not None:
        name = driver_name_for(channel)
    return get_driver("social", name)
