"""Báo tin cho khách (mốc đơn, mời đánh giá, nhắc mua lại...).

Driver: `mock` (mặc định, lưu hộp thư gửi trong bộ nhớ), `zalo_zns` (tin theo mẫu đã duyệt của Zalo, gửi tới số điện
thoại hoặc user id OA), `email` (SMTP). Chọn driver theo kênh bằng `NOTIFY_CHANNEL_DRIVERS="zalo_oa=zalo_zns,email=email"`;
kênh không khai dùng `NOTIFY_DRIVER` (mặc định `mock`). Gửi qua `send(msg)` để được định tuyến theo kênh và để lỗi
cấu hình/mạng thành `NotifyResult(status="failed")` thay vì làm hỏng luồng gọi."""

from __future__ import annotations

import abc
import logging
from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.core.enums import Channel

log = logging.getLogger("app.integrations.notify")


class OutboundNotification(BaseModel):
    channel: Channel = Field(description="zalo_oa | email | sms | facebook (messenger)")
    to: str = Field(description="Định danh người nhận theo kênh: zalo user id, email, số điện thoại...")
    text: str
    subject: str | None = None
    template: str | None = Field(default=None, description="Mã mẫu tin phía nhà cung cấp (ZNS...) nếu có")
    data: dict = Field(default_factory=dict)
    link_url: str | None = None
    kind: str | None = Field(
        default=None,
        description="Loại tin của hệ thống (order_received, reorder_reminder...). Driver gửi theo mẫu (ZNS) tra mẫu "
        "theo loại này; `data` mang giá trị tham số.",
    )
    promotional: bool = Field(
        default=False, description="Tin quảng cáo / chăm sóc (nhắc mua lại, báo đợt) — khác tin giao dịch (mốc đơn)"
    )


class NotifyResult(BaseModel):
    external_id: str | None
    status: Literal["sent", "queued", "failed"]
    sent_at: datetime | None = None
    error: str | None = None
    # chỉ có nghĩa khi status="failed": True = lỗi tạm thời (mạng, hạn mức, giờ cấm gửi) → gửi lại sau;
    # False = lỗi vĩnh viễn (số sai, mẫu bị từ chối, thiếu cấu hình) → không gửi lại, thử kênh khác.
    retryable: bool = True


class NotifyDriver(abc.ABC):
    name: str
    channels: tuple[Channel, ...] = ()

    def missing_config(self) -> str | None:
        """Câu tiếng Việt nêu cấu hình còn thiếu; None = đủ để gửi."""
        return None

    @abc.abstractmethod
    async def send(self, msg: OutboundNotification) -> NotifyResult: ...


def failed(error: str, *, retryable: bool) -> NotifyResult:
    return NotifyResult(external_id=None, status="failed", error=error, retryable=retryable)


def driver_name_for(channel: Channel | str) -> str:
    """Driver cho một kênh: `NOTIFY_CHANNEL_DRIVERS` → `NOTIFY_DRIVER` → `mock`."""
    from app.core.config import settings

    key = channel.value if isinstance(channel, Channel) else str(channel)
    spec = settings.notify_channel_drivers.replace(" ", "")
    mapping = dict(p.split("=", 1) for p in spec.split(",") if "=" in p)
    return mapping.get(key) or settings.notify_driver or "mock"


def driver_for(channel: Channel | str) -> NotifyDriver:
    from app.integrations.base import get_driver

    return get_driver("notify", driver_name_for(channel))


async def send(msg: OutboundNotification) -> NotifyResult:
    """Gửi một tin qua driver của kênh. Không raise: thiếu cấu hình / kênh không hỗ trợ / lỗi mạng → `failed`."""
    from app.integrations.base import IntegrationError, IntegrationNotConfigured

    try:
        driver = driver_for(msg.channel)
    except IntegrationNotConfigured as e:
        return failed(e.message, retryable=False)
    if driver.channels and msg.channel not in driver.channels:
        return failed(f"Driver báo tin «{driver.name}» không gửi được kênh «{msg.channel.value}».", retryable=False)
    missing = driver.missing_config()
    if missing:
        return failed(missing, retryable=False)
    try:
        return await driver.send(msg)
    except IntegrationNotConfigured as e:
        return failed(e.message, retryable=False)
    except IntegrationError as e:
        return failed(e.message, retryable=True)
    except (httpx.HTTPError, OSError) as e:
        log.warning("Báo tin qua %s lỗi mạng: %s", driver.name, e)
        return failed(f"Không kết nối được dịch vụ gửi tin ({driver.name}), sẽ thử lại sau.", retryable=True)
