"""Đợt gom (g3), hàng đang về, tồn kho nhỏ (g8) — phía orders.

- `drop.closed` → chốt danh sách đơn của đợt (ghi hành trình từng đơn). Số lượng theo món: bên supply tự đọc
  `order_items`; chị xem ở màn hình đợt (`overview`).
- `inbound.arrived` → mọi lô của đợt đã về thì đơn của đợt chuyển sang chờ giao.
- Lô đang trên đường về → báo khách «hàng đang về» một lần.
- Tồn kho thuộc catalog: orders chỉ đọc, cảnh báo sắp hết → việc chờ chị."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.modules.catalog.models import Drop, DropStatus, InventoryItem, Product, ProductVariant
from app.modules.orders import notify, refs, service
from app.modules.orders.models import FulfillmentSource, Notification, Order, OrderEvent, OrderItem, OrderStatus
from app.modules.orders.schemas import DropItemStat, DropOverview, InventoryRow
from app.modules.supply.models import InboundShipment, PurchaseOrder

log = logging.getLogger("app.orders.drops")

LOW_STOCK_ACTION = "orders.restock_alert"
CONFIRMED_LIKE = (
    OrderStatus.CONFIRMED,
    OrderStatus.AWAITING_STOCK,
    OrderStatus.READY_TO_SHIP,
    OrderStatus.SHIPPING,
    OrderStatus.DELIVERED,
    OrderStatus.COMPLETED,
)


async def overview(db: AsyncSession, drop: Drop) -> DropOverview:
    rows = (
        await db.execute(
            select(OrderItem.drop_item_id, Order.status, func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.drop_id == drop.id, Order.status.not_in(service.NOT_HOLDING))
            .group_by(OrderItem.drop_item_id, Order.status)
        )
    ).all()
    confirmed: dict[uuid.UUID, int] = {}
    pending: dict[uuid.UUID, int] = {}
    for di_id, status, qty in rows:
        target = pending if status == OrderStatus.PENDING_PAYMENT else confirmed
        target[di_id] = target.get(di_id, 0) + int(qty)
    orders = dict(
        (
            await db.execute(
                select(Order.status, func.count())
                .where(Order.drop_id == drop.id, Order.status.not_in(service.NOT_HOLDING))
                .group_by(Order.status)
            )
        ).all()
    )
    revenue = int(
        await db.scalar(
            select(func.coalesce(func.sum(Order.total_vnd), 0)).where(
                Order.drop_id == drop.id, Order.status.in_(CONFIRMED_LIKE)
            )
        )
        or 0
    )
    products = await refs.products_by_id(db, [di.product_id for di in drop.items])
    variants = {
        v.id: v.name
        for v in (await db.execute(select(ProductVariant).where(ProductVariant.product_id.in_(products.keys())))).scalars()
    } if products else {}  # fmt: skip
    items = []
    for di in drop.items:
        p = products.get(di.product_id)
        name = (p.name if p else "Món đã xoá") + (f" · {variants[di.variant_id]}" if di.variant_id in variants else "")
        items.append(
            DropItemStat(
                drop_item_id=di.id,
                product_id=di.product_id,
                variant_id=di.variant_id,
                name=name,
                price_vnd=di.price_vnd or (p.price_vnd if p else 0),
                slots_total=di.slots_total,
                quantity_confirmed=confirmed.get(di.id, 0),
                quantity_pending=pending.get(di.id, 0),
                min_total_to_order=di.min_total_to_order,
            )
        )
    totals = [di.slots_total for di in drop.items]
    lots = await refs.inbound_for_drop(db, drop.id)
    return DropOverview(
        id=drop.id, code=drop.code, title=drop.title, status=drop.status.value, closes_at=drop.closes_at,
        expected_arrival_date=refs.eta_of(drop, lots), orders_total=sum(orders.values()),
        orders_confirmed=sum(v for k, v in orders.items() if k != OrderStatus.PENDING_PAYMENT),
        orders_pending=orders.get(OrderStatus.PENDING_PAYMENT, 0), revenue_vnd=revenue,
        slots_total=None if any(t is None for t in totals) or not totals else sum(t or 0 for t in totals),
        slots_taken=sum(confirmed.values()) + sum(pending.values()), items=items,
        inbound=[refs.inbound_brief(s) for s in lots],
    )  # fmt: skip


async def active_drops(db: AsyncSession) -> list[Drop]:
    """Đợt cần chị để ý: đang mở, đã chốt, đang đặt nguồn, hàng đang về, đang giao."""
    keep = (DropStatus.OPEN, DropStatus.CLOSED, DropStatus.SOURCING, DropStatus.ARRIVING, DropStatus.FULFILLING)
    return list(
        (
            await db.execute(select(Drop).where(Drop.status.in_(keep)).order_by(Drop.closes_at.asc().nulls_last()))
        ).scalars()
    )


async def on_drop_closed(db: AsyncSession, drop_id: uuid.UUID) -> int:
    """Chốt danh sách đơn của đợt: mỗi đơn đang giữ suất ghi một mốc «đã chốt đợt». Gọi lặp không ghi trùng."""
    drop = await db.get(Drop, drop_id)
    if drop is None:
        return 0
    orders = list(
        (
            await db.execute(select(Order).where(Order.drop_id == drop_id, Order.status.not_in(service.NOT_HOLDING)))
        ).scalars()
    )
    done = set(
        (
            await db.execute(
                select(OrderEvent.order_id).where(
                    OrderEvent.order_id.in_([o.id for o in orders]), OrderEvent.kind == "drop_closed"
                )
            )
        ).scalars()
    ) if orders else set()  # fmt: skip
    n = 0
    for o in orders:
        if o.id in done:
            continue
        service.add_event(
            db, o, "drop_closed", f"Chốt đợt {drop.code}, chị đặt nhà cung cấp",
            data={"drop_id": str(drop.id)},
        )  # fmt: skip
        n += 1
    await db.flush()
    return n


async def on_inbound_arrived(db: AsyncSession, inbound_id: uuid.UUID) -> int:
    """Lô hàng về tới kho. Mọi lô của đợt đã về → đơn chờ hàng chuyển sang chờ giao. Trả số đơn đã chuyển."""
    lot = await db.get(InboundShipment, inbound_id)
    if lot is None or lot.purchase_order_id is None:
        return 0
    po = await db.get(PurchaseOrder, lot.purchase_order_id)
    if po is None or po.drop_id is None:
        return 0
    drop = await db.get(Drop, po.drop_id)
    if drop is None:
        return 0
    orders = list(
        (
            await db.execute(
                select(Order).where(
                    Order.drop_id == drop.id, Order.status.in_((OrderStatus.CONFIRMED, OrderStatus.AWAITING_STOCK))
                )
            )
        ).scalars()
    )
    if not await refs.drop_arrived(db, drop):
        for o in orders:  # một lô về, còn lô khác: chỉ ghi mốc
            exists = await db.scalar(
                select(func.count()).where(
                    OrderEvent.order_id == o.id, OrderEvent.kind == "inbound_lot_arrived",
                    OrderEvent.data["inbound_id"].astext == str(lot.id),
                )
            )  # fmt: skip
            if not exists:
                service.add_event(
                    db, o, "inbound_lot_arrived", "Một phần hàng đã về kho, chờ nốt lô còn lại",
                    data={"inbound_id": str(lot.id)},
                )  # fmt: skip
        await db.flush()
        return 0
    n = 0
    for o in orders:
        if service.set_status(db, o, OrderStatus.READY_TO_SHIP, "Hàng đã về tới kho, chị kiểm từng món rồi gửi bạn"):
            n += 1
    await db.flush()
    return n


async def notify_arriving(db: AsyncSession) -> int:
    """Báo «hàng đang về» một lần cho mỗi đơn khi lô của đợt bắt đầu về Việt Nam."""
    rows = list(
        (
            await db.execute(
                select(Order).where(Order.status == OrderStatus.AWAITING_STOCK, Order.drop_id.is_not(None))
            )
        ).scalars()
    )
    by_drop: dict[uuid.UUID, list[Order]] = {}
    for o in rows:
        by_drop.setdefault(o.drop_id, []).append(o)  # type: ignore[arg-type]
    n = 0
    for drop_id, orders in by_drop.items():
        lots = await refs.inbound_for_drop(db, drop_id)
        if not lots or not any(s.status in refs.TRANSIT_STATUSES for s in lots):
            continue
        drop = await db.get(Drop, drop_id)
        eta = refs.eta_of(drop, lots)
        for o in orders:
            before = await db.scalar(
                select(func.count()).where(Notification.dedupe_key == f"order:{o.id}:stock_arriving")
            )
            await notify.notify_order(db, o, "stock_arriving", drop_arrival=eta.strftime("%d/%m") if eta else None)
            n += 0 if before else 1
    return n


# ---- tồn kho nhỏ (g8) ----------------------------------------------------------------------------------------------


async def inventory_rows(db: AsyncSession) -> list[InventoryRow]:
    items = list((await db.execute(select(InventoryItem))).scalars())
    products = await refs.products_by_id(db, [i.product_id for i in items])
    variant_ids = [i.variant_id for i in items if i.variant_id]
    variants = (
        {
            v.id: v.name
            for v in (await db.execute(select(ProductVariant).where(ProductVariant.id.in_(variant_ids)))).scalars()
        }
        if variant_ids
        else {}
    )
    default_threshold = int(await control.get_setting(db, "orders.low_stock_default_threshold") or 3)
    out = []
    for inv in items:
        held = await service.pending_stock_qty(db, inv.product_id, inv.variant_id)
        available = inv.on_hand - inv.reserved - held
        threshold = inv.low_stock_threshold if inv.low_stock_threshold is not None else default_threshold
        p: Product | None = products.get(inv.product_id)
        name = (p.name if p else "Món đã xoá") + (
            f" · {variants[inv.variant_id]}" if inv.variant_id in variants else ""
        )
        out.append(
            InventoryRow(
                inventory_item_id=inv.id,
                product_id=inv.product_id,
                variant_id=inv.variant_id,
                name=name,
                on_hand=inv.on_hand,
                reserved=inv.reserved,
                pending_orders_qty=held,
                available=available,
                low_stock_threshold=threshold,
                low=available <= threshold,
            )
        )
    out.sort(key=lambda r: (not r.low, r.available))
    return out


async def check_low_stock(db: AsyncSession, items: list[OrderItem]) -> int:
    """Sau khi bán món giữ sẵn: còn ≤ ngưỡng thì tạo việc chờ chị (mỗi món một việc đang chờ, không lặp)."""
    keys = {
        (i.product_id, i.variant_id) for i in items if i.product_id and i.fulfillment_source == FulfillmentSource.STOCK
    }
    if not keys:
        return 0
    default_threshold = int(await control.get_setting(db, "orders.low_stock_default_threshold") or 3)
    n = 0
    for product_id, variant_id in keys:
        inv = await refs.inventory_for(db, product_id, variant_id)
        if inv is None:
            continue
        held = await service.pending_stock_qty(db, product_id, variant_id)
        available = inv.on_hand - inv.reserved - held
        threshold = inv.low_stock_threshold if inv.low_stock_threshold is not None else default_threshold
        if available > threshold:
            continue
        p = await db.get(Product, product_id)
        name = p.name if p else "Món giữ sẵn"
        await control.propose(
            LOW_STOCK_ACTION,
            f"Sắp hết: {name} còn {max(available, 0)} cái",
            {"inventory_item_id": str(inv.id), "product_id": str(product_id), "available": available},
            {"name": name, "on_hand": inv.on_hand, "reserved": inv.reserved, "pending_orders": held,
             "available": available, "threshold": threshold},
            db=db, summary=f"Còn {max(available, 0)} cái (ngưỡng báo {threshold}). Chị cân nhắc đặt thêm.",
            ref_type="inventory_items", ref_id=inv.id, dedupe_key=f"low-stock:{inv.id}", ai_generated=False,
        )  # fmt: skip
        n += 1
    return n
