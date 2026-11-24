"""Dữ liệu thử cho finance: đơn đã thanh toán (bảng của orders — chỉ test mới ghi thẳng), chạy sự kiện như orders phát."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.timeutil import now_utc
from app.modules.orders.models import Customer, Order, OrderItem, OrderStatus, PaymentState

_n = 0


async def make_customer(db: AsyncSession, name: str = "Khách Thử") -> Customer:
    global _n
    _n += 1
    c = Customer(name=name, phone=f"09000000{_n:02d}")
    db.add(c)
    await db.flush()
    return c


async def make_order(
    db: AsyncSession,
    *,
    items: list[tuple[str, int, int, int | None]] = (("Bình giữ nhiệt 480 ml", 1, 245_000, 160_000),),  # type: ignore[assignment]
    shipping: int = 30_000,
    discount: int = 0,
    customer: Customer | None = None,
    paid: bool = True,
    paid_at: datetime | None = None,
    placed_at: datetime | None = None,
    product_id: uuid.UUID | None = None,
) -> Order:
    """items: (tên, số lượng, đơn giá, giá vốn hoặc None)."""
    global _n
    _n += 1
    subtotal = sum(q * p for _, q, p, _ in items)
    when = paid_at or now_utc()
    o = Order(
        code=f"HCT{_n:06d}",
        customer_id=customer.id if customer else None,
        recipient_name="Nguyễn Thị Thử",
        recipient_phone="0900000000",
        address_line="12 Ngõ Thử",
        province="Hà Nội",
        status=OrderStatus.CONFIRMED if paid else OrderStatus.PENDING_PAYMENT,
        payment_state=PaymentState.PAID if paid else PaymentState.UNPAID,
        subtotal_vnd=subtotal,
        shipping_fee_vnd=shipping,
        discount_vnd=discount,
        total_vnd=subtotal + shipping - discount,
        paid_vnd=subtotal + shipping - discount if paid else 0,
        placed_at=placed_at or when - timedelta(hours=1),
        paid_at=when if paid else None,
    )
    for i, (name, q, price, cost) in enumerate(items):
        o.items.append(
            OrderItem(
                position=i,
                name=name,
                quantity=q,
                unit_price_vnd=price,
                line_total_vnd=q * price,
                unit_cost_vnd=cost,
                product_id=product_id,
            )
        )
    db.add(o)
    await db.flush()
    return o


async def pay(db: AsyncSession, order: Order) -> None:
    """Như orders phát `order.paid` khi khớp tiền."""
    await events.emit("order.paid", {"order_id": str(order.id), "payment_id": None}, db=db)
