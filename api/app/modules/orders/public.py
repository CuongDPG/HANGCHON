"""Trang theo dõi đơn cho khách (e5): hành trình gồm cả chặng hàng từ nước ngoài về (đọc `inbound_shipments`
của đợt, chỉ đọc), thông tin chuyển khoản VietQR, đổi địa chỉ khi chưa giao."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.enums import Channel, ShippingStatus
from app.core.timeutil import to_local
from app.integrations import get_driver
from app.modules.catalog.models import Drop, DropStatus
from app.modules.orders import refs, service
from app.modules.orders.models import (
    Order,
    OrderEvent,
    OrderStatus,
    PaymentMethod,
    Return,
    Shipment,
)
from app.modules.orders.returns import OPEN_STATUSES
from app.modules.orders.schemas import (
    PaymentInfo,
    PublicEvent,
    PublicItem,
    PublicOrderOut,
    PublicReturn,
    PublicReviewLink,
    PublicShipment,
    TimelineStep,
)
from app.modules.orders.shipping import FINAL
from app.modules.orders.util import code_suffix, order_access_token
from app.modules.supply.models import InboundStatus

CLOSED_DROP = (DropStatus.CLOSED, DropStatus.SOURCING, DropStatus.ARRIVING, DropStatus.FULFILLING, DropStatus.COMPLETED)
AFTER_ARRIVAL = (OrderStatus.READY_TO_SHIP, OrderStatus.SHIPPING, OrderStatus.DELIVERED, OrderStatus.COMPLETED)


def _d(v: date | None) -> str | None:
    return v.strftime("%d/%m") if v else None


async def payment_info(order: Order) -> PaymentInfo | None:
    if order.payment_method != PaymentMethod.BANK_TRANSFER:
        return PaymentInfo(
            method=order.payment_method, transfer_content=None, bank_code=None, account_no=None, account_name=None,
            amount_due_vnd=order.cod_amount_vnd, qr_url=None, qr_payload=None, due_at=None,
        )  # fmt: skip
    due = service.amount_due(order)
    if due <= 0:
        return PaymentInfo(
            method=order.payment_method, transfer_content=order.transfer_content, bank_code=None, account_no=None,
            account_name=None, amount_due_vnd=0, qr_url=None, qr_payload=None, due_at=None,
        )  # fmt: skip
    req = await get_driver("payments").create_request(code_suffix(order.code), due)
    return PaymentInfo(
        method=order.payment_method, transfer_content=order.transfer_content or req.transfer_content,
        bank_code=req.bank_code, account_no=req.account_no, account_name=req.account_name, amount_due_vnd=due,
        qr_url=f"/api/store/orders/{order.code}/qr.svg?t={order_access_token(order.id)}", qr_payload=req.qr_payload,
        due_at=order.payment_due_at,
    )  # fmt: skip


def _finish(steps: list[TimelineStep], *, stop: bool = False) -> list[TimelineStep]:
    if not stop and not any(s.status == "current" for s in steps):
        for s in steps:
            if s.status == "todo":
                s.status = "current"
                break
    return steps


async def timeline(
    db: AsyncSession, order: Order, drop: Drop | None, sh: Shipment | None
) -> tuple[list[TimelineStep], str]:
    evs = list(
        (
            await db.execute(select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.occurred_at))
        ).scalars()
    )
    first = {e.kind: e for e in reversed(evs)}  # mốc sớm nhất của mỗi loại
    paid = order.paid_at is not None
    steps: list[TimelineStep] = []
    pay_meta = {PaymentMethod.COD: "Trả tiền khi nhận hàng", PaymentMethod.MARKETPLACE: "Sàn thu hộ"}.get(
        order.payment_method
    )
    steps.append(
        TimelineStep(
            key="placed",
            title="Đã nhận đơn"
            + (", đã thanh toán" if paid and order.payment_method == PaymentMethod.BANK_TRANSFER else ""),
            status="done",
            at=order.placed_at,
            meta=pay_meta,
        )
    )
    if order.status == OrderStatus.CANCELLED:
        steps.append(
            TimelineStep(
                key="cancelled", title="Đơn đã huỷ", status="done", at=order.cancelled_at, meta=order.cancel_reason
            )
        )
        return steps, "Đơn đã huỷ"
    if order.payment_method == PaymentMethod.BANK_TRANSFER and not paid:
        due = to_local(order.payment_due_at).strftime("%H:%M %d/%m") if order.payment_due_at else None
        steps.append(
            TimelineStep(
                key="payment",
                title="Chờ bạn chuyển khoản",
                status="current",
                meta=f"Giữ suất tới {due}" if due else None,
            )
        )

    headline = "Đã nhận đơn"
    lots = await refs.inbound_for_drop(db, drop.id) if drop else []
    eta = refs.eta_of(drop, lots)
    arrived = (
        order.status in AFTER_ARRIVAL
        or order.status == OrderStatus.RETURNED
        or (drop is not None and await refs.drop_arrived(db, drop))
    )
    if drop is not None:
        closed = drop.status in CLOSED_DROP or "drop_closed" in first
        headline = "Chị đã đặt nhà cung cấp, chờ hàng về" if closed else f"Đã giữ suất, chờ chốt đợt {drop.code}"
        ev = first.get("drop_closed")
        steps.append(TimelineStep(
            key="drop", title=f"Chốt đợt {drop.code}, đã đặt nhà cung cấp" if closed else f"Chốt đợt {drop.code}",
            status="done" if closed else "todo", at=ev.occurred_at if ev else None,
            meta=None if closed else (f"Đợt chốt {to_local(drop.closes_at).strftime('%d/%m')}" if drop.closes_at else None),
        ))  # fmt: skip
        lot = refs.slowest(lots)
        lot_in_at: datetime | None = None
        if lot is not None and lot.status != InboundStatus.ORDERED:
            if lot.status != InboundStatus.DELIVERED and not arrived:
                brief = refs.inbound_brief(lot)
                steps.append(TimelineStep(key="inbound", title=brief.last_note or brief.status_label,
                                          status="current", at=brief.last_at))  # fmt: skip
                headline = brief.status_label
            else:
                # Hàng đã về: mốc «về tới kho» thuộc bước «arrived» bên dưới (một mốc chỉ ghi một lần);
                # chặng đường về chỉ còn phần vận chuyển.
                lot_in_at = refs.last_milestone_at(lot, {InboundStatus.DELIVERED})
                transit_at = refs.last_milestone_at(lot, refs.TRANSIT_STATUSES)
                if transit_at is not None:
                    steps.append(TimelineStep(key="inbound", title="Hàng đã về Việt Nam", status="done", at=transit_at))
        elif not arrived:
            steps.append(TimelineStep(key="inbound", title="Hàng trên đường về Việt Nam", status="todo"))
        steps.append(TimelineStep(
            key="arrived", title="Về tới kho, chị kiểm từng món", status="done" if arrived else "todo",
            at=next((e.occurred_at for e in evs if e.status == OrderStatus.READY_TO_SHIP), None) or lot_in_at,
            meta=None if arrived else (f"Dự kiến {_d(eta)}" if eta else None),
        ))  # fmt: skip
    else:
        packed = sh is not None or order.status in (OrderStatus.SHIPPING, OrderStatus.DELIVERED, OrderStatus.COMPLETED)
        steps.append(
            TimelineStep(
                key="packing",
                title="Chị đóng gói",
                status="done" if packed else "todo",
                at=sh.created_at if sh else None,
            )
        )
    delivered = order.status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED)
    carrier_meta = f"Mã vận đơn {sh.tracking_code}" if sh and sh.tracking_code else None
    if order.status == OrderStatus.RETURNED:
        steps.append(TimelineStep(key="returned", title="Hàng đã hoàn về chị", status="done"))
        return _finish(steps, stop=True), "Đơn đã hoàn về"
    if delivered:
        steps.append(
            TimelineStep(
                key="delivered", title="Đã giao cho bạn", status="done", at=order.delivered_at, meta=carrier_meta
            )
        )
        headline = "Đã giao xong"
    elif order.status == OrderStatus.SHIPPING:
        out_for = sh is not None and sh.status == ShippingStatus.OUT_FOR_DELIVERY
        steps.append(
            TimelineStep(
                key="shipping",
                title="Đang giao tới bạn" if out_for else "Đã giao cho hãng vận chuyển",
                status="current",
                at=order.shipped_at,
                meta=carrier_meta,
            )
        )
        steps.append(TimelineStep(key="delivered", title="Giao cho bạn", status="todo"))
        headline = "Đang giao tới bạn"
    else:
        hint = None
        if drop is not None and eta and not arrived:
            hint = f"Dự kiến {_d(eta + timedelta(days=1))}–{_d(eta + timedelta(days=3))}"
        steps.append(TimelineStep(key="delivered", title="Giao cho bạn", status="todo", meta=hint))
        if order.status == OrderStatus.READY_TO_SHIP:
            headline = "Chị đang chuẩn bị gói hàng"
    if order.payment_method == PaymentMethod.BANK_TRANSFER and not paid:
        headline = "Chờ bạn chuyển khoản"
    return _finish(steps), headline


async def public_view(db: AsyncSession, order: Order) -> PublicOrderOut:
    drop = await db.get(Drop, order.drop_id) if order.drop_id else None
    products = await refs.products_by_id(db, [i.product_id for i in order.items])
    images = await refs.primary_images(db, products.keys())
    sh = (
        await db.execute(
            select(Shipment)
            .where(Shipment.order_id == order.id, Shipment.status != ShippingStatus.CANCELLED)
            .order_by(Shipment.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    steps, headline = await timeline(db, order, drop, sh)
    visible = list(
        (
            await db.execute(
                select(OrderEvent)
                .where(OrderEvent.order_id == order.id, OrderEvent.visible_to_customer.is_(True))
                .order_by(OrderEvent.occurred_at.desc())
            )
        ).scalars()
    )
    rets = list(
        (
            await db.execute(select(Return).where(Return.order_id == order.id).order_by(Return.created_at.desc()))
        ).scalars()
    )
    from app.modules.catalog.models import Review, ReviewStatus  # chỉ đọc

    review_rows = (
        (await db.execute(select(Review).where(Review.order_id == order.id).order_by(Review.created_at)))
        .scalars()
        .all()
        if order.status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED)
        else []
    )
    names = {i.id: i.name for i in order.items}
    marketplace = order.channel in (Channel.TIKTOK_SHOP, Channel.SHOPEE)
    active_ship = sh is not None and sh.status not in FINAL
    notify_on = await control.get_setting(db, "orders.notify_enabled") is not False
    channel = await control.get_setting(db, "orders.notify_channel") or "zalo_oa"
    hint_channel = {"zalo_oa": "tin nhắn Zalo", "sms": "tin nhắn SMS", "email": "email"}.get(channel, "tin nhắn")
    return PublicOrderOut(
        code=order.code, token=order_access_token(order.id), status=order.status,
        status_label=service.STATUS_LABELS[order.status], headline=headline, channel=order.channel,
        payment_method=order.payment_method, payment_state=order.payment_state,
        items=[
            PublicItem(
                name=i.name, variant_name=i.variant_name, quantity=i.quantity, unit_price_vnd=i.unit_price_vnd,
                line_total_vnd=i.line_total_vnd, image_url=images.get(i.product_id) if i.product_id else None,
                slug=products[i.product_id].slug if i.product_id in products else None,
            )
            for i in order.items
        ],
        subtotal_vnd=order.subtotal_vnd, shipping_fee_vnd=order.shipping_fee_vnd, discount_vnd=order.discount_vnd,
        total_vnd=order.total_vnd, paid_vnd=order.paid_vnd, refunded_vnd=order.refunded_vnd,
        deposit_required_vnd=order.deposit_required_vnd, cod_amount_vnd=order.cod_amount_vnd,
        recipient_name=order.recipient_name, recipient_phone=order.recipient_phone, address_line=order.address_line,
        ward=order.ward, district=order.district, province=order.province, customer_note=order.customer_note,
        placed_at=order.placed_at, payment=await payment_info(order), drop=refs.drop_brief(drop), timeline=steps,
        events=[PublicEvent(title=e.title, detail=e.detail, occurred_at=e.occurred_at) for e in visible[:20]],
        shipment=PublicShipment(carrier=sh.carrier, tracking_code=sh.tracking_code, status=sh.status) if sh else None,
        returns=[PublicReturn(code=r.code, kind=r.kind, status=r.status, created_at=r.created_at) for r in rets],
        can_change_address=order.status in service.ADDRESS_EDITABLE and not active_ship and not marketplace and order.status != OrderStatus.DRAFT,
        can_request_return=order.status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED) and not any(r.status in OPEN_STATUSES for r in rets),
        notify_hint=f"Mỗi mốc bạn sẽ nhận một {hint_channel}." if notify_on and not marketplace else None,
        reviews=[
            PublicReviewLink(name=names.get(r.order_item_id, "Món đã nhận"), token=r.token, status=r.status.value)
            for r in review_rows if r.status in (ReviewStatus.REQUESTED, ReviewStatus.SUBMITTED,
                                                 ReviewStatus.PENDING_REVIEW, ReviewStatus.PUBLISHED)
        ],
    )  # fmt: skip
