"""Luật được phép nhắn lại khách theo từng kênh (cửa sổ trả lời).

- Messenger / Instagram (tài liệu Meta Messenger Platform): trong 24 giờ kể từ tin cuối của khách → nhắn bình thường
  (`messaging_type=RESPONSE`). Từ 24 giờ tới 7 ngày → chỉ **người thật** được trả lời, gắn thẻ `HUMAN_AGENT`
  (AI tự gửi thì không được). Quá 7 ngày → không nhắn được.
- Trả lời công khai dưới bình luận: không giới hạn thời gian. Nhắn riêng từ bình luận (private reply): một lần,
  trong 7 ngày kể từ bình luận.
- Zalo OA «tin tư vấn»: trong cửa sổ kể từ lần tương tác cuối của người dùng. Hằng số `ZALO_CS_WINDOW` để 7 ngày theo
  tài liệu Zalo OA API v3 — **chưa thử thật, cần kiểm lại chính sách hiện hành**; quá cửa sổ API sẽ báo lỗi.
- Nhóm Zalo: OA không gửi vào nhóm được → chị gửi tay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.modules.inbox.models import Thread, ThreadKind

META_STANDARD_WINDOW = timedelta(hours=24)
META_HUMAN_AGENT_WINDOW = timedelta(days=7)
META_PRIVATE_REPLY_WINDOW = timedelta(days=7)
ZALO_CS_WINDOW = timedelta(days=7)

META_CHANNELS = (Channel.FACEBOOK, Channel.INSTAGRAM)
ZALO_CHANNELS = (Channel.ZALO_OA, Channel.ZALO)


@dataclass
class Window:
    allowed: bool
    tag: str | None = None  # "HUMAN_AGENT" khi cần thẻ của Meta
    reason: str | None = None  # câu tiếng Việt khi không được


def reply_window(
    thread: Thread,
    *,
    human: bool,
    private: bool = False,
    now: datetime | None = None,
    comment_at: datetime | None = None,
) -> Window:
    """`human` = chị/người phụ bấm gửi (kể cả duyệt nháp AI); False = AI tự gửi."""
    now = now or now_utc()
    last = thread.last_inbound_at
    age = (now - last) if last else None

    if thread.kind == ThreadKind.GROUP:
        return Window(False, reason="Nhóm Zalo không gửi qua API được, chị dán tin vào nhóm giúp em.")
    if thread.kind == ThreadKind.WEB_CHAT:
        return Window(False, reason="Hội thoại từ trợ lý trên web: chị liên hệ khách qua số điện thoại khách để lại.")

    if thread.kind == ThreadKind.COMMENT:
        if not private:
            return Window(True)
        if thread.channel not in META_CHANNELS:
            return Window(False, reason="Kênh này không có nhắn riêng từ bình luận.")
        ref = comment_at or last
        if ref and now - ref > META_PRIVATE_REPLY_WINDOW:
            return Window(False, reason="Bình luận đã quá 7 ngày, Facebook không cho nhắn riêng nữa.")
        return Window(True)

    # tin nhắn riêng
    if thread.channel in META_CHANNELS:
        if age is None or age <= META_STANDARD_WINDOW:
            return Window(True)
        if age <= META_HUMAN_AGENT_WINDOW:
            if human:
                return Window(True, tag="HUMAN_AGENT")
            return Window(False, reason="Quá 24 giờ từ tin cuối của khách: chỉ chị trả lời được (thẻ người thật).")
        return Window(
            False, reason="Quá 7 ngày từ tin cuối của khách, Meta không cho nhắn tiếp. Chị chờ khách nhắn lại."
        )
    if thread.channel in ZALO_CHANNELS:
        if age is None or age <= ZALO_CS_WINDOW:
            return Window(True)
        return Window(False, reason="Quá hạn gửi tin tư vấn Zalo OA kể từ lần khách tương tác cuối.")
    return Window(True)
