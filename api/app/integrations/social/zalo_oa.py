"""Driver `zalo_oa`: Zalo Official Account — bài viết OA (`ZaloOAPublisher`) và tin nhắn 1–1 (`ZaloOAMessaging`)
trong một lớp. ⚠️ CHƯA THỬ VỚI OA THẬT (xem chú thích ở hai tệp phần)."""

from __future__ import annotations

import httpx

from app.core.enums import Channel
from app.integrations.social import SocialDriver
from app.integrations.social._zalo_oa_messaging import ZaloOAMessaging, zalo_signature
from app.integrations.social._zalo_oa_publish import ZaloOAPublisher


class Driver(ZaloOAMessaging, ZaloOAPublisher, SocialDriver):
    name = "zalo_oa"
    supports_messaging = True
    channels = (Channel.ZALO_OA,)

    def __init__(
        self, transport: httpx.AsyncBaseTransport | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        ZaloOAMessaging.__init__(self, client)
        self._transport = transport


__all__ = ["Driver", "zalo_signature"]
