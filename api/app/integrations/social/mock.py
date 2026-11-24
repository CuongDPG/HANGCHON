"""Mạng xã hội giả: lưu bài đăng/tin gửi trong bộ nhớ; `simulate_inbound` giả lập khách bình luận/nhắn tin.

Webhook mock: body JSON `{"events": [InboundEvent...]}`, header `X-Mock-Signature: sha256=<hmac(HOOKS_MOCK_SECRET)>`."""

from __future__ import annotations

import json
from datetime import datetime

from app.core.config import settings
from app.core.enums import Channel
from app.core.security import verify_hmac_sha256
from app.core.timeutil import now_utc
from app.integrations._mockutil import rng, short_id
from app.integrations.base import IntegrationError
from app.integrations.social import (
    InboundEvent,
    PostMetrics,
    PublishResult,
    SentMessage,
    SocialDriver,
    SocialPost,
)


class Driver(SocialDriver):
    name = "mock"

    def __init__(self) -> None:
        self.published: list[tuple[SocialPost, PublishResult]] = []
        self.sent: list[dict[str, str]] = []
        self._inbound: list[InboundEvent] = []
        self._n = 0

    def _next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{short_id(prefix, self._n, now_utc().timestamp())}"

    async def publish(self, post: SocialPost) -> PublishResult:
        ext = self._next(post.channel.value)
        draft = post.mode == "draft" or post.channel == Channel.TIKTOK
        res = PublishResult(
            external_id=ext,
            url=None if draft else f"https://mock.hangchon.local/{post.channel.value}/posts/{ext}",
            status="draft_pushed" if draft else "published",
            published_at=None if draft else now_utc(),
        )
        self.published.append((post, res))
        return res

    def simulate_inbound(
        self,
        text: str,
        *,
        channel: Channel = Channel.FACEBOOK,
        kind: str = "direct_message",
        author_name: str = "Khách thử nghiệm",
        author_external_id: str | None = None,
        thread_external_id: str | None = None,
        post_external_id: str | None = None,
    ) -> InboundEvent:
        author = author_external_id or f"user_{short_id(author_name, length=8)}"
        ev = InboundEvent(
            channel=channel,
            kind=kind,  # type: ignore[arg-type]
            account_external_id=f"mock_{channel.value}_page",
            thread_external_id=thread_external_id or f"t_{channel.value}_{author}",
            message_external_id=self._next("m"),
            post_external_id=post_external_id,
            author_external_id=author,
            author_name=author_name,
            text=text,
            sent_at=now_utc(),
        )
        self._inbound.append(ev)
        return ev

    async def fetch_inbound(self, since: datetime | None = None) -> list[InboundEvent]:
        events = [e for e in self._inbound if since is None or e.sent_at > since]
        self._inbound = [e for e in self._inbound if e not in events]
        return events

    async def send_message(self, channel: Channel, thread_external_id: str, text: str) -> SentMessage:
        ext = self._next("out")
        self.sent.append({"channel": channel.value, "thread": thread_external_id, "text": text, "id": ext})
        return SentMessage(external_id=ext, sent_at=now_utc())

    async def reply_comment(self, channel: Channel, comment_external_id: str, text: str) -> SentMessage:
        ext = self._next("reply")
        self.sent.append({"channel": channel.value, "comment": comment_external_id, "text": text, "id": ext})
        return SentMessage(external_id=ext, sent_at=now_utc())

    async def post_metrics(self, channel: Channel, external_id: str) -> PostMetrics:
        r = rng("metrics", external_id)
        reach = r.randint(200, 8000)
        return PostMetrics(
            external_id=external_id,
            impressions=int(reach * r.uniform(1.1, 1.8)),
            reach=reach,
            likes=r.randint(5, reach // 10),
            comments=r.randint(0, 80),
            shares=r.randint(0, 40),
            saves=r.randint(0, 60),
            clicks=r.randint(0, 300),
            video_views=r.randint(0, reach * 2) if channel in (Channel.TIKTOK, Channel.INSTAGRAM) else 0,
        )

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[InboundEvent]:
        sig = {k.lower(): v for k, v in headers.items()}.get("x-mock-signature", "")
        if not verify_hmac_sha256(settings.hooks_mock_secret, body, sig):
            raise IntegrationError("Chữ ký webhook không hợp lệ.", code="invalid_signature")
        data = json.loads(body or b"{}")
        return [InboundEvent.model_validate(e) for e in data.get("events", [])]
