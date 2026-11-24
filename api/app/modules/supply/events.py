"""Nghe sự kiện: mua mẫu → gợi ý đơn đặt mẫu; đóng đợt → soạn đơn đặt lô theo nhà cung cấp (g3)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.supply import service


@events.on("candidate.stage_changed")
async def _suggest_sample_order(db: AsyncSession, payload: dict[str, Any]) -> None:
    if payload.get("to") != "sample":
        return
    await service.sample_order_for(db, uuid.UUID(payload["candidate_id"]), skip_if_exists=True)


@events.on("drop.closed")
async def _batch_orders(db: AsyncSession, payload: dict[str, Any]) -> None:
    await service.batch_orders_for_drop(db, uuid.UUID(payload["drop_id"]))
