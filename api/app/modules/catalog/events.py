"""catalog nghe sự kiện của module khác (ARCHITECTURE mục 10). Mọi người nghe chạy lặp lại không sinh trùng."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.config import settings
from app.core.jobs import enqueue
from app.modules.catalog import inventory
from app.modules.catalog import products as product_svc
from app.modules.catalog import reviews as review_svc

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
    """e3/g8: đơn đã trả → tính lại suất của đợt và phần tồn đang giữ; hết suất thì đóng đợt."""
    oid = _id(payload, "order_id")
    if oid is not None:
        await inventory.sync_order(db, oid, close_sold_out=True)


@events.on("order.cancelled")
@events.on("order.refunded")
async def on_order_released(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Đơn huỷ / hoàn tiền → trả suất và phần tồn đang giữ (tính lại từ đơn nên không trả hai lần)."""
    oid = _id(payload, "order_id")
    if oid is not None:
        await inventory.sync_order(db, oid)


@events.on("order.shipped")
async def on_order_shipped(db: AsyncSession, payload: dict[str, Any]) -> None:
    """g8: đơn rời kho → trừ tồn món giữ sẵn (một lần cho mỗi đơn)."""
    oid = _id(payload, "order_id")
    if oid is not None:
        await inventory.ship_order(db, oid)


@events.on("inbound.arrived")
async def on_inbound_arrived(db: AsyncSession, payload: dict[str, Any]) -> None:
    """g8/e3: lô hàng về → nhập tồn (lô bổ sung) hoặc chuyển đợt sang giao khi mọi lô đã về."""
    iid = _id(payload, "inbound_shipment_id")
    if iid is not None:
        await inventory.receive_inbound(db, iid)
