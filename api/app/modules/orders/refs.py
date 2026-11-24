"""Đọc (chỉ đọc) bảng của module khác mà orders cần: sản phẩm (catalog), đợt (catalog), tồn kho (catalog),
lô hàng về (supply). Không ghi gì vào các bảng này — ghi sang module khác chỉ qua sự kiện."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.modules.catalog.models import Drop, DropStatus, InventoryItem, Product, ProductImage
from app.modules.orders.schemas import DropBrief, InboundBrief
from app.modules.supply.models import InboundShipment, InboundStatus, PurchaseOrder

INBOUND_LABELS: dict[str, str] = {
    InboundStatus.ORDERED: "Đã đặt nhà cung cấp",
    InboundStatus.SELLER_SHIPPED: "Bên bán đã gửi hàng",
    InboundStatus.AT_AGENT_WAREHOUSE: "Hàng đã về kho bên mua hộ",
    InboundStatus.INTERNATIONAL_TRANSIT: "Hàng đang trên đường về Việt Nam",
    InboundStatus.CUSTOMS: "Hàng đang thông quan",
    InboundStatus.DOMESTIC_TRANSIT: "Hàng đang chuyển về kho của chị",
    InboundStatus.DELIVERED: "Hàng đã về tới kho, chị kiểm từng món",
    InboundStatus.PROBLEM: "Lô hàng gặp trục trặc, chị đang xử lý",
}
INBOUND_ORDER = [
    InboundStatus.ORDERED,
    InboundStatus.SELLER_SHIPPED,
    InboundStatus.AT_AGENT_WAREHOUSE,
    InboundStatus.INTERNATIONAL_TRANSIT,
    InboundStatus.CUSTOMS,
    InboundStatus.DOMESTIC_TRANSIT,
    InboundStatus.DELIVERED,
]
TRANSIT_STATUSES = {
    InboundStatus.SELLER_SHIPPED,
    InboundStatus.AT_AGENT_WAREHOUSE,
    InboundStatus.INTERNATIONAL_TRANSIT,
    InboundStatus.CUSTOMS,
    InboundStatus.DOMESTIC_TRANSIT,
}


def drop_brief(drop: Drop | None) -> DropBrief | None:
    if drop is None:
        return None
    return DropBrief(
        id=drop.id,
        code=drop.code,
        title=drop.title,
        status=drop.status.value,
        closes_at=drop.closes_at,
        expected_arrival_date=drop.expected_arrival_date,
    )


def image_url(key: str | None) -> str | None:
    if not key:
        return None
    if key.startswith(("http://", "https://", "/")):
        return key
    return get_storage().url(key)


async def primary_images(db: AsyncSession, product_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {p for p in product_ids if p}
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(ProductImage)
            .where(ProductImage.product_id.in_(ids))
            .order_by(ProductImage.is_primary.desc(), ProductImage.position)
        )
    ).scalars()
    out: dict[uuid.UUID, str] = {}
    for img in rows:
        if img.product_id not in out:
            url = image_url(img.processed_key or img.original_key)
            if url:
                out[img.product_id] = url
    return out


async def products_by_id(db: AsyncSession, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, Product]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {p.id: p for p in (await db.execute(select(Product).where(Product.id.in_(ids)))).scalars()}


async def inbound_for_drop(db: AsyncSession, drop_id: uuid.UUID) -> list[InboundShipment]:
    return list(
        (
            await db.execute(
                select(InboundShipment)
                .join(PurchaseOrder, PurchaseOrder.id == InboundShipment.purchase_order_id)
                .where(PurchaseOrder.drop_id == drop_id)
                .order_by(InboundShipment.created_at)
            )
        ).scalars()
    )


def _last_milestone(s: InboundShipment) -> tuple[str | None, datetime | None]:
    ms = [m for m in (s.milestones or []) if isinstance(m, dict)]
    if not ms:
        return None, None
    last = ms[-1]
    at = last.get("at")
    try:
        at_dt = datetime.fromisoformat(at) if isinstance(at, str) else None
    except ValueError:
        at_dt = None
    return (last.get("note") or None), at_dt


def inbound_brief(s: InboundShipment) -> InboundBrief:
    note, at = _last_milestone(s)
    return InboundBrief(
        id=s.id,
        code=s.code,
        status=s.status.value,
        status_label=INBOUND_LABELS.get(s.status, s.status.value),
        eta=s.eta,
        last_note=note,
        last_at=at or s.updated_at,
    )


def slowest(shipments: list[InboundShipment]) -> InboundShipment | None:
    """Lô chậm nhất của đợt (đại diện cho hành trình khách thấy). Lô có trục trặc được ưu tiên báo."""
    if not shipments:
        return None
    problem = [s for s in shipments if s.status == InboundStatus.PROBLEM]
    if problem:
        return problem[0]
    return min(shipments, key=lambda s: INBOUND_ORDER.index(s.status) if s.status in INBOUND_ORDER else 0)


async def drop_arrived(db: AsyncSession, drop: Drop) -> bool:
    """Hàng của đợt đã về kho chưa: đợt đã sang giao/xong, có ngày về thật, hoặc mọi lô đã về."""
    if drop.status in (DropStatus.FULFILLING, DropStatus.COMPLETED) or drop.actual_arrival_date:
        return True
    lots = await inbound_for_drop(db, drop.id)
    return bool(lots) and all(s.status == InboundStatus.DELIVERED for s in lots)


def eta_of(drop: Drop | None, lots: list[InboundShipment]) -> date | None:
    etas = [s.eta for s in lots if s.eta]
    if etas:
        return max(etas)
    return drop.expected_arrival_date if drop else None


async def inventory_for(
    db: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID | None, *, lock: bool = False
) -> InventoryItem | None:
    q = select(InventoryItem).where(
        InventoryItem.product_id == product_id,
        InventoryItem.variant_id.is_(None) if variant_id is None else InventoryItem.variant_id == variant_id,
    )
    if lock:
        q = q.with_for_update()  # khoá dòng để chống đặt vượt (chỉ đọc, không ghi)
    return (await db.execute(q)).scalar_one_or_none()
