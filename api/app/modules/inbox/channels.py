"""Chọn driver nhắn tin cho từng tài khoản kênh.

`channel_accounts.driver` cho biết tài khoản dùng driver nào (`mock`, `meta`, `zalo_oa`). Phần nhắn tin của driver thật
nằm ở `app/integrations/social/<ten>_messaging.py` (phần đăng bài do module nội dung viết ở `<ten>.py`). Khi hai phần
đã được gộp (lớp `Driver` của `<ten>.py` có `supports_messaging = True`) thì dùng thẳng `<ten>`.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import Channel
from app.integrations import IntegrationNotConfigured, get_driver

# webhook /api/hooks/social/<kênh> → driver
HOOK_DRIVERS = {"facebook": "meta", "instagram": "meta", "meta": "meta", "zalo_oa": "zalo_oa", "mock": "mock"}

DEFAULT_DRIVER_BY_CHANNEL = {Channel.FACEBOOK: "meta", Channel.INSTAGRAM: "meta", Channel.ZALO_OA: "zalo_oa"}


def messaging_driver(name: str | None) -> Any:
    name = name or "mock"
    if name == "mock":
        return get_driver("social", "mock")
    try:
        d = get_driver("social", name)
        if getattr(d, "supports_messaging", False):
            return d
    except IntegrationNotConfigured:
        pass
    return get_driver("social", f"{name}_messaging")
