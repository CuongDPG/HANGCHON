"""Nghe sự kiện để ghi sổ tự động (k1). Mỗi người nghe chạy lặp lại không sinh trùng (khoá `source_key`)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.control import service as control
from app.modules.finance import service

log = logging.getLogger("app.finance")


def _uuid(v: Any) -> uuid.UUID | None:
    return uuid.UUID(str(v)) if v else None


@events.on("order.paid")
async def on_order_paid(db: AsyncSession, payload: dict[str, Any]) -> None:
    order_id = _uuid(payload.get("order_id"))
    if order_id is None:
        return
    await service.record_order_paid(db, order_id, _uuid(payload.get("payment_id")))
    if await control.get_setting(db, "finance.auto_invoice"):
        try:
            async with db.begin_nested():
                await service.prepare_invoice(db, order_id)
        except Exception as e:  # không làm hỏng việc ghi sổ
            log.info("Không tự soạn hoá đơn cho đơn %s: %s", order_id, e)


@events.on("order.refunded")
async def on_order_refunded(db: AsyncSession, payload: dict[str, Any]) -> None:
    if payload.get("order_id"):
        await service.record_order_refunded(db, payload)


@events.on("expense.recorded")
async def on_expense_recorded(db: AsyncSession, payload: dict[str, Any]) -> None:
    await service.record_expense_event(db, payload)
