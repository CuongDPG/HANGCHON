"""Dựng dữ liệu trả về cho bàn làm việc (desk)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ShippingStatus
from app.modules.catalog.models import Drop
from app.modules.orders import refs, service
from app.modules.orders.models import (
    Customer,
    Notification,
    Order,
    OrderEvent,
    OrderStatus,
    Payment,
    Return,
    Shipment,
    ShipmentEvent,
)
from app.modules.orders.schemas import (
    CustomerOut,
    NotificationOut,
    OrderDetailOut,
    OrderEventOut,
    OrderItemOut,
    PaymentOut,
    PaymentRowOut,
    ReturnOut,
    ShipmentEventOut,
    ShipmentOut,
    ShipmentWithEvents,
)
from app.modules.orders.shipping import FINAL
from app.modules.orders.util import order_access_token


async def order_detail(db: AsyncSession, order: Order) -> OrderDetailOut:
    evs = list(
        (
            await db.execute(
                select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.occurred_at.desc())
            )
        ).scalars()
    )
    pays = list(
        (
            await db.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.received_at.desc()))
        ).scalars()
    )
    ships = list(
        (
            await db.execute(select(Shipment).where(Shipment.order_id == order.id).order_by(Shipment.created_at.desc()))
        ).scalars()
    )
    ship_events = {
        s.id: list(
            (
                await db.execute(
                    select(ShipmentEvent)
                    .where(ShipmentEvent.shipment_id == s.id)
                    .order_by(ShipmentEvent.occurred_at.desc())
                )
            ).scalars()
        )
        for s in ships
    }
    notes = list(
        (
            await db.execute(
                select(Notification).where(Notification.order_id == order.id).order_by(Notification.created_at.desc())
            )
        ).scalars()
    )
    rets = list(
        (
            await db.execute(select(Return).where(Return.order_id == order.id).order_by(Return.created_at.desc()))
        ).scalars()
    )
    drop = await db.get(Drop, order.drop_id) if order.drop_id else None
    customer = await db.get(Customer, order.customer_id) if order.customer_id else None
    active = any(s.status not in FINAL for s in ships)
    base = OrderDetailOut.model_validate(
        {
            **{
                k: getattr(order, k)
                for k in OrderDetailOut.model_fields
                if k not in ("items", "events", "drop", "customer", "payments", "shipments", "notifications", "returns")
                and hasattr(order, k)
            },
            "status_label": service.STATUS_LABELS[order.status],
            "items": [OrderItemOut.model_validate(i) for i in order.items],
            "events": [OrderEventOut.model_validate(e) for e in evs],
            "payments": [PaymentOut.model_validate(p) for p in pays],
            "shipments": [
                ShipmentWithEvents(
                    **ShipmentOut.model_validate(s).model_dump(),
                    events=[ShipmentEventOut.model_validate(e) for e in ship_events[s.id]],
                )
                for s in ships
            ],
            "notifications": [NotificationOut.model_validate(n) for n in notes],
            "returns": [ReturnOut.model_validate(r) for r in rets],
            "drop": refs.drop_brief(drop),
            "customer": CustomerOut.model_validate(customer) if customer else None,
            "public_url": f"{settings.web_base_url.rstrip('/')}/don/{order.code}?t={order_access_token(order.id)}",
            "missing_info": service.missing_info(order) if order.status == OrderStatus.DRAFT else [],
            "amount_due_vnd": service.amount_due(order),
            "can_cancel": order.status in service.CANCELLABLE and not active,
            "can_ship": order.status == OrderStatus.READY_TO_SHIP and not active,
            "can_edit_address": order.status in service.ADDRESS_EDITABLE
            and not any(s.status != ShippingStatus.CANCELLED and s.status not in FINAL for s in ships),
        }
    )
    return base


async def payment_rows(db: AsyncSession, rows: list[Payment]) -> list[PaymentRowOut]:
    ids = {p.order_id for p in rows if p.order_id}
    codes = dict((await db.execute(select(Order.id, Order.code).where(Order.id.in_(ids)))).all()) if ids else {}
    return [PaymentRowOut(**PaymentOut.model_validate(p).model_dump(), order_code=codes.get(p.order_id)) for p in rows]
