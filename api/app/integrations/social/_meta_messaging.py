"""Meta — phần bình luận và tin nhắn: webhook Page (bình luận + Messenger), Instagram (bình luận + Instagram Messaging),
trả lời bình luận, nhắn riêng từ bình luận (private reply), gửi tin nhắn theo cửa sổ 24 giờ / thẻ HUMAN_AGENT.

**CHƯA THỬ THẬT** với ứng dụng Meta thật — viết theo tài liệu chính thức:
- Webhooks: https://developers.facebook.com/docs/graph-api/webhooks/getting-started (GET hub.challenge,
  chữ ký `X-Hub-Signature-256: sha256=HMAC_SHA256(app_secret, body)`)
- Messenger Platform Send API: https://developers.facebook.com/docs/messenger-platform/send-messages
  (`messaging_type` RESPONSE | MESSAGE_TAG + `tag=HUMAN_AGENT`), private replies:
  https://developers.facebook.com/docs/messenger-platform/discovery/private-replies (`recipient.comment_id`)
- Page feed webhook (`changes[].field == "feed"`, `item == "comment"`), trả lời bình luận `POST /{comment-id}/comments`
- Instagram: webhook `comments` + `messages`; trả lời bình luận `POST /{ig-comment-id}/replies`; nhắn tin
  `POST /{page-id}/messages` (Instagram Messaging qua Facebook Login, dùng Page token)

Cấu hình (api/.env): META_APP_SECRET, META_PAGE_ID, META_PAGE_TOKEN, META_IG_USER_ID, META_WEBHOOK_VERIFY_TOKEN,
META_GRAPH_VERSION (mặc định v24.0). Token không lưu trong CSDL.

Phần đăng bài (`publish`, `post_metrics`) do module nội dung viết ở `meta.py`; lớp `MetaMessaging` ở đây là mixin để
người tích hợp gộp: `class Driver(MetaMessaging, <phần đăng bài>)` và đặt `supports_messaging = True`.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.enums import Channel
from app.core.security import verify_hmac_sha256
from app.core.timeutil import now_utc
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.social import InboundEvent, PostMetrics, PublishResult, SentMessage, SocialDriver, SocialPost

log = logging.getLogger("app.integrations.meta")

GRAPH = "https://graph.facebook.com"


def _ts(value: Any) -> datetime:
    """Thời điểm trong webhook: số mili giây (messaging) hoặc giây / ISO (changes)."""
    if isinstance(value, int | float):
        v = float(value)
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=UTC)
    if isinstance(value, str) and value:
        if value.isdigit():
            return _ts(int(value))
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00").replace("+0000", "+00:00"))
        except ValueError:
            pass
    return now_utc()


class MetaMessaging:
    """Mixin nhắn tin cho driver Meta."""

    supports_messaging = True
    supports_message_tags = True
    supports_private_reply = True

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._names: dict[str, str] = {}

    # ---- cấu hình -----------------------------------------------------------------------------------------------

    @property
    def version(self) -> str:
        return os.environ.get("META_GRAPH_VERSION", "v24.0")

    def _token(self) -> str:
        if not settings.meta_page_token:
            raise IntegrationNotConfigured("Chưa cấu hình META_PAGE_TOKEN cho trang Facebook.")
        return settings.meta_page_token

    def _page_id(self) -> str:
        if not settings.meta_page_id:
            raise IntegrationNotConfigured("Chưa cấu hình META_PAGE_ID.")
        return settings.meta_page_id

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{GRAPH}/{self.version}/{path.lstrip('/')}"
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            r = await client.post(url, params={"access_token": self._token()}, json=body)
        except httpx.HTTPError as e:
            raise IntegrationError(f"Không gọi được Meta: {e}") from e
        finally:
            if self._client is None:
                await client.aclose()
        data = r.json() if r.content else {}
        if r.status_code >= 400 or "error" in data:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            raise IntegrationError(
                f"Meta từ chối: {err.get('message') or r.text[:300]}", code=f"meta_{err.get('code', r.status_code)}"
            )
        return data

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{GRAPH}/{self.version}/{path.lstrip('/')}"
        client = self._client or httpx.AsyncClient(timeout=10)
        try:
            r = await client.get(url, params={**params, "access_token": self._token()})
            return r.json() if r.status_code < 400 else {}
        except httpx.HTTPError:
            return {}
        finally:
            if self._client is None:
                await client.aclose()

    # ---- webhook ------------------------------------------------------------------------------------------------

    def verify_subscription(self, params: dict[str, str]) -> str | None:
        """GET đăng ký webhook: trả `hub.challenge` khi verify token khớp, None nếu sai."""
        token = settings.meta_webhook_verify_token
        if params.get("hub.mode") == "subscribe" and token and params.get("hub.verify_token") == token:
            return params.get("hub.challenge", "")
        return None

    def check_signature(self, headers: dict[str, str], body: bytes) -> None:
        secret = settings.meta_app_secret
        if not secret:
            raise IntegrationNotConfigured("Chưa cấu hình META_APP_SECRET để kiểm chữ ký webhook.")
        sig = {k.lower(): v for k, v in headers.items()}.get("x-hub-signature-256", "")
        if not sig.startswith("sha256=") or not verify_hmac_sha256(secret, body, sig):
            raise IntegrationError("Chữ ký webhook Meta không hợp lệ.", code="invalid_signature")

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[InboundEvent]:
        self.check_signature(headers, body)
        try:
            data = json.loads(body or b"{}")
        except ValueError as e:
            raise IntegrationError("Webhook Meta không phải JSON.", code="invalid_payload") from e
        obj = data.get("object")
        channel = Channel.INSTAGRAM if obj == "instagram" else Channel.FACEBOOK
        out: list[InboundEvent] = []
        for entry in data.get("entry", []) or []:
            account = str(entry.get("id", ""))
            for m in entry.get("messaging", []) or []:
                ev = await self._from_messaging(channel, account, m)
                if ev:
                    out.append(ev)
            for ch in entry.get("changes", []) or []:
                ev = self._from_change(channel, account, ch)
                if ev:
                    out.append(ev)
        return out

    async def _from_messaging(self, channel: Channel, account: str, m: dict[str, Any]) -> InboundEvent | None:
        msg = m.get("message")
        if not isinstance(msg, dict) or msg.get("is_echo") or msg.get("is_deleted"):
            return None  # tin do chính trang gửi, đã xoá, hoặc sự kiện read/delivery
        sender = str((m.get("sender") or {}).get("id", ""))
        if not sender or sender == account:
            return None
        attachments = [
            str((a.get("payload") or {}).get("url"))
            for a in msg.get("attachments", []) or []
            if (a.get("payload") or {}).get("url")
        ]
        text = msg.get("text") or ("[Ảnh/tệp đính kèm]" if attachments else "")
        if not text:
            return None
        return InboundEvent(
            channel=channel,
            kind="direct_message",
            account_external_id=account,
            thread_external_id=sender,  # một hội thoại cho mỗi PSID / IGSID
            message_external_id=str(msg.get("mid") or f"{sender}:{m.get('timestamp')}"),
            author_external_id=sender,
            author_name=await self._profile_name(sender, channel),
            text=text,
            attachments=attachments,
            sent_at=_ts(m.get("timestamp")),
        )

    def _from_change(self, channel: Channel, account: str, ch: dict[str, Any]) -> InboundEvent | None:
        field, v = ch.get("field"), ch.get("value") or {}
        if channel == Channel.FACEBOOK:
            if field != "feed" or v.get("item") != "comment" or v.get("verb") not in ("add", "edited"):
                return None
            author = v.get("from") or {}
            if str(author.get("id", "")) == account:
                return None  # bình luận của chính trang
            comment_id = str(v.get("comment_id", ""))
            post_id = str(v.get("post_id", "")) or None
            parent = str(v.get("parent_id", "")) or None
            top = parent if parent and parent != post_id else comment_id
            text, name, sent = v.get("message") or "", author.get("name") or "Khách Facebook", v.get("created_time")
        else:
            if field != "comments":
                return None
            author = v.get("from") or {}
            if settings.meta_ig_user_id and str(author.get("id", "")) == settings.meta_ig_user_id:
                return None
            comment_id = str(v.get("id", ""))
            post_id = str((v.get("media") or {}).get("id", "")) or None
            top = str(v.get("parent_id", "")) or comment_id
            text, name, sent = v.get("text") or "", author.get("username") or "Khách Instagram", v.get("timestamp")
        if not comment_id or not text:
            return None
        return InboundEvent(
            channel=channel,
            kind="comment",
            account_external_id=account,
            thread_external_id=f"c:{top}",
            message_external_id=comment_id,
            post_external_id=post_id,
            author_external_id=str(author.get("id", "")) or comment_id,
            author_name=name,
            text=text,
            sent_at=_ts(sent),
        )

    async def _profile_name(self, user_id: str, channel: Channel) -> str:
        if user_id in self._names:
            return self._names[user_id]
        fallback = "Khách Instagram" if channel == Channel.INSTAGRAM else "Khách Facebook"
        if not settings.meta_page_token:
            return fallback
        fields = "name,username" if channel == Channel.INSTAGRAM else "first_name,last_name,name"
        data = await self._get(user_id, {"fields": fields})
        name = (
            data.get("name")
            or data.get("username")
            or " ".join(p for p in (data.get("last_name"), data.get("first_name")) if p)
        )
        self._names[user_id] = name or fallback
        return self._names[user_id]

    async def fetch_inbound(self, since: datetime | None = None) -> list[InboundEvent]:
        """Meta đẩy qua webhook; không kéo định kỳ."""
        return []

    # ---- gửi ----------------------------------------------------------------------------------------------------

    async def send_message(
        self, channel: Channel, thread_external_id: str, text: str, *, tag: str | None = None
    ) -> SentMessage:
        body: dict[str, Any] = {"recipient": {"id": thread_external_id}, "message": {"text": text}}
        if tag:
            body.update(messaging_type="MESSAGE_TAG", tag=tag)
        else:
            body["messaging_type"] = "RESPONSE"
        data = await self._post(f"{self._page_id()}/messages", body)
        return SentMessage(external_id=str(data.get("message_id", "")), sent_at=now_utc())

    async def send_private_reply(self, channel: Channel, comment_external_id: str, text: str) -> SentMessage:
        data = await self._post(
            f"{self._page_id()}/messages", {"recipient": {"comment_id": comment_external_id}, "message": {"text": text}}
        )
        return SentMessage(external_id=str(data.get("message_id", "")), sent_at=now_utc())

    async def reply_comment(self, channel: Channel, comment_external_id: str, text: str) -> SentMessage:
        path = f"{comment_external_id}/replies" if channel == Channel.INSTAGRAM else f"{comment_external_id}/comments"
        data = await self._post(path, {"message": text})
        return SentMessage(external_id=str(data.get("id", "")), sent_at=now_utc())


class Driver(MetaMessaging, SocialDriver):
    """Driver chỉ có phần nhắn tin (dùng khi `meta.py` chưa gộp phần này)."""

    name = "meta_messaging"

    async def publish(self, post: SocialPost) -> PublishResult:
        raise IntegrationNotConfigured("Đăng bài Meta nằm ở driver «meta» của module nội dung.")

    async def post_metrics(self, channel: Channel, external_id: str) -> PostMetrics:
        raise IntegrationNotConfigured("Số liệu bài Meta nằm ở driver «meta» của module nội dung.")
