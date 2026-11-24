"""Suất trong đợt và tồn kho nhỏ (e3, g8) — catalog là bên duy nhất ghi `drop_items.slots_reserved` và `inventory_items`.

Một cách tính duy nhất, chung với orders (`app.modules.orders.models`):
  · đơn **đã trả** (`paid_at` có giá trị, đơn còn sống) → catalog ghi vào `slots_reserved` / `reserved`;
  · đơn **chưa trả** còn sống → orders tự cộng như «đang giữ tạm» khi kiểm còn suất/còn hàng.
Hai tập không giao nhau nên không có đơn nào bị đếm hai lần. Món giữ sẵn rời kho khi đơn được giao cho hãng
(`order.shipped`): `on_hand` giảm một lần cho mỗi đơn (ghi `inventory_movements`).
Mọi hàm tính lại từ đơn hoặc kiểm vết đã ghi → chạy lặp lại không sai."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog import drops as drop_svc
from app.modules.catalog.models import (
    Drop,
    DropItem,
    DropStatus,
    InventoryItem,
    InventoryMovement,
    MovementReason,
)
from app.modules.orders.models import PRE_SHIP_STATUSES, FulfillmentSource, Order, OrderItem


async def _inventory(db: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID | None) -> InventoryItem | None:
    q = select(InventoryItem).where(
        InventoryItem.product_id == product_id,
        InventoryItem.variant_id.is_(None) if variant_id is None else InventoryItem.variant_id == variant_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def recount_reserved(db: AsyncSession, keys: set[tuple[uuid.UUID, uuid.UUID | None]]) -> None:
    """`reserved` = món giữ sẵn của các đơn đã trả mà chưa rời kho."""
    for product_id, variant_id in keys:
        inv = await _inventory(db, product_id, variant_id)
        if inv is None:
            continue
        qty = await db.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.product_id == product_id,
                OrderItem.variant_id.is_(None) if variant_id is None else OrderItem.variant_id == variant_id,
                OrderItem.fulfillment_source == FulfillmentSource.STOCK,
                Order.paid_at.is_not(None),
                Order.status.in_(PRE_SHIP_STATUSES),
            )
        )
        inv.reserved = int(qty or 0)
    await db.flush()


async def _order_lines(db: AsyncSession, order_id: uuid.UUID) -> list[OrderItem]:
    return list((await db.execute(select(OrderItem).where(OrderItem.order_id == order_id))).scalars())


def _stock_keys(lines: list[OrderItem]) -> set[tuple[uuid.UUID, uuid.UUID | None]]:
    return {
        (i.product_id, i.variant_id) for i in lines if i.product_id and i.fulfillment_source == FulfillmentSource.STOCK
    }


async def sync_order(db: AsyncSession, order_id: uuid.UUID, *, close_sold_out: bool = False) -> None:
    """Đơn đổi trạng thái tiền/sống chết → tính lại suất của đợt và phần tồn đang giữ của các món trong đơn."""
    lines = await _order_lines(db, order_id)
    drop_item_ids = [i.drop_item_id for i in lines if i.drop_item_id]
    if drop_item_ids:
        await drop_svc.recount_slots(db, drop_item_ids)
        if close_sold_out:
            drop_ids = set((await db.execute(select(DropItem.drop_id).where(DropItem.id.in_(drop_item_ids)))).scalars())
            for did in drop_ids:
                d = await db.get(Drop, did)
                if d is not None and d.status == DropStatus.OPEN:
                    await db.refresh(d, ["items"])
                    if drop_svc.sold_out(d):
                        await drop_svc.close_drop(db, d, reason="hết suất")
    await recount_reserved(db, _stock_keys(lines))


async def ship_order(db: AsyncSession, order_id: uuid.UUID) -> int:
    """Đơn rời kho: trừ `on_hand` các món giữ sẵn (một lần cho mỗi đơn), rồi tính lại phần đang giữ."""
    lines = await _order_lines(db, order_id)
    keys = _stock_keys(lines)
    moved = 0
    for product_id, variant_id in keys:
        inv = await _inventory(db, product_id, variant_id)
        if inv is None:
            continue
        done = await db.scalar(
            select(InventoryMovement.id).where(
                InventoryMovement.inventory_item_id == inv.id,
                InventoryMovement.reason == MovementReason.ORDER_SHIPPED,
                InventoryMovement.ref_type == "orders",
                InventoryMovement.ref_id == order_id,
            )
        )
        if done:
            continue
        qty = sum(
            i.quantity for i in lines if i.fulfillment_source == FulfillmentSource.STOCK and
            (i.product_id, i.variant_id) == (product_id, variant_id)
        )  # fmt: skip
        inv.on_hand = max(0, inv.on_hand - qty)
        db.add(
            InventoryMovement(
                inventory_item_id=inv.id, delta_on_hand=-qty, reason=MovementReason.ORDER_SHIPPED,
                ref_type="orders", ref_id=order_id, note="Giao cho hãng vận chuyển",
            )
        )  # fmt: skip
        moved += qty
    await db.flush()
    await recount_reserved(db, keys)
    return moved


async def receive_inbound(db: AsyncSession, inbound_id: uuid.UUID) -> int:
    """Lô hàng về: lô bổ sung hàng giữ sẵn → nhập tồn; lô của đợt → khi mọi lô của đợt đã về, đợt chuyển sang giao."""
    from app.modules.supply.models import InboundShipment, InboundStatus, POKind, PurchaseOrder  # chỉ đọc

    lot = await db.get(InboundShipment, inbound_id)
    if lot is None or lot.purchase_order_id is None:
        return 0
    po = await db.get(PurchaseOrder, lot.purchase_order_id)
    if po is None:
        return 0
    added = 0
    if po.kind == POKind.RESTOCK:
        for ln in po.lines:
            if ln.product_id is None:
                continue
            done = await db.scalar(
                select(InventoryMovement.id).join(InventoryItem, InventoryItem.id == InventoryMovement.inventory_item_id)
                .where(
                    InventoryItem.product_id == ln.product_id,
                    InventoryMovement.reason == MovementReason.PURCHASE_RECEIVED,
                    InventoryMovement.ref_type == "purchase_order_lines",
                    InventoryMovement.ref_id == ln.id,
                )
            )  # fmt: skip
            if done:
                continue
            qty = (ln.received_qty - ln.defect_qty) if ln.received_qty else ln.quantity
            if qty <= 0:
                continue
            inv = await _inventory(db, ln.product_id, ln.variant_id)
            if inv is None:
                inv = InventoryItem(product_id=ln.product_id, variant_id=ln.variant_id, on_hand=0, reserved=0)
                db.add(inv)
                await db.flush()
            inv.on_hand += qty
            if ln.unit_cost_vnd:
                inv.unit_cost_vnd = ln.unit_cost_vnd
            db.add(
                InventoryMovement(
                    inventory_item_id=inv.id, delta_on_hand=qty, reason=MovementReason.PURCHASE_RECEIVED,
                    ref_type="purchase_order_lines", ref_id=ln.id, note=f"Nhập từ đơn {po.code}",
                )
            )  # fmt: skip
            added += qty
        await db.flush()
    if po.drop_id:
        drop = await db.get(Drop, po.drop_id)
        if drop is not None and drop.status in (DropStatus.CLOSED, DropStatus.SOURCING, DropStatus.ARRIVING):
            lots = list(
                (
                    await db.execute(
                        select(InboundShipment.status)
                        .join(PurchaseOrder, PurchaseOrder.id == InboundShipment.purchase_order_id)
                        .where(PurchaseOrder.drop_id == drop.id)
                    )
                ).scalars()
            )
            if lots and all(s == InboundStatus.DELIVERED for s in lots):
                drop.status = DropStatus.FULFILLING
                drop.actual_arrival_date = (lot.received_at or lot.updated_at).date()
                await db.flush()
    return added
