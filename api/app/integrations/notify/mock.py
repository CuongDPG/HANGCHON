"""Báo tin giả: lưu vào `outbox`. Người nhận chứa «fail» thì trả lỗi (để thử nhánh gửi hỏng)."""

from __future__ import annotations

from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations._mockutil import short_id
from app.integrations.notify import NotifyDriver, NotifyResult, OutboundNotification


class Driver(NotifyDriver):
    name = "mock"
    channels = (Channel.ZALO_OA, Channel.EMAIL, Channel.SMS, Channel.FACEBOOK)

    def __init__(self) -> None:
        self.outbox: list[OutboundNotification] = []

    async def send(self, msg: OutboundNotification) -> NotifyResult:
        if "fail" in msg.to:
            return NotifyResult(external_id=None, status="failed", error="Người nhận không tồn tại (giả lập).")
        self.outbox.append(msg)
        return NotifyResult(
            external_id=f"N{short_id(msg.to, msg.text, len(self.outbox))}", status="sent", sent_at=now_utc()
        )
