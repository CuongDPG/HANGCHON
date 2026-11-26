"""Zalo Official Account — phần tin nhắn: webhook tin người dùng gửi OA, gửi «tin tư vấn» trong cửa sổ cho phép.

**CHƯA THỬ THẬT** với OA thật — viết theo tài liệu Zalo OA API v3 (https://developers.zalo.me/docs/official-account):
- Webhook: header `X-ZEvent-Signature: mac=<sha256(app_id + body + timestamp + oa_secret_key)>`; sự kiện
  `user_send_text`, `user_send_image`, `user_send_file`, `user_send_sticker`... với `sender.id` (user id theo OA),
  `recipient.id` (OA id), `message.msg_id`, `message.text`, `timestamp` (mili giây).
- Gửi tin tư vấn: `POST https://openapi.zalo.me/v3.0/oa/message/cs`, header `access_token`,
  body `{"recipient": {"user_id"}, "message": {"text"}}` → `{"error": 0, "data": {"message_id"}}`.
- Hồ sơ người dùng: `GET https://openapi.zalo.me/v3.0/oa/user/detail?data={"user_id": ...}` → `data.display_name`.

Cấu hình (settings): ZALO_OA_ID, ZALO_OA_ACCESS_TOKEN, ZALO_OA_SECRET (khoá bí mật OA dùng kiểm chữ ký), ZALO_APP_ID.
Lớp `ZaloOAMessaging` được gộp vào driver `zalo_oa` (`zalo_oa.py`). Access token OA hết hạn theo giờ — làm mới token là việc của người vận hành.
Zalo OA không có bình luận; gửi vào nhóm Zalo không làm qua đây.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations import channel_config as cc
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.integrations.social import InboundEvent, SentMessage

API = "https://openapi.zalo.me"
INBOUND_EVENTS = {
    "user_send_text",
    "user_send_image",
    "user_send_file",
    "user_send_sticker",
    "user_send_gif",
    "user_send_link",
    "user_send_location",
    "user_send_audio",
    "user_send_video",
}


def zalo_signature(app_id: str, body: bytes, timestamp: str, secret: str) -> str:
    return hashlib.sha256(app_id.encode() + body + timestamp.encode() + secret.encode()).hexdigest()


class ZaloOAMessaging:
    supports_messaging = True
    supports_message_tags = False
    supports_private_reply = False

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._names: dict[str, str] = {}

    def _token(self) -> str:
        if not cc.value("zalo_oa", "access_token"):
            raise IntegrationNotConfigured("Chưa cấu hình ZALO_OA_ACCESS_TOKEN.")
        return cc.value("zalo_oa", "access_token")

    async def _request(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            r = await client.request(method, f"{API}{path}", headers={"access_token": self._token()}, **kw)
        except httpx.HTTPError as e:
            raise IntegrationError(f"Không gọi được Zalo OA: {e}") from e
        finally:
            if self._client is None:
                await client.aclose()
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 400 or (isinstance(data, dict) and data.get("error", 0) != 0):
            raise IntegrationError(
                f"Zalo OA từ chối: {data.get('message') or r.text[:300]}",
                code=f"zalo_{data.get('error', r.status_code)}",
            )
        return data

    # ---- webhook ------------------------------------------------------------------------------------------------

    def check_signature(self, headers: dict[str, str], body: bytes, timestamp: str) -> None:
        secret, app_id = cc.value("zalo_oa", "oa_secret"), cc.value("zalo_oa", "app_id") or ""
        if not secret or not app_id:
            raise IntegrationNotConfigured("Chưa cấu hình ZALO_OA_SECRET / ZALO_APP_ID để kiểm chữ ký webhook Zalo.")
        sig = {k.lower(): v for k, v in headers.items()}.get("x-zevent-signature", "").removeprefix("mac=")
        if not sig or not hmac.compare_digest(sig, zalo_signature(app_id, body, timestamp, secret)):
            raise IntegrationError("Chữ ký webhook Zalo không hợp lệ.", code="invalid_signature")

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[InboundEvent]:
        try:
            data = json.loads(body or b"{}")
        except ValueError as e:
            raise IntegrationError("Webhook Zalo không phải JSON.", code="invalid_payload") from e
        self.check_signature(headers, body, str(data.get("timestamp", "")))
        if data.get("event_name") not in INBOUND_EVENTS:
            return []  # follow, oa_send_*, user_seen_message...
        sender = str((data.get("sender") or {}).get("id", ""))
        msg = data.get("message") or {}
        attachments = [
            str((a.get("payload") or {}).get("url"))
            for a in msg.get("attachments", []) or []
            if (a.get("payload") or {}).get("url")
        ]
        text = msg.get("text") or ("[Ảnh/tệp đính kèm]" if attachments else "")
        if not sender or not text:
            return []
        ts = data.get("timestamp")
        sent_at = datetime.fromtimestamp(int(ts) / 1000, tz=UTC) if str(ts or "").isdigit() else now_utc()
        return [
            InboundEvent(
                channel=Channel.ZALO_OA,
                kind="direct_message",
                account_external_id=str(
                    (data.get("recipient") or {}).get("id", "") or cc.value("zalo_oa", "oa_id") or ""
                ),
                thread_external_id=sender,
                message_external_id=str(msg.get("msg_id") or f"{sender}:{ts}"),
                author_external_id=sender,
                author_name=await self._display_name(sender),
                text=text,
                attachments=attachments,
                sent_at=sent_at,
            )
        ]

    async def _display_name(self, user_id: str) -> str:
        if user_id in self._names:
            return self._names[user_id]
        name = "Khách Zalo"
        if cc.value("zalo_oa", "access_token"):
            try:
                data = await self._request(
                    "GET", "/v3.0/oa/user/detail", params={"data": json.dumps({"user_id": user_id})}
                )
                name = (data.get("data") or {}).get("display_name") or name
            except IntegrationError:
                pass
        self._names[user_id] = name
        return name

    async def fetch_inbound(self, since: datetime | None = None) -> list[InboundEvent]:
        """Zalo đẩy qua webhook; không kéo định kỳ."""
        return []

    # ---- gửi ----------------------------------------------------------------------------------------------------

    async def send_message(self, channel: Channel, thread_external_id: str, text: str, **_: Any) -> SentMessage:
        data = await self._request(
            "POST",
            "/v3.0/oa/message/cs",
            json={"recipient": {"user_id": thread_external_id}, "message": {"text": text}},
        )
        return SentMessage(external_id=str((data.get("data") or {}).get("message_id", "")), sent_at=now_utc())

    async def reply_comment(self, channel: Channel, comment_external_id: str, text: str) -> SentMessage:
        raise IntegrationError("Zalo OA không có bình luận để trả lời.", code="not_supported")
