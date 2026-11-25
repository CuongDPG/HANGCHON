"""Báo tin cho khách (g5): mỗi mốc một tin theo mẫu tiếng Việt chị sửa được, lưu `notifications`, không gửi trùng.

Tin mốc đơn là tin theo mẫu chị đã duyệt (không phải AI soạn) nên gửi thẳng, không qua hàng chờ duyệt;
chị tắt được bằng cài đặt `orders.notify_enabled`.

Kênh: thử kênh chính `orders.notify_channel`, không gửi được thì lần lượt các kênh `orders.notify_fallback_channels`
(vd `["email"]`, chỉ khi khách có định danh ở kênh đó). Driver của từng kênh chọn bằng `NOTIFY_CHANNEL_DRIVERS`.
Lỗi tạm thời → cron `orders.retry_notifications` gửi lại (tối đa `MAX_ATTEMPTS` lần); mọi kênh đều lỗi vĩnh viễn →
không gửi lại. Driver theo mẫu (Zalo ZNS) nhận loại tin (`kind` = khoá mốc) và giá trị các ô mẫu (`data`).
Giới hạn: bảng `notifications` không lưu giá trị ô, nên lần gửi lại dựng lại ô từ đơn — ô phụ của từng mốc (lý do huỷ,
mã vận đơn, kết quả đổi trả...) không còn; mẫu ZNS cần các ô đó sẽ báo thiếu và chuyển sang kênh dự phòng."""

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
from app.integrations import notify as notify_api
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

MAX_ATTEMPTS = 3
CHANNEL_LABELS = {Channel.ZALO_OA: "Zalo", Channel.EMAIL: "Email", Channel.SMS: "SMS", Channel.FACEBOOK: "Messenger"}

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

CARRIER_NAMES = {
    "ghn": "Giao Hàng Nhanh",
    "ghtk": "Giao Hàng Tiết Kiệm",
    "mock": "hãng giao (thử)",
    "self": "Hàng Chọn (tự giao)",
}


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
    values = {**base_values(order, drop_arrival=drop_arrival), **(extra or {})}
    body = render(templates[key], values)
    candidates = await _candidates(db, order)
    channel, recipient = candidates[0] if candidates else (await _primary_channel(db), None)
    n = Notification(
        customer_id=order.customer_id,
        order_id=order.id,
        event=EVENT_OF.get(key, NotificationEvent.OTHER),
        channel=channel,
        recipient=recipient or "",
        subject=f"{settings.app_name}: {TEMPLATE_LABELS.get(key, 'Thông báo')} · đơn {order.code}"[:200],
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
    await deliver(db, n, candidates=candidates, values=values, order=order)
    return n


async def _primary_channel(db: AsyncSession) -> Channel:
    return Channel(await control.get_setting(db, "orders.notify_channel") or Channel.ZALO_OA.value)


async def _candidates(db: AsyncSession, order: Order) -> list[tuple[Channel, str]]:
    """Các (kênh, người nhận) theo thứ tự ưu tiên: kênh chính rồi kênh dự phòng; bỏ kênh khách không có định danh."""
    channels = [await _primary_channel(db)]
    for raw in await control.get_setting(db, "orders.notify_fallback_channels") or []:
        try:
            ch = Channel(str(raw))
        except ValueError:
            continue
        if ch not in channels:
            channels.append(ch)
    out: list[tuple[Channel, str]] = []
    for ch in channels:
        to = await _recipient(db, order, ch)
        if to:
            out.append((ch, to))
    return out


def _key_of(n: Notification) -> str | None:
    parts = (n.dedupe_key or "").split(":")
    return parts[2] if len(parts) > 2 and parts[0] == "order" else None


async def deliver(
    db: AsyncSession,
    n: Notification,
    *,
    candidates: list[tuple[Channel, str]] | None = None,
    values: dict[str, Any] | None = None,
    order: Order | None = None,
) -> None:
    """Gửi một tin đã giữ chỗ, thử lần lượt các kênh. Lần gửi lại (cron) chỉ có `n`: dựng lại kênh + ô mẫu từ đơn."""
    n.attempts += 1
    if order is None and n.order_id:
        order = await db.get(Order, n.order_id)
    if candidates is None:
        candidates = (await _candidates(db, order)) if order else []
        if (n.channel, n.recipient) not in candidates and n.recipient:
            candidates.insert(0, (n.channel, n.recipient))
    if values is None:
        values = base_values(order) if order else {}
    data = {k: "" if v is None else str(v) for k, v in values.items()}
    if order and order.recipient_phone:
        data.setdefault("phone", order.recipient_phone)
    errors: list[str] = []
    retryable = False
    for channel, to in candidates:
        msg = OutboundNotification(
            channel=channel,
            to=to,
            text=n.body,
            subject=n.subject,
            kind=_key_of(n),
            data=data,
            link_url=data.get("link"),
        )
        try:
            res = await notify_api.send(msg)
        except Exception as e:  # driver lỗi bất ngờ: không làm hỏng luồng đơn
            log.warning("Gửi tin %s qua %s lỗi: %s", n.dedupe_key, channel.value, e)
            res = notify_api.failed(str(getattr(e, "message", e)), retryable=True)
        if res.status in ("sent", "queued"):
            n.channel, n.recipient = channel, to
            n.status = NotificationStatus.SENT
            n.external_id = res.external_id
            n.sent_at = res.sent_at or now_utc()
            n.error = "; ".join(errors)[:500] or None  # ghi lại kênh đã lỗi trước khi sang kênh dự phòng
            await db.flush()
            return
        errors.append(f"{CHANNEL_LABELS.get(channel, channel.value)}: {res.error or 'lỗi không rõ'}")
        retryable = retryable or res.retryable
    n.status = NotificationStatus.FAILED
    n.error = "; ".join(errors)[:500] or "Khách chưa có kênh nhận tin."
    if not retryable:
        n.attempts = max(n.attempts, MAX_ATTEMPTS)  # lỗi vĩnh viễn ở mọi kênh: cron không gửi lại
    await db.flush()


async def channel_status(db: AsyncSession) -> list[dict[str, Any]]:
    """Kênh đang bật cho màn mẫu tin: kênh chính + dự phòng, driver từng kênh, đủ cấu hình chưa."""
    from app.integrations import IntegrationNotConfigured

    primary = await _primary_channel(db)
    channels: list[tuple[Channel, str]] = [(primary, "primary")]
    for raw in await control.get_setting(db, "orders.notify_fallback_channels") or []:
        try:
            ch = Channel(str(raw))
        except ValueError:
            continue
        if all(ch != c for c, _ in channels):
            channels.append((ch, "fallback"))
    out = []
    for ch, role in channels:
        name = notify_api.driver_name_for(ch)
        try:
            driver = notify_api.driver_for(ch)
        except IntegrationNotConfigured as e:
            note: str | None = e.message
        else:
            if driver.channels and ch not in driver.channels:
                note = f"Driver «{name}» không gửi được kênh này."
            elif name == "mock":
                note = "Driver giả (mock): tin chỉ ghi lại, không tới khách thật."
            else:
                note = driver.missing_config()
        out.append({"channel": ch, "label": CHANNEL_LABELS.get(ch, ch.value), "role": role, "driver": name,
                    "ready": note is None, "note": note})  # fmt: skip
    return out


async def recent_failures(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Notification, Order.code)
            .outerjoin(Order, Order.id == Notification.order_id)
            .where(Notification.status == NotificationStatus.FAILED)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": n.id, "order_id": n.order_id, "order_code": code,
            "event_label": TEMPLATE_LABELS.get(_key_of(n) or "", "Tin khác"),
            "channel": n.channel, "recipient": n.recipient, "error": n.error, "attempts": n.attempts,
            "will_retry": n.attempts < MAX_ATTEMPTS and bool(n.recipient), "created_at": n.created_at,
        }
        for n, code in rows
    ]  # fmt: skip
