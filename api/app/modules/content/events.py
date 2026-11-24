"""Nghe sự kiện: sản phẩm lên web / mở đợt → tạo bản `drafting` cho từng kênh (idempotent) rồi hẹn job soạn.

Người nghe chạy trong giao dịch của bên phát (chưa commit), nên việc gọi AI để job làm sau: job hẹn 5 giây + cron
quét `content.compose_pending` mỗi 2 phút bắt mọi bản còn `drafting`."""

from __future__ import annotations

import logging
import uuid
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


@events.on("review.published")
async def on_review_published(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Đánh giá tốt (≥ 4★) được hiển thị → gợi ý một bài Facebook kể lại lời khách (chị gật thì AI mới soạn)."""
    from datetime import datetime, time, timedelta

    from app import control
    from app.core.enums import Channel
    from app.core.timeutil import VN_TZ, local_today
    from app.modules.catalog.models import Review
    from app.modules.content.service import ACTION_SUGGEST

    review = await db.get(Review, uuid.UUID(str(payload.get("review_id"))))
    product = await facts.get_product(db, payload.get("product_id", ""))
    if review is None or product is None or (review.rating or 0) < 4 or not (review.body or "").strip():
        return
    slot = datetime.combine(local_today() + timedelta(days=1), time(20, 0), tzinfo=VN_TZ)
    quote = review.body.strip()[:200]
    await control.propose(
        ACTION_SUGGEST,
        f"Gợi ý bài từ đánh giá {review.rating}★: {product.name}",
        {"slot_at": slot.isoformat(), "channel": Channel.FACEBOOK.value, "product_id": str(product.id),
         "idea": f"Kể lại cảm nhận của khách đã nhận hàng ({review.rating}★): «{quote}». Giữ nguyên lời khách."},
        {"product": product.name, "rating": review.rating, "quote": quote, "slot_at": slot.isoformat()},
        db=db, summary="Khách vừa khen món này; một bài kể lại lời khách thường ra đơn tốt.",
        ref_type="reviews", ref_id=review.id, dedupe_key=f"review-post:{review.id}", ai_generated=False,
    )  # fmt: skip
