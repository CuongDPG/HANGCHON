"""Đánh giá có ảnh của khách (e8): `order.delivered` → lời mời (mã một lần) → khách gửi sao + chữ + ảnh
→ AI lọc → chờ chị duyệt hiển thị → `review.published`."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.config import settings
from app.core.enums import Channel
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.security import random_token
from app.core.storage import get_storage
from app.core.timeutil import now_utc
from app.integrations import notify as notify_api
from app.integrations.notify import OutboundNotification
from app.modules.catalog import images as img_lib
from app.modules.catalog.ai_tasks import ModerateIn, ModerateOut, moderate_rules
from app.modules.catalog.models import Product, Review, ReviewStatus

log = logging.getLogger("app.catalog")

REVIEW_TTL_DAYS = 60
MAX_PHOTOS = 4
MAX_REASON = 300  # «Vì sao bạn chọn món này?»


def short_name(full: str | None) -> str | None:
    """«Nguyễn Thị Lan» → «Lan» (tên gọi, không lộ họ tên đầy đủ)."""
    parts = (full or "").split()
    return parts[-1] if parts else None


def review_link(token: str) -> str:
    return f"{settings.web_base_url.rstrip('/')}/danh-gia/{token}"


async def request_for_order(db: AsyncSession, order_id: uuid.UUID) -> list[Review]:
    """Tạo lời mời đánh giá cho từng dòng hàng của đơn đã giao (mỗi dòng tối đa một). Chạy lặp không sinh trùng."""
    from app.modules.orders.models import Order, OrderItem

    order = await db.get(Order, order_id)
    if order is None:
        log.warning("order.delivered: không thấy đơn %s", order_id)
        return []
    items = list((await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars())
    have = set(
        (
            await db.execute(select(Review.order_item_id).where(Review.order_item_id.in_([i.id for i in items])))
        ).scalars()
    )
    created: list[Review] = []
    for it in items:
        if it.product_id is None or it.id in have:
            continue
        r = Review(
            product_id=it.product_id,
            order_id=order.id,
            order_item_id=it.id,
            customer_id=order.customer_id,
            token=random_token(18),
            status=ReviewStatus.REQUESTED,
            requested_at=now_utc(),
            display_name=short_name(order.recipient_name),
        )
        db.add(r)
        created.append(r)
    if not created:
        return []
    await db.flush()
    names = {i.id: i.name for i in items}
    lines = "\n".join(f"• {names[r.order_item_id]}: {review_link(r.token)}" for r in created if r.order_item_id)
    text = (
        f"Hàng Chọn cảm ơn bạn đã nhận đơn {order.code}. Dùng vài hôm rồi, bạn chấm giúp mình vài chữ và một tấm ảnh nhé "
        f"(không bắt buộc):\n{lines}"
    )
    await control.propose(
        "catalog.send_review_request",
        f"Xin đánh giá đơn {order.code}",
        {
            "order_id": str(order.id),
            "review_ids": [str(r.id) for r in created],
            "to": order.recipient_phone,
            "text": text,
        },
        {"order_code": order.code, "text": text, "count": len(created)},
        db=db,
        ref_type="orders",
        ref_id=order.id,
        dedupe_key=f"review-request:{order.id}",
        ai_generated=False,
    )
    return created


async def send_request(payload: dict[str, Any]) -> dict[str, Any]:
    to, text = str(payload["to"]), str(payload["text"])
    res = await notify_api.send(
        OutboundNotification(
            channel=Channel.ZALO_OA, to=to, text=text, kind="review_request", data={"phone": to, "noi_dung": text}
        )
    )
    if res.status == "failed":
        raise BadRequest(f"Chưa gửi được tin xin đánh giá: {res.error or 'lỗi kênh gửi'}")
    return {"external_id": res.external_id, "status": res.status}


async def get_by_token(db: AsyncSession, token: str) -> Review:
    r = (await db.execute(select(Review).where(Review.token == token))).scalar_one_or_none()
    if r is None:
        raise NotFound("Đường link đánh giá không đúng hoặc đã hết hạn.")
    if (
        r.status == ReviewStatus.REQUESTED
        and r.requested_at
        and r.requested_at < now_utc() - timedelta(days=REVIEW_TTL_DAYS)
    ):
        r.status = ReviewStatus.EXPIRED
        await db.flush()
    return r


async def submit(
    db: AsyncSession,
    review: Review,
    *,
    rating: int,
    body: str | None,
    display_name: str | None,
    photos: list[bytes],
    choice_reason: str | None = None,
) -> Review:
    if review.status == ReviewStatus.EXPIRED:
        raise Conflict("Đường link này đã hết hạn.", code="review_expired")
    if review.status != ReviewStatus.REQUESTED:
        raise Conflict("Bạn đã gửi đánh giá cho món này rồi. Cảm ơn bạn!", code="review_already_submitted")
    if not 1 <= rating <= 5:
        raise BadRequest("Bạn chọn từ 1 đến 5 sao nhé.")
    body = (body or "").strip()
    if len(body) > 2000:
        raise BadRequest("Lời đánh giá dài quá 2.000 chữ.")
    choice_reason = " ".join((choice_reason or "").split())
    if len(choice_reason) > MAX_REASON:
        raise BadRequest(f"Lý do chọn dài quá {MAX_REASON} chữ.")
    if len(photos) > MAX_PHOTOS:
        raise BadRequest(f"Tối đa {MAX_PHOTOS} ảnh.")
    stored = []
    for data in photos:
        processed = img_lib.process_photo(data, enhance=False)  # chỉ xoay, cắt vuông, bỏ EXIF (vị trí chụp)
        stored.append({"files": await img_lib.store_renditions(f"public/reviews/{review.id}", processed)})
    review.rating = rating
    review.body = body or None
    review.choice_reason = choice_reason or None
    review.display_name = (display_name or "").strip()[:60] or review.display_name
    review.photos = stored
    review.submitted_at = now_utc()
    review.status = ReviewStatus.SUBMITTED
    await db.flush()
    await moderate_and_propose(db, review)
    return review


async def moderate_and_propose(db: AsyncSession, review: Review) -> control.ProposeOutcome:
    product = await db.get(Product, review.product_id)
    # AI lọc cả lời đánh giá lẫn lý do chọn (cả hai đều hiện công khai)
    text = "\n".join(
        t for t in (review.body, f"Vì sao chọn: {review.choice_reason}" if review.choice_reason else None) if t
    )
    inp = ModerateIn(kind="review", text=text, product_name=product.name if product else None,
                     rating=review.rating)  # fmt: skip
    rules = moderate_rules(inp)
    run_id = None
    try:
        res = await ai.run("catalog.moderate_review", inp, ModerateOut)
        verdict, run_id = res.output, res.run_id
    except ai.AIError as e:  # AI dừng (trần chi phí, mất mạng): vẫn đưa chị duyệt bằng luật đơn giản
        log.warning("Lọc đánh giá bằng AI lỗi: %s", e)
        verdict = rules
    flags = {
        "spam": verdict.spam or rules.spam,
        "offensive": verdict.offensive or rules.offensive,
        "personal_info": verdict.personal_info or rules.personal_info,
        "off_topic": verdict.off_topic,
    }
    hide = verdict.recommend == "hide" or any(flags[k] for k in ("spam", "offensive", "personal_info"))
    review.ai_flags = {**flags, "recommend": "hide" if hide else "publish"}
    review.ai_summary = rules.reason if (hide and verdict.recommend != "hide") else verdict.reason
    review.status = ReviewStatus.PENDING_REVIEW
    await db.flush()
    out = await control.propose(
        "catalog.publish_review",
        f"Hiện đánh giá {review.rating}★ cho {product.name if product else 'sản phẩm'}",
        {"review_id": str(review.id)},
        {
            "product": product.name if product else None,
            "rating": review.rating,
            "body": review.body,
            "choice_reason": review.choice_reason,
            "display_name": review.display_name,
            "photos": [photo_url(p, 400) for p in review.photos],
            "flags": review.ai_flags,
            "reason": review.ai_summary,
        },
        db=db,
        summary=review.ai_summary,
        rationale="AI lọc spam, từ thô tục, lộ thông tin cá nhân. Chê thật lòng không phải lý do để ẩn.",
        ref_type="reviews",
        ref_id=review.id,
        ai_run_id=run_id,
        dedupe_key=f"review:{review.id}",
    )
    if out.status == "pending":
        review.approval_item_id = out.item_id
        await db.flush()
    return out


def photo_url(photo: Any, size: int = 800) -> str | None:
    files = photo.get("files") if isinstance(photo, dict) else None
    key = img_lib.pick(files or {}, size) if files else None
    return get_storage().url(key) if key else None


async def publish(db: AsyncSession, review: Review, *, mode: str) -> Review:
    if mode == "auto" and review.ai_flags.get("recommend") == "hide":
        # AI tự làm thì không bao giờ tự hiện bài bị gắn cờ; chị duyệt tay thì theo chị
        review.status = ReviewStatus.HIDDEN
        await db.flush()
        return review
    review.status = ReviewStatus.PUBLISHED
    review.published_at = now_utc()
    await db.flush()
    await recompute_rating(db, review.product_id)
    await events.emit("review.published", {"review_id": str(review.id), "product_id": str(review.product_id)}, db=db)
    return review


async def hide(db: AsyncSession, review: Review, status: ReviewStatus = ReviewStatus.HIDDEN) -> Review:
    review.status = status
    await db.flush()
    await recompute_rating(db, review.product_id)
    return review


async def recompute_rating(db: AsyncSession, product_id: uuid.UUID) -> None:
    avg, n = (
        await db.execute(
            select(func.avg(Review.rating), func.count()).where(
                Review.product_id == product_id, Review.status == ReviewStatus.PUBLISHED
            )
        )
    ).one()
    product = await db.get(Product, product_id)
    if product is not None:
        product.review_count = int(n)
        product.rating_avg = round(float(avg), 2) if avg is not None else None
        await db.flush()


async def get_review(db: AsyncSession, review_id: uuid.UUID) -> Review:
    r = await db.get(Review, review_id)
    if r is None:
        raise NotFound("Không tìm thấy đánh giá.")
    return r
