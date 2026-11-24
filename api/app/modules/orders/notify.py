"""Báo tin cho khách (g5): mỗi mốc một tin theo mẫu tiếng Việt chị sửa được, lưu `notifications`, không gửi trùng.

Tin mốc đơn là tin theo mẫu chị đã duyệt (không phải AI soạn) nên gửi thẳng, không qua hàng chờ duyệt;
chị tắt được bằng cài đặt `orders.notify_enabled`."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.config import settings
from app.core.enums import Channel
from app.core.money import format_vnd
from app.core.timeutil import format_local, now_utc
from app.integrations import get_driver
from app.integrations.notify import OutboundNotification
from app.modules.orders.models import (
    Customer,
    CustomerIdentity,
    Notification,
    NotificationEvent,
    NotificationStatus,
    Order,
    PaymentMethod,
)
from app.modules.orders.util import order_access_token

log = logging.getLogger("app.orders.notify")

TEMPLATE_LABELS: dict[str, str] = {
    "order_received": "Đã nhận đơn",
    "payment_confirmed": "Đã nhận tiền",
    "payment_reminder": "Nhắc chuyển khoản",
    "stock_arriving": "Hàng đang về",
    "shipped": "Đã giao cho hãng vận chuyển",
    "out_for_delivery": "Đang giao tới khách",
    "delivered": "Đã giao xong",
    "order_cancelled": "Đơn đã huỷ",
    "return_update": "Cập nhật đổi trả",
    "owner_reply": "Chị trả lời câu hỏi về đơn",
}

DEFAULT_TEMPLATES: dict[str, str] = {
    "order_received": "Hàng Chọn đã nhận đơn {ma_don} của {ten}: {mon}. Tổng {tong_tien}. {cach_tra} Theo dõi đơn: {link}",
    "payment_confirmed": "Hàng Chọn đã nhận {so_tien} cho đơn {ma_don}. Cảm ơn {ten}! {ngay_ve}",
    "payment_reminder": (
        "Đơn {ma_don} vẫn đang chờ chuyển khoản {can_tra} (nội dung «{noi_dung_ck}»). "
        "Mình giữ suất tới {han_tra}, quá hạn suất sẽ được nhường cho người khác. {link}"
    ),
    "stock_arriving": "Hàng của đơn {ma_don} đang trên đường về Việt Nam, dự kiến về {ngay_ve_ngan}. Theo dõi: {link}",
    "shipped": "Đơn {ma_don} đã giao cho {hang}, mã vận đơn {ma_van_don}. {thu_ho}",
    "out_for_delivery": "Đơn {ma_don} đang được giao tới bạn. {thu_ho}",
    "delivered": "Đơn {ma_don} đã giao xong. Cảm ơn {ten}! Có điều gì chưa ưng bạn nhắn lại giúp mình nhé.",
    "order_cancelled": "Đơn {ma_don} đã huỷ: {ly_do}. Nếu cần đặt lại, bạn vào {link_cua_hang} nhé.",
    "return_update": "Yêu cầu đổi trả {ma_doi_tra} cho đơn {ma_don}: {ket_qua}",
    "owner_reply": "Về đơn {ma_don}: {noi_dung}",
}

PLACEHOLDERS: dict[str, str] = {
    "ten": "Tên người nhận",
    "ma_don": "Mã đơn, vd HC-48213",
    "mon": "Tóm tắt món đã đặt",
    "tong_tien": "Tổng tiền đơn",
    "so_tien": "Số tiền vừa nhận",
    "can_tra": "Số tiền còn phải chuyển",
    "noi_dung_ck": "Nội dung chuyển khoản",
    "han_tra": "Hạn chuyển khoản",
    "cach_tra": "Câu nhắc cách trả tiền",
    "ngay_ve": "Câu nhắc ngày hàng về (nếu đơn trong đợt)",
    "ngay_ve_ngan": "Ngày hàng về dự kiến",
    "hang": "Hãng vận chuyển",
    "ma_van_don": "Mã vận đơn",
    "thu_ho": "Câu nhắc tiền thu khi nhận (đơn trả khi nhận)",
    "ly_do": "Lý do huỷ",
    "ma_doi_tra": "Mã yêu cầu đổi trả",
    "ket_qua": "Kết quả xử lý đổi trả",
    "noi_dung": "Lời chị trả lời",
    "link": "Đường link theo dõi đơn",
    "link_cua_hang": "Địa chỉ website",
}

EVENT_OF: dict[str, NotificationEvent] = {
    "order_received": NotificationEvent.ORDER_RECEIVED,
    "payment_confirmed": NotificationEvent.PAYMENT_CONFIRMED,
    "payment_reminder": NotificationEvent.PAYMENT_REMINDER,
    "stock_arriving": NotificationEvent.STOCK_ARRIVING,
    "shipped": NotificationEvent.SHIPPED,
    "out_for_delivery": NotificationEvent.OUT_FOR_DELIVERY,
    "delivered": NotificationEvent.DELIVERED,
    "return_update": NotificationEvent.RETURN_UPDATE,
    "order_cancelled": NotificationEvent.OTHER,
    "owner_reply": NotificationEvent.OTHER,
}

CARRIER_NAMES = {"ghn": "Giao Hàng Nhanh", "ghtk": "Giao Hàng Tiết Kiệm", "mock": "hãng giao (thử)", "self": "chị"}


def vnd(v: int) -> str:
    return format_vnd(v, suffix="đ")


def order_link(order: Order) -> str:
    return f"{settings.web_base_url.rstrip('/')}/don/{order.code}?t={order_access_token(order.id)}"


async def get_templates(db: AsyncSession) -> dict[str, str]:
    saved = await control.get_setting(db, "orders.notify_templates") or {}
    return {**DEFAULT_TEMPLATES, **{k: v for k, v in saved.items() if k in DEFAULT_TEMPLATES and str(v).strip()}}


def render(template: str, values: dict[str, Any]) -> str:
    text = template.format_map(defaultdict(str, {k: "" if v is None else v for k, v in values.items()}))
    return " ".join(text.split())


def base_values(order: Order, *, drop_arrival: str | None = None) -> dict[str, Any]:
    due = order.total_vnd - order.paid_vnd
    deposit_due = max(0, order.deposit_required_vnd - order.paid_vnd)
    need = deposit_due or due
    items = ", ".join(f"{i.name} x{i.quantity}" for i in order.items)
    if order.payment_method == PaymentMethod.BANK_TRANSFER and need > 0:
        cach_tra = f"Bạn chuyển khoản {vnd(need)} với nội dung «{order.transfer_content}» nhé."
    elif order.payment_method == PaymentMethod.COD:
        cach_tra = f"Bạn trả {vnd(order.cod_amount_vnd)} khi nhận hàng."
    else:
        cach_tra = ""
    return {
        "ten": order.recipient_name,
        "ma_don": order.code,
        "mon": items,
        "tong_tien": vnd(order.total_vnd),
        "can_tra": vnd(need),
        "noi_dung_ck": order.transfer_content or "",
        "han_tra": format_local(order.payment_due_at, "%H:%M %d/%m") if order.payment_due_at else "",
        "cach_tra": cach_tra,
        "ngay_ve": f"Hàng về dự kiến {drop_arrival}." if drop_arrival else "",
        "ngay_ve_ngan": drop_arrival or "sớm",
        "thu_ho": f"Bạn chuẩn bị {vnd(order.cod_amount_vnd)} khi nhận hàng nhé." if order.cod_amount_vnd else "",
        "link": order_link(order),
        "link_cua_hang": settings.web_base_url,
    }


async def _recipient(db: AsyncSession, order: Order, channel: Channel) -> str | None:
    if order.customer_id:
        ident = (
            await db.execute(
                select(CustomerIdentity.external_id).where(
                    CustomerIdentity.customer_id == order.customer_id, CustomerIdentity.channel == channel
                )
            )
        ).scalar_one_or_none()
        if ident:
            return ident
        if channel == Channel.EMAIL:
            return (await db.execute(select(Customer.email).where(Customer.id == order.customer_id))).scalar()
    if channel == Channel.EMAIL:
        return None
    return order.recipient_phone  # Zalo ZNS / SMS gửi theo số điện thoại


async def already_sent(db: AsyncSession, order: Order, key: str, dedupe: str | None = None) -> bool:
    dedupe_key = f"order:{order.id}:{key}" + (f":{dedupe}" if dedupe else "")
    return bool(await db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)))


async def notify_order(
    db: AsyncSession,
    order: Order,
    key: str,
    extra: dict[str, Any] | None = None,
    *,
    dedupe: str | None = None,
    drop_arrival: str | None = None,
) -> Notification | None:
    """Gửi tin mốc `key` cho khách của đơn. Mỗi (đơn, mốc[, dedupe]) chỉ gửi một lần. Lỗi gửi không làm hỏng luồng đơn."""
    if order.channel in (Channel.TIKTOK_SHOP, Channel.SHOPEE):
        return None  # sàn tự báo khách, mình không có kênh nhắn riêng
    dedupe_key = f"order:{order.id}:{key}" + (f":{dedupe}" if dedupe else "")
    existing = (
        await db.execute(select(Notification).where(Notification.dedupe_key == dedupe_key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    templates = await get_templates(db)
    body = render(templates[key], {**base_values(order, drop_arrival=drop_arrival), **(extra or {})})
    channel = Channel(await control.get_setting(db, "orders.notify_channel") or Channel.ZALO_OA.value)
    recipient = await _recipient(db, order, channel)
    n = Notification(
        customer_id=order.customer_id,
        order_id=order.id,
        event=EVENT_OF.get(key, NotificationEvent.OTHER),
        channel=channel,
        recipient=recipient or "",
        body=body,
        dedupe_key=dedupe_key,
        status=NotificationStatus.QUEUED,
    )
    try:
        async with db.begin_nested():
            db.add(n)
            await db.flush()
    except IntegrityError:  # hai luồng cùng gửi một mốc: luồng kia đã giữ chỗ
        return (await db.execute(select(Notification).where(Notification.dedupe_key == dedupe_key))).scalar_one()
    enabled = await control.get_setting(db, "orders.notify_enabled")
    if enabled is False or not recipient:
        n.status = NotificationStatus.SKIPPED
        n.error = None if recipient else "Khách chưa có kênh nhận tin."
        await db.flush()
        return n
    await deliver(db, n)
    return n


async def deliver(db: AsyncSession, n: Notification) -> None:
    n.attempts += 1
    try:
        res = await get_driver("notify").send(OutboundNotification(channel=n.channel, to=n.recipient, text=n.body))
    except Exception as e:  # tích hợp lỗi mạng / chưa cấu hình
        log.warning("Gửi tin %s lỗi: %s", n.dedupe_key, e)
        n.status = NotificationStatus.FAILED
        n.error = str(getattr(e, "message", e))[:500]
    else:
        n.status = NotificationStatus.SENT if res.status in ("sent", "queued") else NotificationStatus.FAILED
        n.external_id = res.external_id
        n.sent_at = res.sent_at or (now_utc() if n.status == NotificationStatus.SENT else None)
        n.error = res.error
    await db.flush()
