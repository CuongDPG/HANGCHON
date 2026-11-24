"""Driver Zalo OA — phần ĐĂNG BÀI VIẾT và gửi TIN BÀI VIẾT cho người quan tâm.

⚠️ CHƯA THỬ VỚI TÀI KHOẢN THẬT. Viết theo tài liệu Zalo for Developers (Official Account API, header `access_token`):
- Tạo bài viết: POST https://openapi.zalo.me/v2.0/article/create (`type=normal`, title, author, cover, description,
  body[] {type:text|image}, status=show) → `data.token`; xác nhận: POST /v2.0/article/verify `{token}` → `data.id`.
- Gửi cho người quan tâm (tin Broadcast, giới hạn theo gói OA): POST /v2.0/oa/message với `recipient.target` và
  `attachment.payload.template_type=media` mang `media_type=article`, `attachment_id=<id bài viết>`.
  Bật bằng ZALO_OA_BROADCAST=1 (mặc định chỉ tạo bài viết, chị tự bấm gửi trong trang quản lý OA).
- Số liệu: GET /v2.0/article/getdetail?id= (lượt xem, chia sẻ nếu có).

Cấu hình: ZALO_OA_ACCESS_TOKEN (settings), ZALO_OA_AUTHOR (tên tác giả hiển thị, mặc định «Hàng Chọn»).
Phần tin nhắn 1–1 thuộc driver hộp thư.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.social import InboundEvent, PostMetrics, PublishResult, SentMessage, SocialDriver, SocialPost
from app.integrations.social._ratelimit_publish import RateLimited, limiter

API = "https://openapi.zalo.me/v2.0"


class ZaloOAPublisher:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _token(self) -> str:
        if not settings.zalo_oa_access_token:
            raise IntegrationNotConfigured("Thiếu ZALO_OA_ACCESS_TOKEN để đăng bài Zalo OA.")
        return settings.zalo_oa_access_token

    async def _req(
        self, method: str, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60, transport=self._transport) as c:
            try:
                r = await c.request(
                    method,
                    f"{API}/{path.lstrip('/')}",
                    json=json,
                    params=params,
                    headers={"access_token": self._token()},
                )
            except httpx.HTTPError as e:
                raise IntegrationError(f"Không kết nối được Zalo: {e}") from e
        data = r.json() if "json" in r.headers.get("content-type", "") else {}
        err = data.get("error", 0)
        if r.status_code == 429 or err in (-32, -230):  # -32: vượt hạn mức gọi API
            raise RateLimited("Zalo OA báo chạm giới hạn, thử lại sau.")
        if r.status_code >= 400 or err not in (0, None):
            raise IntegrationError(f"Zalo OA báo lỗi: {data.get('message') or r.status_code}", code="zalo_error")
        return data.get("data") or {}

    async def publish(self, post: SocialPost) -> PublishResult:
        if post.channel not in (Channel.ZALO_OA, Channel.ZALO, Channel.ZALO_GROUP):
            raise IntegrationError(f"Driver Zalo không đăng được kênh {post.channel}.", code="unsupported_channel")
        limiter.check("zalo:article", limit=10, per_seconds=24 * 3600, label="Zalo OA")
        lines = [ln for ln in post.text.split("\n") if ln.strip()]
        title = (lines[0] if lines else "Hàng Chọn")[:150]
        body: list[dict[str, Any]] = [{"type": "text", "content": ln} for ln in lines]
        body += [{"type": "image", "url": u} for u in post.media_urls[:5] if post.media_kind in ("image", "carousel")]
        if post.link_url:
            body.append({"type": "text", "content": post.link_url})
        cover = {"cover_type": "photo", "photo_url": post.media_urls[0], "status": "show"} if post.media_urls else None
        art: dict[str, Any] = {
            "type": "normal",
            "title": title,
            "author": os.environ.get("ZALO_OA_AUTHOR", "Hàng Chọn"),
            "description": post.text[:300],
            "body": body,
            "status": "show",
            "comment": "show",
        }
        if cover:
            art["cover"] = cover
        token = (await self._req("POST", "article/create", json=art)).get("token")
        if not token:
            raise IntegrationError("Zalo OA không trả mã bài viết.", code="zalo_error")
        aid = (await self._req("POST", "article/verify", json={"token": token})).get("id") or token
        if os.environ.get("ZALO_OA_BROADCAST") == "1":
            await self._req(
                "POST",
                "oa/message",
                json={
                    "recipient": {"target": {}},
                    "message": {
                        "attachment": {
                            "type": "template",
                            "payload": {
                                "template_type": "media",
                                "elements": [{"media_type": "article", "attachment_id": aid}],
                            },
                        }
                    },
                },
            )
        return PublishResult(external_id=str(aid), url=None, status="published", published_at=now_utc())

    async def post_metrics(self, channel: Channel, external_id: str) -> PostMetrics:
        d = await self._req("GET", "article/getdetail", params={"id": external_id})
        views = int(d.get("total_view") or 0)
        return PostMetrics(
            external_id=external_id, impressions=views, reach=views, shares=int(d.get("total_share") or 0)
        )


class Driver(ZaloOAPublisher, SocialDriver):
    name = "zalo_oa_publish"

    async def fetch_inbound(self, since: datetime | None = None) -> list[InboundEvent]:
        raise IntegrationNotConfigured("Tin nhắn Zalo OA nằm ở driver «zalo_oa» của module hộp thư.")

    async def send_message(self, channel: Channel, thread_external_id: str, text: str) -> SentMessage:
        raise IntegrationNotConfigured("Tin nhắn Zalo OA nằm ở driver «zalo_oa» của module hộp thư.")

    async def reply_comment(self, channel: Channel, comment_external_id: str, text: str) -> SentMessage:
        raise IntegrationNotConfigured("Zalo OA nằm ở driver «zalo_oa» của module hộp thư.")

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[InboundEvent]:
        raise IntegrationNotConfigured("Webhook Zalo OA nằm ở driver «zalo_oa» của module hộp thư.")
