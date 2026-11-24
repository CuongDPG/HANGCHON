"""Driver `meta`: Facebook Page, Instagram, Threads — đăng bài + số liệu (`MetaPublisher`) và bình luận/tin nhắn
(`MetaMessaging`) trong một lớp. ⚠️ CHƯA THỬ VỚI ỨNG DỤNG META THẬT (xem chú thích ở hai tệp phần)."""

from __future__ import annotations

import httpx

from app.core.enums import Channel
from app.integrations.social import SocialDriver
from app.integrations.social._meta_messaging import MetaMessaging
from app.integrations.social._meta_publish import MetaPublisher


class Driver(MetaMessaging, MetaPublisher, SocialDriver):
    name = "meta"
    supports_messaging = True
    channels = (Channel.FACEBOOK, Channel.INSTAGRAM, Channel.THREADS)

    def __init__(
        self, transport: httpx.AsyncBaseTransport | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        MetaMessaging.__init__(self, client)
        self._transport = transport
