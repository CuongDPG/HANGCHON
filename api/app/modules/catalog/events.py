"""catalog nghe sự kiện của module khác (ARCHITECTURE mục 10). Mọi người nghe chạy lặp lại không sinh trùng."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.config import settings
from app.core.jobs import enqueue
from app.modules.catalog import drops as drop_svc
from app.modules.catalog import products as product_svc
from app.modules.catalog import reviews as review_svc
from app.modules.catalog.models import Drop, DropItem, DropStatus

log = logging.getLogger("app.catalog")


def _id(payload: dict[str, Any], key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, ValueError, TypeError):
        log.warning("Sự kiện thiếu %s: %s", key, payload)
        return None


@events.on("candidate.selected")
async def on_candidate_selected(db: AsyncSession, payload: dict[str, Any]) -> None:
    """e1: ứng viên được chọn → sản phẩm nháp ngay (cùng giao dịch), AI viết trang ở việc nền."""
    cid = _id(payload, "candidate_id")
    if cid is None:
        return
    product = await product_svc.draft_from_candidate(
        db, cid, _id(payload, "decision_id") if payload.get("decision_id") else None
    )
    if product is None or product.ai_generated:
        return
    if settings.jobs_eager:
        # JOBS_EAGER chạy việc ngay trong phiên khác khi giao dịch của bên phát chưa commit → không thấy dữ liệu,
        # hoặc tự khoá chết khi dòng sản phẩm đang bị giữ. Test gọi job trực tiếp; cron là lưới an toàn.
        return
    try:
        # chạy sau khi giao dịch của bên phát đã commit; cron catalog.write_missing_pages là lưới an toàn
        await enqueue("catalog.write_product_page", product_id=str(product.id), _defer_by=5)
    except Exception:
        log.warning("Chưa xếp được việc AI viết trang cho %s (cron sẽ làm sau)", product.id, exc_info=True)


@events.on("price.approved")
async def on_price_approved(db: AsyncSession, payload: dict[str, Any]) -> None:
    cid = _id(payload, "candidate_id")
    if cid is None:
        return
    await product_svc.apply_price(db, cid, int(payload.get("price_vnd") or 0))


@events.on("order.delivered")
async def on_order_delivered(db: AsyncSession, payload: dict[str, Any]) -> None:
    """e8: khách nhận hàng → lời mời đánh giá (mỗi dòng hàng một mã)."""
    oid = _id(payload, "order_id")
    if oid is not None:
        await review_svc.request_for_order(db, oid)


@events.on("order.paid")
async def on_order_paid(db: AsyncSession, payload: dict[str, Any]) -> None:
    """e3: trừ suất trong đợt (đếm lại từ đơn đã trả tiền); hết suất thì đóng đợt."""
    from app.modules.orders.models import OrderItem

    oid = _id(payload, "order_id")
    if oid is None:
        return
    item_ids = [
        i for i in (await db.execute(select(OrderItem.drop_item_id).where(OrderItem.order_id == oid))).scalars() if i
    ]
    if not item_ids:
        return
    await drop_svc.recount_slots(db, item_ids)
    drop_ids = set((await db.execute(select(DropItem.drop_id).where(DropItem.id.in_(item_ids)))).scalars())
    for did in drop_ids:
        d = await db.get(Drop, did)
        if d is not None and d.status == DropStatus.OPEN:
            await db.refresh(d, ["items"])
            if drop_svc.sold_out(d):
                await drop_svc.close_drop(db, d, reason="hết suất")
