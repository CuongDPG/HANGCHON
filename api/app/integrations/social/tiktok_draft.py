"""Driver TikTok — Content Posting API, chế độ ĐẨY BẢN NHÁP vào hộp thư của người dùng («Upload to inbox»).

⚠️ CHƯA THỬ VỚI TÀI KHOẢN THẬT. Viết theo tài liệu TikTok for Developers (Content Posting API):
- Video: POST https://open.tiktokapis.com/v2/post/publish/inbox/video/init/ (scope `video.upload`), nguồn
  `PULL_FROM_URL` (tên miền phải được xác minh) → `data.publish_id`. Người dùng nhận thông báo trong app TikTok và tự
  bấm đăng. Ứng dụng chưa qua kiểm duyệt chỉ đăng riêng tư được, nên Hàng Chọn luôn đẩy nháp.
- Ảnh: POST /v2/post/publish/content/init/ với `post_mode=MEDIA_UPLOAD`, `media_type=PHOTO`.
- Trạng thái: POST /v2/post/publish/status/fetch/ `{publish_id}` → `status` (vd SEND_TO_USER_INBOX, PUBLISH_COMPLETE)
  và `publicaly_available_post_id` khi chị đã đăng.
- Số liệu: POST /v2/video/query/?fields=id,view_count,like_count,comment_count,share_count (scope `video.list`).
- Giới hạn: 6 yêu cầu khởi tạo mỗi phút cho mỗi token người dùng.

Cấu hình (settings): TIKTOK_ACCESS_TOKEN (token người dùng; làm mới bằng TIKTOK_CLIENT_KEY/SECRET ngoài phạm vi
driver này). Chọn bằng `SOCIAL_CHANNEL_DRIVERS=tiktok=tiktok_draft`. Không có video/ảnh thì không đẩy được: kịch bản chữ để chị tự quay.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.enums import Channel
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.social import InboundEvent, PostMetrics, PublishResult, SentMessage, SocialDriver, SocialPost
from app.integrations.social._ratelimit import RateLimited, limiter

API = "https://open.tiktokapis.com/v2"


class TikTokDraftPublisher:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _token(self) -> str:
        tok = settings.tiktok_access_token
        if not tok:
            raise IntegrationNotConfigured("Thiếu TIKTOK_ACCESS_TOKEN để đẩy bản nháp TikTok.")
        return tok

    async def _post(self, path: str, body: dict[str, Any], params: dict[str, str] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json; charset=UTF-8"}
        async with httpx.AsyncClient(timeout=60, transport=self._transport) as c:
            try:
                r = await c.post(f"{API}/{path.lstrip('/')}", json=body, params=params, headers=headers)
            except httpx.HTTPError as e:
                raise IntegrationError(f"Không kết nối được TikTok: {e}") from e
        data = r.json() if "json" in r.headers.get("content-type", "") else {}
        err = data.get("error") or {}
        if r.status_code == 429 or err.get("code") == "rate_limit_exceeded":
            raise RateLimited("TikTok báo chạm giới hạn, thử lại sau ít phút.")
        if r.status_code >= 400 or (err.get("code") not in (None, "ok")):
            raise IntegrationError(f"TikTok báo lỗi: {err.get('message') or r.status_code}", code="tiktok_error")
        return data.get("data") or {}

    async def publish(self, post: SocialPost) -> PublishResult:
        if post.channel != Channel.TIKTOK:
            raise IntegrationError(f"Driver TikTok không đăng được kênh {post.channel}.", code="unsupported_channel")
        if not post.media_urls:
            raise IntegrationError(
                "TikTok cần video hoặc ảnh để đẩy bản nháp. Chị dựng video từ clip (mục Video) rồi thử lại.",
                code="media_required",
            )
        tok = self._token()
        limiter.check(f"tiktok:{tok[-8:]}", limit=6, per_seconds=60, label="TikTok")
        if post.media_kind == "video":
            data = await self._post(
                "post/publish/inbox/video/init/",
                {"source_info": {"source": "PULL_FROM_URL", "video_url": post.media_urls[0]}},
            )
        else:
            data = await self._post(
                "post/publish/content/init/",
                {
                    "post_info": {"title": post.text[:90], "description": post.text[:4000]},
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "photo_cover_index": 0,
                        "photo_images": post.media_urls[:35],
                    },
                    "post_mode": "MEDIA_UPLOAD",
                    "media_type": "PHOTO",
                },
            )
        pid = data.get("publish_id")
        if not pid:
            raise IntegrationError("TikTok không trả mã bản nháp.", code="tiktok_error")
        return PublishResult(external_id=pid, url=None, status="draft_pushed", published_at=None)

    async def post_metrics(self, channel: Channel, external_id: str) -> PostMetrics:
        video_id = external_id
        if not external_id.isdigit():  # publish_id của bản nháp → hỏi trạng thái để lấy id video khi chị đã đăng
            st = await self._post("post/publish/status/fetch/", {"publish_id": external_id})
            ids = st.get("publicaly_available_post_id") or []
            if not ids:
                return PostMetrics(external_id=external_id)
            video_id = str(ids[0])
        d = await self._post(
            "video/query/",
            {"filters": {"video_ids": [video_id]}},
            params={"fields": "id,view_count,like_count,comment_count,share_count"},
        )
        v = (d.get("videos") or [{}])[0]
        return PostMetrics(
            external_id=external_id,
            impressions=v.get("view_count", 0),
            reach=v.get("view_count", 0),
            video_views=v.get("view_count", 0),
            likes=v.get("like_count", 0),
            comments=v.get("comment_count", 0),
            shares=v.get("share_count", 0),
        )


class Driver(TikTokDraftPublisher, SocialDriver):
    name = "tiktok_draft"
    supports_messaging = False
    channels = (Channel.TIKTOK,)

    async def fetch_inbound(self, since: datetime | None = None) -> list[InboundEvent]:
        return []  # Content Posting API không có bình luận/tin nhắn

    async def send_message(self, channel: Channel, thread_external_id: str, text: str) -> SentMessage:
        raise IntegrationNotConfigured("TikTok không hỗ trợ gửi tin qua API này.")

    async def reply_comment(self, channel: Channel, comment_external_id: str, text: str) -> SentMessage:
        raise IntegrationNotConfigured("TikTok không hỗ trợ trả lời bình luận qua API này.")

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[InboundEvent]:
        raise IntegrationNotConfigured("Webhook TikTok chưa dùng.")
