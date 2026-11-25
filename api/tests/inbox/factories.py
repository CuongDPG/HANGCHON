"""Tạo dữ liệu thử cho test inbox/crm (sản phẩm, đợt, khách, đơn). Tên đều là ví dụ."""

from __future__ import annotations

import itertools
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.modules.catalog.models import Drop, DropItem, DropStatus, InventoryItem, Product, ProductStatus
from app.modules.inbox.models import AccountStatus, ChannelAccount
from app.modules.orders.models import Customer, CustomerIdentity, Order, OrderItem, OrderStatus

_n = itertools.count(1)


async def accounts(db: AsyncSession) -> None:
    for ch in (Channel.FACEBOOK, Channel.INSTAGRAM, Channel.ZALO_OA):
        db.add(
            ChannelAccount(channel=ch, name=f"{ch} giả", external_id=f"mock_{ch.value}_page", status=AccountStatus.MOCK)
        )
    await db.flush()


async def product(
    db: AsyncSession,
    name: str = "Bình giữ nhiệt 480 ml",
    price: int = 385_000,
    *,
    stock: int | None = None,
    consumable: bool = False,
    reorder_days: int | None = None,
) -> Product:
    n = next(_n)
    p = Product(
        slug=f"sp-{n}",
        name=name,
        price_vnd=price,
        status=ProductStatus.PUBLISHED,
        published_at=now_utc(),
        short_description="Giữ nóng 9 tiếng, nắp không ám mùi",
        not_satisfied="Hơi nặng khi đầy nước",
        is_consumable=consumable,
        reorder_days=reorder_days,
    )
    db.add(p)
    await db.flush()
    if stock is not None:
        db.add(InventoryItem(product_id=p.id, on_hand=stock))
        await db.flush()
    return p


async def open_drop(db: AsyncSession, p: Product, *, slots: int = 120, reserved: int = 86) -> Drop:
    n = next(_n)
    d = Drop(
        code=f"D{n}",
        slug=f"dot-{n}",
        title=f"Đợt {n}",
        status=DropStatus.OPEN,
        opens_at=now_utc(),
        closes_at=now_utc() + timedelta(days=2),
        expected_arrival_date=date.today() + timedelta(days=14),
    )
    db.add(d)
    await db.flush()
    db.add(DropItem(drop_id=d.id, product_id=p.id, price_vnd=p.price_vnd, slots_total=slots, slots_reserved=reserved))
    await db.flush()
    return d


async def customer(
    db: AsyncSession,
    name: str = "Thu Hà",
    phone: str | None = None,
    *,
    orders: int = 0,
    email: str | None = None,
    identity: tuple[Channel, str] | None = None,
    marketing_opt_in: bool = True,
) -> Customer:
    n = next(_n)
    c = Customer(
        name=name, phone=phone or f"09{n:08d}", email=email, order_count=orders, total_spent_vnd=orders * 300_000,
        marketing_opt_in=marketing_opt_in,
    )  # fmt: skip
    db.add(c)
    await db.flush()
    if identity:
        db.add(CustomerIdentity(customer_id=c.id, channel=identity[0], external_id=identity[1], display_name=name))
        await db.flush()
    return c


async def order(
    db: AsyncSession,
    c: Customer,
    p: Product,
    *,
    qty: int = 1,
    status: OrderStatus = OrderStatus.CONFIRMED,
    referral_code: str | None = None,
    delivered: bool = False,
) -> Order:
    n = next(_n)
    now = now_utc()
    o = Order(
        code=f"HC{n:06d}",
        customer_id=c.id,
        channel=Channel.WEB,
        status=OrderStatus.DELIVERED if delivered else status,
        recipient_name=c.name or "Khách",
        recipient_phone=c.phone or "0900000000",
        subtotal_vnd=p.price_vnd * qty,
        total_vnd=p.price_vnd * qty,
        placed_at=now - timedelta(days=3),
        delivered_at=now if delivered else None,
        referral_code=referral_code,
    )
    o.items = [
        OrderItem(
            product_id=p.id, name=p.name, quantity=qty, unit_price_vnd=p.price_vnd, line_total_vnd=p.price_vnd * qty
        )
    ]
    db.add(o)
    await db.flush()
    return o
