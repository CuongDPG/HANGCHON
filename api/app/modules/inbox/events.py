"""inbox nghe sự kiện của module khác (ARCHITECTURE mục 10). Chạy lặp lại không sinh trùng."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.inbox.models import Thread


@events.on("customer.identified")
async def _link_customer(db: AsyncSession, payload: dict[str, Any]) -> None:
    """orders nhận ra / tạo khách từ tin nhắn → gắn mọi hội thoại cùng người (cùng kênh, cùng định danh) vào hồ sơ đó."""
    cid = uuid.UUID(str(payload["customer_id"]))
    await db.execute(
        update(Thread)
        .where(
            (Thread.id == uuid.UUID(str(payload["thread_id"])))
            | (
                (Thread.channel == payload.get("channel"))
                & (Thread.participant_external_id == payload.get("external_id"))
                & Thread.customer_id.is_(None)
            )
        )
        .values(customer_id=cid)
    )
