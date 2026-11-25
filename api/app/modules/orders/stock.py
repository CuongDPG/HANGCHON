"""Tồn kho nhỏ (g8) — phía chị: nhập tồn đầu kỳ, điều chỉnh tay (có lý do, có lưu vết), ngưỡng báo theo từng món.

Bảng `inventory_items` / `inventory_movements` thuộc catalog (catalog là bên duy nhất ghi). orders kiểm đầu vào rồi
phát `inventory.adjust_requested`; catalog nghe và ghi (cùng giao dịch, idempotent theo `request_id`), orders đọc lại."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core import events
from app.core.errors import AppError, BadRequest, Conflict, NotFound
from app.modules.catalog.models import InventoryItem, InventoryMovement, Product, ProductStatus, ProductVariant
from app.modules.control.models import User
from app.modules.orders import drops, refs
from app.modules.orders.schemas import InventoryMovementRow, InventoryRow, StockCandidate

ADJUST_EVENT = "inventory.adjust_requested"

KIND_LABELS = {
    "opening": "Tồn đầu kỳ",
    "count": "Đếm lại",
    "received": "Nhập thêm",
    "damaged": "Hỏng / mất",
    "other": "Điều chỉnh",
}
REASON_LABELS = {
    "purchase_received": "Nhập từ đơn đặt nguồn",
    "order_reserved": "Giữ cho đơn",
    "order_released": "Trả lại từ đơn",
    "order_shipped": "Giao cho hãng vận chuyển",
    "return_restock": "Hàng trả về kho",
    "adjustment": "Điều chỉnh tay",
    "damaged": "Hỏng / mất",
    "sample_use": "Dùng làm mẫu",
}


async def _row(db: AsyncSession, inv_id: uuid.UUID) -> InventoryRow:
    for r in await drops.inventory_rows(db):
        if r.inventory_item_id == inv_id:
            return r
    raise NotFound("Không thấy món trong tồn kho.")


async def _request(db: AsyncSession, payload: dict[str, Any]) -> InventoryItem:
    """Phát yêu cầu ghi tồn cho catalog rồi đọc lại dòng tồn (catalog ghi trong cùng giao dịch)."""
    await events.emit(ADJUST_EVENT, payload, db=db)
    inv = await refs.inventory_for(db, uuid.UUID(payload["product_id"]), _uuid(payload.get("variant_id")))
    if inv is None:
        raise AppError("Chưa ghi được tồn kho (catalog chưa nhận yêu cầu).", code="inventory_not_written")
    await db.refresh(inv)
    return inv


def _uuid(v: Any) -> uuid.UUID | None:
    return uuid.UUID(str(v)) if v else None


async def candidates(db: AsyncSession) -> list[StockCandidate]:
    """Món (và phân loại) chưa có dòng tồn kho — để chị thêm món giữ sẵn."""
    have = {(i.product_id, i.variant_id) for i in (await db.execute(select(InventoryItem))).scalars()}
    products = list(
        (
            await db.execute(
                select(Product).where(Product.status != ProductStatus.ARCHIVED).order_by(Product.name).limit(500)
            )
        ).scalars()
    )
    out: list[StockCandidate] = []
    for p in products:
        active = [v for v in p.variants if v.is_active]
        if not active and (p.id, None) not in have:
            out.append(StockCandidate(product_id=p.id, variant_id=None, name=p.name))
        for v in active:
            if (p.id, v.id) not in have:
                out.append(StockCandidate(product_id=p.id, variant_id=v.id, name=f"{p.name} · {v.name}"))
    return out


async def create(
    db: AsyncSession, user: User, *, product_id: uuid.UUID, variant_id: uuid.UUID | None, on_hand: int,
    threshold: int | None, note: str | None,
) -> InventoryRow:  # fmt: skip
    p = await db.get(Product, product_id)
    if p is None or p.status == ProductStatus.ARCHIVED:
        raise NotFound("Không thấy món này (hoặc món đã ngừng bán).")
    if variant_id:
        v = await db.get(ProductVariant, variant_id)
        if v is None or v.product_id != p.id:
            raise BadRequest("Phân loại không thuộc món này.")
    if await refs.inventory_for(db, product_id, variant_id) is not None:
        raise Conflict("Món này đã có trong tồn kho, chị điều chỉnh ở dòng của nó.", code="inventory_exists")
    request_id = uuid.uuid4()
    inv = await _request(
        db,
        {
            "request_id": str(request_id), "product_id": str(product_id),
            "variant_id": str(variant_id) if variant_id else None, "set_on_hand": on_hand, "kind": "opening",
            "note": " · ".join(x for x in ("Tồn đầu kỳ", (note or "").strip()) if x), "user_id": str(user.id),
            "low_stock_threshold": threshold,
        },
    )  # fmt: skip
    await control.audit(
        db, "orders.inventory_opening", user=user, entity_type="inventory_items", entity_id=inv.id,
        summary=f"Tồn đầu kỳ {p.name}: {on_hand} cái", data={"on_hand": on_hand, "threshold": threshold},
    )  # fmt: skip
    await drops.check_low_stock_keys(db, {(product_id, variant_id)})
    return await _row(db, inv.id)


async def _get(db: AsyncSession, inv_id: uuid.UUID) -> InventoryItem:
    inv = await db.get(InventoryItem, inv_id)
    if inv is None:
        raise NotFound("Không thấy món trong tồn kho.")
    return inv


async def adjust(
    db: AsyncSession, user: User, inv_id: uuid.UUID, *, mode: str, quantity: int, kind: str, reason: str
) -> InventoryRow:
    inv = await _get(db, inv_id)
    target = quantity if mode == "set" else inv.on_hand + quantity
    if target < 0:
        raise BadRequest(f"Tồn sau điều chỉnh không được âm (đang có {inv.on_hand}).")
    if mode == "delta" and quantity == 0:
        raise BadRequest("Chị ghi số lượng cần cộng hoặc trừ.")
    delta = target - inv.on_hand
    await _request(
        db,
        {
            "request_id": str(uuid.uuid4()), "product_id": str(inv.product_id),
            "variant_id": str(inv.variant_id) if inv.variant_id else None, "set_on_hand": target,
            "kind": "count" if mode == "set" else kind, "note": f"{KIND_LABELS.get(kind, 'Điều chỉnh')}: {reason}",
            "user_id": str(user.id),
        },
    )  # fmt: skip
    await control.audit(
        db, "orders.inventory_adjusted", user=user, entity_type="inventory_items", entity_id=inv.id,
        summary=f"Điều chỉnh tồn {inv.on_hand - delta} → {inv.on_hand}: {reason}",
        data={"mode": mode, "quantity": quantity, "kind": kind, "delta": delta, "reason": reason},
    )  # fmt: skip
    if delta < 0:
        await drops.check_low_stock_keys(db, {(inv.product_id, inv.variant_id)})
    return await _row(db, inv.id)


async def set_threshold(db: AsyncSession, user: User, inv_id: uuid.UUID, threshold: int | None) -> InventoryRow:
    inv = await _get(db, inv_id)
    old = inv.low_stock_threshold
    await _request(
        db,
        {
            "request_id": str(uuid.uuid4()), "product_id": str(inv.product_id),
            "variant_id": str(inv.variant_id) if inv.variant_id else None, "low_stock_threshold": threshold,
            "user_id": str(user.id),
        },
    )  # fmt: skip
    await control.audit(
        db, "orders.inventory_threshold", user=user, entity_type="inventory_items", entity_id=inv.id,
        summary=f"Ngưỡng báo sắp hết: {old if old is not None else 'ngưỡng chung'} → "
        f"{threshold if threshold is not None else 'ngưỡng chung'}",
        data={"from": old, "to": threshold},
    )  # fmt: skip
    await drops.check_low_stock_keys(db, {(inv.product_id, inv.variant_id)})
    return await _row(db, inv.id)


async def movements(db: AsyncSession, inv_id: uuid.UUID, limit: int = 50) -> list[InventoryMovementRow]:
    await _get(db, inv_id)
    rows = (
        await db.execute(
            select(InventoryMovement, User.name)
            .outerjoin(User, User.id == InventoryMovement.created_by_id)
            .where(InventoryMovement.inventory_item_id == inv_id)
            .order_by(InventoryMovement.created_at.desc())
            .limit(limit)
        )
    ).all()
    out = []
    for m, name in rows:
        label = REASON_LABELS.get(m.reason.value, m.reason.value)
        note = (m.note or "").removeprefix(f"{label}: ").strip()
        out.append(
            InventoryMovementRow(
                id=m.id, delta_on_hand=m.delta_on_hand, reason=m.reason.value, reason_label=label,
                note=None if not note or note == label else note, created_by_name=name, created_at=m.created_at,
            )
        )  # fmt: skip
    return out
