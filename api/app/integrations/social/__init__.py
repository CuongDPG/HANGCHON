"""Mạng xã hội: đăng bài, đẩy bản nháp (TikTok), đọc bình luận/tin nhắn, trả lời, số liệu bài.

Driver: `mock` (mặc định), `meta` (Facebook Page, Instagram, Threads), `tiktok_draft`, `zalo_oa`. Mỗi driver thật gộp
phần đăng bài + phần nhắn tin trong một lớp `Driver`. Chọn driver theo kênh bằng một cấu hình chung cho đăng bài và
hộp thư: `SOCIAL_CHANNEL_DRIVERS="facebook=meta,instagram=meta,threads=meta,zalo_oa=zalo_oa,tiktok=tiktok_draft"`;
kênh không khai dùng `SOCIAL_DRIVER` (mặc định `mock`). Xem `driver_name_for(channel)`."""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import Channel


class SocialPost(BaseModel):
    channel: Channel
    account_external_id: str | None = None
    text: str
    media_urls: list[str] = Field(default_factory=list)
    media_kind: Literal["none", "image", "carousel", "video"] = "none"
    link_url: str | None = None
    mode: Literal["publish", "draft"] = "publish"  # TikTok: luôn "draft" (chị bấm đăng trong app)
    ai_label: bool = False  # gắn nhãn «có nội dung do AI tạo» (k3)


class PublishResult(BaseModel):
    external_id: str
    url: str | None = None
    status: Literal["published", "draft_pushed", "scheduled"]
    published_at: datetime | None = None


class InboundEvent(BaseModel):
    """Bình luận hoặc tin nhắn từ khách."""

    channel: Channel
    kind: Literal["comment", "direct_message", "group_message"]
    account_external_id: str
    thread_external_id: str
    message_external_id: str
    post_external_id: str | None = None
    author_external_id: str
    author_name: str
    text: str
    attachments: list[str] = Field(default_factory=list)
    sent_at: datetime


class SentMessage(BaseModel):
    external_id: str
    sent_at: datetime


class PostMetrics(BaseModel):
    external_id: str
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    clicks: int = 0
    video_views: int = 0


# Tên driver cũ (khi phần đăng bài / nhắn tin còn tách đôi) → driver đã gộp
_ALIASES = {
    "meta_publish": "meta",
    "meta_messaging": "meta",
    "zalo_oa_publish": "zalo_oa",
    "zalo_oa_messaging": "zalo_oa",
    "tiktok_draft_publish": "tiktok_draft",
}


def canonical_driver(name: str | None) -> str:
    return _ALIASES.get(name or "mock", name or "mock")


def driver_name_for(channel: Channel | str) -> str:
    """Driver cho một kênh: `SOCIAL_CHANNEL_DRIVERS` → `SOCIAL_DRIVER` → `mock`."""
    from app.core.config import settings

    key = channel.value if isinstance(channel, Channel) else str(channel)
    spec = settings.social_channel_drivers.replace(" ", "")
    mapping = dict(p.split("=", 1) for p in spec.split(",") if "=" in p)
    return canonical_driver(mapping.get(key) or settings.social_driver or "mock")


def driver_for(channel: Channel | str) -> SocialDriver:
    from app.integrations.base import get_driver

    return get_driver("social", driver_name_for(channel))


class SocialDriver(abc.ABC):
    name: str
    supports_messaging: bool = True
    channels: tuple[Channel, ...] = ()  # kênh driver phục vụ (rỗng = mọi kênh)

    @abc.abstractmethod
    async def publish(self, post: SocialPost) -> PublishResult: ...

    @abc.abstractmethod
    async def fetch_inbound(self, since: datetime | None = None) -> list[InboundEvent]: ...

    @abc.abstractmethod
    async def send_message(self, channel: Channel, thread_external_id: str, text: str) -> SentMessage: ...

    @abc.abstractmethod
    async def reply_comment(self, channel: Channel, comment_external_id: str, text: str) -> SentMessage: ...

    @abc.abstractmethod
    async def post_metrics(self, channel: Channel, external_id: str) -> PostMetrics: ...

    @abc.abstractmethod
    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[InboundEvent]:
        """Xác thực chữ ký và đổi payload webhook thành sự kiện; sai chữ ký thì raise IntegrationError."""
