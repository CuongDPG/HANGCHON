"""Lịch đăng tuần (f3): xem theo tuần, AI xếp lịch, gợi ý lấp ô trống (chị gật mới soạn).

Gợi ý ô trống là việc chờ duyệt `content.suggest_post` (không thêm bảng): duyệt = AI soạn bài cho ô đó,
trả lại = bỏ gợi ý."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core.enums import Channel
from app.core.errors import Conflict
from app.core.timeutil import now_utc, to_local, week_start
from app.modules.catalog.models import Drop, DropStatus, Product, ProductStatus
from app.modules.content import facts
from app.modules.content.ai_io import EmptySlot, PlanProduct, PlanWeekIn, PlanWeekOut
from app.modules.content.channels import CONTENT_CHANNELS, MAX_POSTS_PER_DAY, POSTING_WEEKDAYS, channel_label
from app.modules.content.checks import can_approve
from app.modules.content.models import ContentDraft, DraftStatus, PostStatus, ScheduledPost
from app.modules.content.publishing import attribution
from app.modules.content.schedule import (
    ACTIVE,
    WEEKDAY_LABELS,
    WEEKDAY_NAMES,
    at_local,
    best_times,
    next_slot,
    src_code,
    week_bounds,
    week_label,
)
from app.modules.content.service import ACTION_PUBLISH, ACTION_SUGGEST, compose, publish_key
from app.modules.control.models import ApprovalItem, ApprovalStatus


def display_status(post: ScheduledPost, draft: ContentDraft | None) -> str:
    """Trạng thái hiển thị trên lịch: published · draft_pushed · approved («Đã duyệt, chờ giờ») · pending · needs_fix ·
    failed · publishing · hidden / removed (gỡ khi ngừng bán)."""
    if post.status in (
        PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED, PostStatus.FAILED, PostStatus.PUBLISHING, PostStatus.HIDDEN,
        PostStatus.REMOVED,
    ):  # fmt: skip
        return post.status.value
    if post.status == PostStatus.APPROVED:
        return "approved"
    if draft is not None and not can_approve(draft.check_status):
        return "needs_fix"
    return "pending"


async def post_cards(db: AsyncSession, posts: list[ScheduledPost]) -> list[dict[str, Any]]:
    drafts = {
        d.id: d
        for d in (
            await db.execute(select(ContentDraft).where(ContentDraft.id.in_([p.draft_id for p in posts])))
        ).scalars()
    }
    pids = {d.product_id for d in drafts.values() if d.product_id}
    names = dict((await db.execute(select(Product.id, Product.name).where(Product.id.in_(pids)))).all()) if pids else {}
    dids = {d.drop_id for d in drafts.values() if d.drop_id}
    dnames = dict((await db.execute(select(Drop.id, Drop.title).where(Drop.id.in_(dids)))).all()) if dids else {}
    items = {
        it.dedupe_key: it.id
        for it in (
            await db.execute(
                select(ApprovalItem).where(
                    ApprovalItem.action == ACTION_PUBLISH,
                    ApprovalItem.status == ApprovalStatus.PENDING,
                    ApprovalItem.dedupe_key.in_([publish_key(p.draft_id) for p in posts]),
                )
            )
        ).scalars()
    }
    attrs = await attribution(db, [p for p in posts if p.status == PostStatus.PUBLISHED])
    out = []
    for p in posts:
        d = drafts.get(p.draft_id)
        out.append(
            {
                "id": p.id,
                "draft_id": p.draft_id,
                "channel": p.channel.value,
                "channel_label": channel_label(p.channel),
                "scheduled_at": p.scheduled_at,
                "published_at": p.published_at,
                "status": p.status.value,
                "display_status": display_status(p, d),
                "title": (d.title if d else None) or "Bài đăng",
                "product_id": d.product_id if d else None,
                "drop_id": d.drop_id if d else None,
                "name": names.get(d.product_id) if d and d.product_id else (dnames.get(d.drop_id) if d else None),
                "external_url": p.external_url,
                "error": p.error,
                "attempts": p.attempts,
                "approval_item_id": items.get(publish_key(p.draft_id)),
                "src_code": src_code(p),
                "orders": attrs.get(p.id, (0, 0))[0],
            }
        )
    return out


async def suggestions_in(db: AsyncSession, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ApprovalItem).where(
                ApprovalItem.action == ACTION_SUGGEST, ApprovalItem.status == ApprovalStatus.PENDING
            )
        )
    ).scalars()
    out = []
    for it in rows:
        try:
            at = datetime.fromisoformat(it.payload["slot_at"])
        except (KeyError, ValueError):
            continue
        if start <= at < end:
            out.append(
                {
                    "id": it.id,
                    "slot_at": at,
                    "channel": it.payload.get("channel"),
                    "channel_label": channel_label(it.payload.get("channel", "")),
                    "product_id": it.payload.get("product_id"),
                    "name": it.payload.get("name"),
                    "idea": it.payload.get("idea"),
                    "reason": it.rationale,
                }
            )
    return out


async def calendar(db: AsyncSession, ws: date | None = None) -> dict[str, Any]:
    ws = week_start(ws)
    start, end = week_bounds(ws)
    posts = list(
        (
            await db.execute(
                select(ScheduledPost)
                .where(
                    ScheduledPost.status != PostStatus.CANCELLED,
                    ScheduledPost.scheduled_at >= start,
                    ScheduledPost.scheduled_at < end,
                )
                .order_by(ScheduledPost.scheduled_at)
            )
        ).scalars()
    )
    cards = await post_cards(db, posts)
    sugg = await suggestions_in(db, start, end)
    times = await best_times(db)
    days = []
    for i in range(7):
        d = ws + timedelta(days=i)
        days.append(
            {
                "day": d,
                "label": WEEKDAY_LABELS[i],
                "name": WEEKDAY_NAMES[i],
                "rest": d.weekday() not in POSTING_WEEKDAYS,
                "posts": [c for c in cards if to_local(c["scheduled_at"]).date() == d],
                "suggestions": [s for s in sugg if to_local(s["slot_at"]).date() == d],
            }
        )
    counts: dict[str, int] = {}
    for c in cards:
        counts[c["display_status"]] = counts.get(c["display_status"], 0) + 1
    return {
        "week_start": ws,
        "label": week_label(ws),
        "days": days,
        "counts": counts,
        "best_times": [
            {"channel": ch.value, "channel_label": channel_label(ch), "time": f"{hm[0]:02d}:{hm[1]:02d}", "source": src}
            for ch, (hm, src) in times.items()
        ],
    }


async def plan_week(db: AsyncSession, ws: date | None = None) -> dict[str, Any]:
    """AI xếp lịch tuần: (1) dời bài chưa duyệt bị trùng chỗ / lỡ giờ sang ô trống gần nhất, (2) gợi ý bài cho ngày trống."""
    ws = week_start(ws)
    start, end = week_bounds(ws)
    now = now_utc()
    times = await best_times(db)
    planned = list(
        (
            await db.execute(
                select(ScheduledPost)
                .where(ScheduledPost.status == PostStatus.PLANNED, ScheduledPost.scheduled_at < end)
                .order_by(ScheduledPost.created_at)
            )
        ).scalars()
    )
    moved = 0
    seen: dict[tuple[date, Channel], int] = {}
    per_day: dict[date, int] = {}
    approved = (
        await db.execute(
            select(ScheduledPost.scheduled_at, ScheduledPost.channel).where(
                ScheduledPost.status.in_(ACTIVE),
                ScheduledPost.status != PostStatus.PLANNED,
                ScheduledPost.scheduled_at >= start,
                ScheduledPost.scheduled_at < end,
            )
        )
    ).all()
    for at, ch in approved:
        d = to_local(at).date()
        seen[(d, ch)] = 1
        per_day[d] = per_day.get(d, 0) + 1
    for p in planned:
        d = to_local(p.scheduled_at).date()
        clash = (d, p.channel) in seen or per_day.get(d, 0) >= MAX_POSTS_PER_DAY or d.weekday() not in POSTING_WEEKDAYS
        if p.scheduled_at < now or clash:
            p.scheduled_at = await next_slot(db, p.channel, earliest=max(now, start), exclude={p.id}, times=times)
            d = to_local(p.scheduled_at).date()
            moved += 1
            await db.flush()
        seen[(d, p.channel)] = 1
        per_day[d] = per_day.get(d, 0) + 1

    # ô trống: ngày đăng trong tuần (chưa qua) không có bài nào và chưa có gợi ý
    existing = {to_local(s["slot_at"]).date() for s in await suggestions_in(db, start, end)}
    rotation = sorted(CONTENT_CHANNELS, key=lambda c: c.value)
    slots: list[tuple[datetime, Channel]] = []
    for i in range(7):
        d = ws + timedelta(days=i)
        if d.weekday() not in POSTING_WEEKDAYS or per_day.get(d, 0) or d in existing:
            continue
        ch = rotation[i % len(rotation)]
        at = at_local(d, times[ch][0])
        if at > now:
            slots.append((at, ch))
    created = 0
    if slots:
        created = await _suggest(db, slots, ws)
    return {"moved": moved, "suggested": created, "week_start": ws}


async def _suggest(db: AsyncSession, slots: list[tuple[datetime, Channel]], ws: date) -> int:
    products = list(
        (await db.execute(select(Product).where(Product.status == ProductStatus.PUBLISHED).limit(30))).scalars()
    )
    last = dict(
        (
            await db.execute(
                select(ContentDraft.product_id, func.max(ScheduledPost.scheduled_at))
                .join(ScheduledPost, ScheduledPost.draft_id == ContentDraft.id)
                .where(ScheduledPost.status.in_((PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED)))
                .group_by(ContentDraft.product_id)
            )
        ).all()
    )
    now = now_utc()
    plan_products = [
        PlanProduct(
            id=str(p.id),
            name=p.name,
            reason_selected=p.reason_selected,
            days_since_last_post=(now - last[p.id]).days if last.get(p.id) else None,
        )
        for p in products
    ]
    drops = [d.title for d in (await db.execute(select(Drop).where(Drop.status == DropStatus.OPEN))).scalars()]
    inp = PlanWeekIn(
        week_label=week_label(ws),
        empty_slots=[
            EmptySlot(
                index=i,
                day_label=WEEKDAY_NAMES[to_local(at).weekday()],
                time=to_local(at).strftime("%H:%M"),
                channel=ch.value,
            )
            for i, (at, ch) in enumerate(slots)
        ],
        products=plan_products,
        open_drops=drops,
        insights=await facts.insight_lines(db),
    )
    try:
        res = await ai.run("content.plan_week", inp, PlanWeekOut)
    except ai.AIError:
        return 0
    names = {str(p.id): p.name for p in products}
    n = 0
    for s in res.output.suggestions:
        if not (0 <= s.slot_index < len(slots)):
            continue
        at, ch = slots[s.slot_index]
        pid = s.product_id if s.product_id in names else None
        out = await control.propose(
            ACTION_SUGGEST,
            f"Gợi ý {WEEKDAY_NAMES[to_local(at).weekday()]} {to_local(at):%H:%M} · {channel_label(ch)}: {s.idea}",
            {
                "slot_at": at.isoformat(),
                "channel": ch.value,
                "product_id": pid,
                "name": names.get(pid or ""),
                "idea": s.idea,
            },
            preview={
                "idea": s.idea,
                "slot_at": at.isoformat(),
                "channel_label": channel_label(ch),
                "name": names.get(pid or ""),
            },
            db=db,
            rationale=s.reason,
            ref_type="products" if pid else None,
            ref_id=uuid.UUID(pid) if pid else None,
            ai_run_id=res.run_id,
            dedupe_key=f"slot:{at.isoformat()}",
        )
        n += out.status in ("pending", "applied")
    return n


async def apply_suggestion(db: AsyncSession, payload: dict[str, Any]) -> control.HandlerResult:
    """Chị gật gợi ý → AI soạn bài cho ô đó (vẫn qua soát lời và chờ duyệt đăng như mọi bài)."""
    at = datetime.fromisoformat(payload["slot_at"])
    ch = Channel(payload["channel"])
    product = await facts.get_product(db, payload["product_id"]) if payload.get("product_id") else None
    if product is None:
        raise Conflict("Gợi ý này chưa gắn sản phẩm; chị soạn bài chung bằng tay nhé.", code="no_product")
    out = await compose(db, product=product, channels=[ch], instruction=payload.get("idea"), slot_at=at)
    draft = await db.scalar(
        select(ContentDraft)
        .where(
            ContentDraft.product_id == product.id,
            ContentDraft.channel == ch,
            ContentDraft.status != DraftStatus.ARCHIVED,
        )
        .order_by(ContentDraft.created_at.desc())
        .limit(1)
    )
    return control.HandlerResult(
        result={"compose": out.status, "draft_id": str(draft.id) if draft else None, "product_id": str(product.id)},
        summary=f"Đã soạn bài {channel_label(ch)} cho {product.name}",
        ref_type="content_drafts" if draft else None,
        ref_id=draft.id if draft else None,
    )
