"""Driver Meta — phần ĐĂNG BÀI và SỐ LIỆU BÀI (Facebook Page, Instagram Content Publishing, Threads).

⚠️ CHƯA THỬ VỚI TÀI KHOẢN THẬT. Viết theo tài liệu chính thức của Meta for Developers:
- Facebook Pages API: POST /{page-id}/feed (chữ/link), /{page-id}/photos (ảnh; nhiều ảnh = tải ảnh `published=false`
  rồi gắn `attached_media` vào /feed), POST graph-video /{page-id}/videos (`file_url`); số liệu: GET /{post-id}
  (reactions/comments/shares) + /{post-id}/insights.
- Instagram Content Publishing: POST /{ig-user-id}/media (ảnh `image_url`; carousel: từng ảnh `is_carousel_item=true`
  rồi container `media_type=CAROUSEL&children=`; Reels: `media_type=REELS&video_url=`) → chờ `status_code=FINISHED`
  → POST /{ig-user-id}/media_publish `creation_id`. Hạn mức 100 bài đăng qua API / 24 giờ. Số liệu: /{media-id}/insights.
- Threads API (graph.threads.net): POST /{threads-user-id}/threads (`media_type=TEXT|IMAGE|VIDEO|CAROUSEL`) → POST
  /{threads-user-id}/threads_publish `creation_id`. Hạn mức 250 bài / 24 giờ, chữ tối đa 500 ký tự.

- Gỡ bài khi ngừng bán (CHƯA THỬ THẬT): Facebook ẩn = POST /{page-post-id} `is_hidden=true` (Page token, quyền
  `pages_manage_posts`; hiện lại `is_hidden=false`), xoá hẳn = DELETE /{post-id}. Instagram xoá hẳn = DELETE
  /{ig-media-id} (quyền `instagram_manage_contents`) — chỉ dựa trên changelog Meta (12/2025, «IG Media Deleting API»),
  CHƯA đối chiếu tài liệu tham chiếu đầy đủ. Threads xoá hẳn = DELETE graph.threads.net /{threads-media-id} (quyền
  `threads_delete`, 100 lượt xoá / 24 giờ). Instagram, Threads không có «ẩn» → chỉ xoá hẳn khi chị chọn «Xoá hẳn».
  Bài video Facebook đăng qua /videos có mã là video id, ẩn bằng `is_hidden` có thể không áp dụng — kiểm khi bật thật.

Cấu hình (settings): META_PAGE_ID, META_PAGE_TOKEN, META_IG_USER_ID, THREADS_USER_ID, THREADS_ACCESS_TOKEN,
META_GRAPH_VERSION. Cài đặt → Mạng xã hội ghi đè các biến này (`channel_config`, khoá mã hoá trong CSDL). Lớp `MetaPublisher` được gộp vào driver `meta` (`meta.py`).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import settings
from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations import channel_config as cc
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.social import PostMetrics, PublishResult, RemoveMode, RemoveResult, SocialPost
from app.integrations.social._ratelimit import RateLimited, limiter

GRAPH = "https://graph.facebook.com"
GRAPH_VIDEO = "https://graph-video.facebook.com"
THREADS = "https://graph.threads.net"
# Mã lỗi Graph API về giới hạn tần suất (application/user/page/business throttling).
RATE_CODES = {4, 17, 32, 613, 80001, 80002, 80006}
DAY = 24 * 3600
# Cách gỡ bài từng kênh: Facebook ẩn được (hiện lại được) hoặc xoá hẳn; Instagram, Threads chỉ xoá hẳn.
REMOVE_MODES: dict[Channel, frozenset[str]] = {
    Channel.FACEBOOK: frozenset({"hide", "delete"}),
    Channel.INSTAGRAM: frozenset({"delete"}),
    Channel.THREADS: frozenset({"delete"}),
}


def _version() -> str:
    return settings.meta_graph_version


class MetaPublisher:
    """Đăng bài + lấy số liệu bài qua Graph API. Dùng chung client httpx; `transport` để test."""

    poll_interval = 3.0
    poll_attempts = 40

    _transport: httpx.AsyncBaseTransport | None = None

    # ---- cấu hình ------------------------------------------------------------------------------------------------

    @staticmethod
    def _need(value: str | None, name: str) -> str:
        if not value:
            raise IntegrationNotConfigured(f"Thiếu {name} để đăng bài qua Meta.")
        return value

    def _page(self) -> tuple[str, str]:
        return self._need(cc.value("facebook", "page_id"), "META_PAGE_ID"), self._need(
            cc.value("facebook", "page_token"), "META_PAGE_TOKEN"
        )

    def _ig(self) -> tuple[str, str]:
        return self._need(cc.value("instagram", "ig_user_id"), "META_IG_USER_ID"), self._need(
            cc.value("facebook", "page_token"), "META_PAGE_TOKEN"
        )

    def _threads(self) -> tuple[str, str]:
        return (
            self._need(cc.value("threads", "user_id"), "THREADS_USER_ID"),
            self._need(cc.value("threads", "access_token"), "THREADS_ACCESS_TOKEN"),
        )

    # ---- HTTP ----------------------------------------------------------------------------------------------------

    async def _call(self, method: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60, transport=self._transport) as c:
            try:
                r = await c.request(
                    method,
                    url,
                    data=params if method == "POST" else None,
                    params=params if method in ("GET", "DELETE") else None,
                )
            except httpx.HTTPError as e:
                raise IntegrationError(f"Không kết nối được Meta: {e}") from e
        data = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
        if r.status_code >= 400 or "error" in data:
            err = data.get("error") or {}
            code = err.get("code")
            msg = err.get("error_user_msg") or err.get("message") or f"HTTP {r.status_code}"
            if code in RATE_CODES or r.status_code == 429:
                raise RateLimited(f"Meta báo chạm giới hạn: {msg}")
            raise IntegrationError(f"Meta báo lỗi: {msg}", code="meta_error")
        return data

    def _g(self, path: str, host: str = GRAPH) -> str:
        return f"{host}/{_version()}/{path.lstrip('/')}"

    # ---- đăng ----------------------------------------------------------------------------------------------------

    async def publish(self, post: SocialPost) -> PublishResult:
        if post.channel == Channel.FACEBOOK:
            return await self._publish_facebook(post)
        if post.channel == Channel.INSTAGRAM:
            return await self._publish_instagram(post)
        if post.channel == Channel.THREADS:
            return await self._publish_threads(post)
        raise IntegrationError(f"Driver Meta không đăng được kênh {post.channel}.", code="unsupported_channel")

    async def _publish_facebook(self, post: SocialPost) -> PublishResult:
        page_id, token = self._page()
        limiter.check(f"fb:{page_id}", limit=1, per_seconds=5, label="Facebook")
        limiter.check(f"fb-day:{page_id}", limit=50, per_seconds=DAY, label="Facebook")
        if post.media_kind == "video" and post.media_urls:
            data = await self._call(
                "POST",
                self._g(f"{page_id}/videos", GRAPH_VIDEO),
                {"file_url": post.media_urls[0], "description": post.text, "access_token": token},
            )
            pid = data["id"]
        elif post.media_kind == "image" and len(post.media_urls) == 1:
            data = await self._call(
                "POST",
                self._g(f"{page_id}/photos"),
                {"url": post.media_urls[0], "caption": post.text, "access_token": token},
            )
            pid = data.get("post_id") or data["id"]
        elif post.media_urls and post.media_kind in ("image", "carousel"):
            media = []
            for url in post.media_urls[:10]:
                d = await self._call(
                    "POST", self._g(f"{page_id}/photos"), {"url": url, "published": "false", "access_token": token}
                )
                media.append(d["id"])
            params: dict[str, Any] = {"message": post.text, "access_token": token}
            for i, fbid in enumerate(media):
                params[f"attached_media[{i}]"] = f'{{"media_fbid":"{fbid}"}}'
            pid = (await self._call("POST", self._g(f"{page_id}/feed"), params))["id"]
        else:
            params = {"message": post.text, "access_token": token}
            if post.link_url:
                params["link"] = post.link_url
            pid = (await self._call("POST", self._g(f"{page_id}/feed"), params))["id"]
        return PublishResult(
            external_id=pid, url=f"https://www.facebook.com/{pid}", status="published", published_at=now_utc()
        )

    async def _wait_container(self, container_id: str, token: str, host: str = GRAPH) -> None:
        field = "status_code" if host == GRAPH else "status"
        for _ in range(self.poll_attempts):
            d = await self._call(
                "GET",
                f"{host}/{_version() if host == GRAPH else 'v1.0'}/{container_id}",
                {"fields": field, "access_token": token},
            )
            status = d.get(field)
            if status in ("FINISHED", "PUBLISHED"):
                return
            if status in ("ERROR", "EXPIRED"):
                raise IntegrationError(f"Meta không xử lý được tệp ({status}).", code="media_error")
            await asyncio.sleep(self.poll_interval)
        raise IntegrationError("Meta xử lý tệp quá lâu, sẽ thử lại sau.", code="media_timeout")

    async def _publish_instagram(self, post: SocialPost) -> PublishResult:
        ig, token = self._ig()
        if not post.media_urls:
            raise IntegrationError("Instagram cần ít nhất một ảnh hoặc video.", code="media_required")
        # Hạn mức chính thức 100 bài/24 giờ; giữ biên an toàn.
        limiter.check(f"ig-day:{ig}", limit=25, per_seconds=DAY, label="Instagram")
        media = self._g(f"{ig}/media")
        if post.media_kind == "video":
            d = await self._call(
                "POST",
                media,
                {"media_type": "REELS", "video_url": post.media_urls[0], "caption": post.text, "access_token": token},
            )
            creation = d["id"]
        elif len(post.media_urls) == 1:
            creation = (
                await self._call(
                    "POST", media, {"image_url": post.media_urls[0], "caption": post.text, "access_token": token}
                )
            )["id"]
        else:
            children = []
            for url in post.media_urls[:10]:  # carousel tối đa 10 mục
                d = await self._call(
                    "POST", media, {"image_url": url, "is_carousel_item": "true", "access_token": token}
                )
                children.append(d["id"])
            for cid in children:
                await self._wait_container(cid, token)
            creation = (
                await self._call(
                    "POST",
                    media,
                    {
                        "media_type": "CAROUSEL",
                        "children": ",".join(children),
                        "caption": post.text,
                        "access_token": token,
                    },
                )
            )["id"]
        await self._wait_container(creation, token)
        mid = (
            await self._call("POST", self._g(f"{ig}/media_publish"), {"creation_id": creation, "access_token": token})
        )["id"]
        link = (await self._call("GET", self._g(mid), {"fields": "permalink", "access_token": token})).get("permalink")
        return PublishResult(external_id=mid, url=link, status="published", published_at=now_utc())

    async def _publish_threads(self, post: SocialPost) -> PublishResult:
        uid, token = self._threads()
        limiter.check(f"threads-day:{uid}", limit=100, per_seconds=DAY, label="Threads")
        base = f"{THREADS}/v1.0/{uid}"
        text = post.text[:500]
        if post.media_kind == "video" and post.media_urls:
            params = {"media_type": "VIDEO", "video_url": post.media_urls[0], "text": text}
        elif post.media_urls and len(post.media_urls) == 1:
            params = {"media_type": "IMAGE", "image_url": post.media_urls[0], "text": text}
        elif post.media_urls:
            kids = []
            for url in post.media_urls[:20]:
                d = await self._call(
                    "POST",
                    f"{base}/threads",
                    {"media_type": "IMAGE", "image_url": url, "is_carousel_item": "true", "access_token": token},
                )
                kids.append(d["id"])
            params = {"media_type": "CAROUSEL", "children": ",".join(kids), "text": text}
        else:
            params = {"media_type": "TEXT", "text": text}
        creation = (await self._call("POST", f"{base}/threads", {**params, "access_token": token}))["id"]
        if params["media_type"] != "TEXT":
            await self._wait_container(creation, token, host=THREADS)
        tid = (await self._call("POST", f"{base}/threads_publish", {"creation_id": creation, "access_token": token}))[
            "id"
        ]
        link = (await self._call("GET", f"{THREADS}/v1.0/{tid}", {"fields": "permalink", "access_token": token})).get(
            "permalink"
        )
        return PublishResult(external_id=tid, url=link, status="published", published_at=now_utc())

    # ---- gỡ bài (ngừng bán) --------------------------------------------------------------------------------------

    def remove_modes(self, channel: Channel) -> frozenset[str]:
        return REMOVE_MODES.get(channel, frozenset())

    async def remove_post(self, channel: Channel, external_id: str, *, mode: RemoveMode = "hide") -> RemoveResult:
        if mode not in self.remove_modes(channel):
            return RemoveResult(mode="unsupported")
        if channel == Channel.FACEBOOK:
            _, token = self._page()
            if mode == "hide":
                await self._call("POST", self._g(external_id), {"is_hidden": "true", "access_token": token})
                return RemoveResult(mode="hidden")
            await self._call("DELETE", self._g(external_id), {"access_token": token})
            return RemoveResult(mode="deleted")
        if channel == Channel.INSTAGRAM:
            _, token = self._ig()
            await self._call("DELETE", self._g(external_id), {"access_token": token})
            return RemoveResult(mode="deleted")
        uid, token = self._threads()
        limiter.check(f"threads-delete:{uid}", limit=100, per_seconds=DAY, label="Threads (xoá bài)")
        await self._call("DELETE", f"{THREADS}/v1.0/{external_id}", {"access_token": token})
        return RemoveResult(mode="deleted")

    async def restore_post(self, channel: Channel, external_id: str) -> None:
        if channel != Channel.FACEBOOK:
            raise IntegrationError(f"Kênh {channel} không hiện lại bài được.", code="unsupported")
        _, token = self._page()
        await self._call("POST", self._g(external_id), {"is_hidden": "false", "access_token": token})

    # ---- số liệu -------------------------------------------------------------------------------------------------

    async def post_metrics(self, channel: Channel, external_id: str) -> PostMetrics:
        if channel == Channel.FACEBOOK:
            _, token = self._page()
            d = await self._call(
                "GET",
                self._g(external_id),
                {
                    "fields": "shares,reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)",
                    "access_token": token,
                },
            )
            ins = await self._insights(
                self._g(f"{external_id}/insights"), token, "post_impressions,post_impressions_unique,post_clicks"
            )
            return PostMetrics(
                external_id=external_id,
                impressions=ins.get("post_impressions", 0),
                reach=ins.get("post_impressions_unique", 0),
                clicks=ins.get("post_clicks", 0),
                likes=(d.get("reactions") or {}).get("summary", {}).get("total_count", 0),
                comments=(d.get("comments") or {}).get("summary", {}).get("total_count", 0),
                shares=(d.get("shares") or {}).get("count", 0),
            )
        if channel == Channel.INSTAGRAM:
            _, token = self._ig()
            ins = await self._insights(
                self._g(f"{external_id}/insights"), token, "reach,likes,comments,shares,saved,views"
            )
            return PostMetrics(
                external_id=external_id,
                impressions=ins.get("views", 0),
                reach=ins.get("reach", 0),
                likes=ins.get("likes", 0),
                comments=ins.get("comments", 0),
                shares=ins.get("shares", 0),
                saves=ins.get("saved", 0),
                video_views=ins.get("views", 0),
            )
        if channel == Channel.THREADS:
            _, token = self._threads()
            ins = await self._insights(
                f"{THREADS}/v1.0/{external_id}/insights", token, "views,likes,replies,reposts,quotes,shares"
            )
            return PostMetrics(
                external_id=external_id,
                impressions=ins.get("views", 0),
                reach=ins.get("views", 0),
                likes=ins.get("likes", 0),
                comments=ins.get("replies", 0),
                shares=ins.get("reposts", 0) + ins.get("quotes", 0) + ins.get("shares", 0),
            )
        raise IntegrationError(f"Driver Meta không đọc số liệu kênh {channel}.", code="unsupported_channel")

    async def _insights(self, url: str, token: str, metrics: str) -> dict[str, int]:
        d = await self._call("GET", url, {"metric": metrics, "access_token": token})
        out: dict[str, int] = {}
        for m in d.get("data", []):
            vals = m.get("values") or []
            v = vals[-1].get("value") if vals else m.get("total_value", {}).get("value")
            if isinstance(v, int | float):
                out[m["name"]] = int(v)
        return out
