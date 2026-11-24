"""crm nghe sự kiện của module khác (ARCHITECTURE mục 10). Mọi người nghe chạy lặp lại không sinh trùng."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.config import settings
from app.core.jobs import enqueue
from app.modules.crm import service
from app.modules.inbox.models import Thread
from app.modules.orders.models import Order


async def _refresh_later(db: AsyncSession, customer_id: uuid.UUID) -> None:
    """Tóm tắt sổ khách sau khi hội thoại lắng xuống (gom các tin trong ~10 phút). Chạy ngay khi JOBS_EAGER (test)."""
    if settings.jobs_eager:
        await service.refresh_profile(db, customer_id)
        return
    bucket = int(time.time() // 600)
    await enqueue(
        "crm.refresh_profile",
        customer_id=str(customer_id),
        _defer_by=600,
        _job_id=f"crm-profile:{customer_id}:{bucket}",
    )


@events.on("message.received")
async def on_message(db: AsyncSession, payload: dict[str, Any]) -> None:
    thread = await db.get(Thread, uuid.UUID(payload["thread_id"]))
    if thread and thread.customer_id:
        await _refresh_later(db, thread.customer_id)


@events.on("customer.identified")
async def on_customer_identified(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Khách mới có hồ sơ từ tin nhắn → tóm tắt sổ khách (h4)."""
    await _refresh_later(db, uuid.UUID(payload["customer_id"]))


@events.on("order.created")
async def on_order_created(db: AsyncSession, payload: dict[str, Any]) -> None:
    oid = uuid.UUID(payload["order_id"])
    await service.record_referral(db, oid)
    await service.mark_rebought(db, oid)
    order = await db.get(Order, oid)
    if order and order.customer_id:
        await _refresh_later(db, order.customer_id)


@events.on("order.delivered")
async def on_order_delivered(db: AsyncSession, payload: dict[str, Any]) -> None:
    oid = uuid.UUID(payload["order_id"])
    await service.schedule_reminders(db, oid)
    await service.qualify_referral(db, oid)


@events.on("drop.opened")
async def on_drop_opened(db: AsyncSession, payload: dict[str, Any]) -> None:
    await service.draft_drop_announcement(db, uuid.UUID(payload["drop_id"]))
