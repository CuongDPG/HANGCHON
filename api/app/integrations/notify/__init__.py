"""Báo tin cho khách (mốc đơn, mời đánh giá, nhắc mua lại...).

Driver: `mock` (mặc định, lưu hộp thư gửi trong bộ nhớ), `zalo_oa`, `email`."""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import Channel


class OutboundNotification(BaseModel):
    channel: Channel = Field(description="zalo_oa | email | sms | facebook (messenger)")
    to: str = Field(description="Định danh người nhận theo kênh: zalo user id, email, số điện thoại...")
    text: str
    subject: str | None = None
    template: str | None = Field(default=None, description="Mã mẫu tin phía nhà cung cấp (ZNS...) nếu có")
    data: dict = Field(default_factory=dict)
    link_url: str | None = None


class NotifyResult(BaseModel):
    external_id: str | None
    status: Literal["sent", "queued", "failed"]
    sent_at: datetime | None = None
    error: str | None = None


class NotifyDriver(abc.ABC):
    name: str
    channels: tuple[Channel, ...] = ()

    @abc.abstractmethod
    async def send(self, msg: OutboundNotification) -> NotifyResult: ...
