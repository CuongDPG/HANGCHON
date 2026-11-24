"""Nghe sự kiện: sản phẩm lên web / mở đợt → tạo bản `drafting` cho từng kênh (idempotent) rồi hẹn job soạn.

Người nghe chạy trong giao dịch của bên phát (chưa commit), nên việc gọi AI để job làm sau: job hẹn 5 giây + cron
quét `content.compose_pending` mỗi 2 phút bắt mọi bản còn `drafting`."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.config import settings
from app.core.jobs import enqueue
from app.modules.content import facts
from app.modules.content.service import ensure_placeholders

log = logging.getLogger("app.content.events")


async def _kick() -> None:
    if settings.jobs_eager:
        return  # test: gọi job quét trực tiếp sau khi bên phát commit
    try:
        await enqueue("content.compose_pending", _defer_by=5)
    except Exception:  # Redis chưa chạy: cron quét vẫn bắt được
        log.warning("Chưa hẹn được job soạn bài; cron quét sẽ làm sau.")


@events.on("product.published")
async def on_product_published(db: AsyncSession, payload: dict[str, Any]) -> None:
    product = await facts.get_product(db, payload.get("product_id", ""))
    if product is None:
        return
    if await ensure_placeholders(db, product=product):
        await _kick()


@events.on("drop.opened")
async def on_drop_opened(db: AsyncSession, payload: dict[str, Any]) -> None:
    drop = await facts.get_drop(db, payload.get("drop_id", ""))
    if drop is None:
        return
    if await ensure_placeholders(db, drop=drop):
        await _kick()
