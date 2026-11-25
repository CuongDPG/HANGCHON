"""Việc nền của nguồn cung: theo dõi lô hàng về qua tích hợp `shipping`, tính lại giá vốn khi tham số đổi."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.core.errors import AppError
from app.core.jobs import cron, job
from app.modules.supply import service
from app.modules.supply.models import InboundShipment, InboundStatus, ProvenanceDocument

log = logging.getLogger("app.supply")


@cron("supply.poll_inbound", minute={5, 35})
async def poll_inbound(ctx: dict[str, Any]) -> int:
    added = 0
    async with ctx["db"]() as db:
        ships = (
            await db.execute(
                select(InboundShipment).where(
                    InboundShipment.tracking_code.is_not(None),
                    InboundShipment.status.not_in([InboundStatus.DELIVERED, InboundStatus.PROBLEM]),
                )
            )
        ).scalars()
        for s in ships:
            try:
                added += await service.sync_tracking(db, s, log=True)
            except AppError as e:
                log.info("Lô %s chưa tra được: %s", s.id, e.message)
        await db.commit()
    return added


@cron("supply.recalc_cost_sheets", hour={6}, minute={0})
async def recalc_cost_sheets(ctx: dict[str, Any]) -> int:
    """Lưới an toàn khi tham số bị đổi ở trang cài đặt chung (không qua API của supply)."""
    async with ctx["db"]() as db:
        n = await service.recalc_all(db)
        await db.commit()
    return n


@job("supply.read_document")
async def read_document(ctx: dict[str, Any], document_id: str) -> str | None:
    """AI đọc chứng từ vừa tải lên (d4). Lỗi AI đã được bắt trong service: không lặp lại vô hạn."""
    async with ctx["db"]() as db:
        doc = await db.get(ProvenanceDocument, uuid.UUID(document_id))
        if doc is None:
            return None
        await service.read_document(db, doc)
        await db.commit()
        return str((doc.extracted or {}).get("status"))
