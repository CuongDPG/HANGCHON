"""Bảng theo dõi nội dung theo món (Xưởng): mỗi sản phẩm / đợt một dòng, mỗi kênh một trạng thái + số liệu bài.

Gom bằng vài truy vấn cho cả danh sách (không truy vấn theo từng món): món → bản nháp hiện tại → bài trên lịch →
lần duyệt → số liệu mới nhất + đơn gắn qua mã bài. Dữ liệu của một người bán (vài trăm món) nên lọc/đếm tab trong bộ nhớ
rồi mới cắt trang.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Drop, DropStatus, Product, ProductStatus
from app.modules.catalog.textutil import matches_vi
from app.modules.content import facts
from app.modules.content.channels import DROP_CHANNELS, PRODUCT_CHANNELS
from app.modules.content.checks import can_approve
from app.modules.content.models import ContentDraft, DraftStatus, PostStatus, ScheduledPost
from app.modules.content.publishing import attribution, latest_metrics
from app.modules.control.models import ApprovalItem

WEBSITE = "website"
BOARD_CHANNELS = [WEBSITE, *(c.value for c, _ in PRODUCT_CHANNELS)]
TABS = ("todo", "review", "scheduled", "published", "all")

# món đang bán hoặc đang chuẩn bị (món đã ngừng bán / lưu trữ không còn việc nội dung)
_PRODUCT_STATUSES = (ProductStatus.DRAFT, ProductStatus.PENDING_REVIEW, ProductStatus.PUBLISHED, ProductStatus.PAUSED)
_DROP_STATUSES = (DropStatus.DRAFT, DropStatus.PENDING_REVIEW, DropStatus.SCHEDULED, DropStatus.OPEN)
# bài đã lên kênh (có số liệu để tính)
_LIVE = (PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED, PostStatus.HIDDEN, PostStatus.REMOVED)


def _kpi(posts: list[ScheduledPost], metrics: dict, attrs: dict) -> dict[str, Any]:
    out: dict[str, Any] = {
        "posts": len(posts),
        "reach": 0,
        "interactions": 0,
        "clicks": 0,
        "orders": 0,
        "revenue_vnd": 0,
    }
    out["measured_at"] = None
    for p in posts:
        m = metrics.get(p.id)
        if m:
            out["reach"] += m.reach
            out["interactions"] += m.likes + m.comments + m.shares + m.saves
            out["clicks"] += m.clicks
            out["measured_at"] = max(out["measured_at"] or m.captured_at, m.captured_at)
        n, rev = attrs.get(p.id, (0, 0))
        out["orders"] += n
        out["revenue_vnd"] += rev
    return out


def _social_cell(
    channel: str,
    draft: ContentDraft | None,
    post: ScheduledPost | None,
    approved_at: datetime | None,
    kpi: dict[str, Any] | None,
) -> dict[str, Any]:
    if draft is None:
        return {"channel": channel, "state": "none"}
    needs_fix = draft.status == DraftStatus.PENDING_REVIEW and not can_approve(draft.check_status)
    if draft.status == DraftStatus.DRAFTING:
        state, raw = "drafting", "drafting"
    elif post is not None and post.status == PostStatus.PUBLISHED:
        state, raw = "published", post.status.value
    elif post is not None and post.status == PostStatus.DRAFT_PUSHED:
        state, raw = "scheduled", post.status.value  # TikTok: nháp đã vào app = đã hẹn giờ
    elif post is not None and post.status == PostStatus.FAILED:
        state, raw = "failed", post.status.value
    elif post is not None and post.status in (PostStatus.HIDDEN, PostStatus.REMOVED):
        state, raw = "removed", post.status.value
    elif (post is not None and post.status in (PostStatus.APPROVED, PostStatus.PUBLISHING)) or draft.status in (
        DraftStatus.APPROVED,
        DraftStatus.SCHEDULED,
    ):
        state, raw = "scheduled", post.status.value if post else draft.status.value
    elif draft.status == DraftStatus.PUBLISHED:
        state, raw = "published", draft.status.value
    else:  # pending_review / returned, bài trên lịch còn «planned»
        state, raw = "pending", draft.status.value
    live = post is not None and post.status in _LIVE
    return {
        "channel": channel,
        "state": state,
        "raw": raw,
        "needs_fix": needs_fix,
        "draft_id": draft.id,
        "post_id": post.id if post else None,
        "created_at": draft.created_at,
        "approved_at": approved_at,
        "scheduled_at": post.scheduled_at if post else None,
        "published_at": post.published_at if post else None,
        "external_url": post.external_url if post else None,
        "error": post.error if post and post.status == PostStatus.FAILED else None,
        "kpi": kpi if live else None,
    }


def _product_web(p: Product) -> dict[str, Any]:
    state = {
        ProductStatus.DRAFT: "drafting",
        ProductStatus.PENDING_REVIEW: "pending",
        ProductStatus.PUBLISHED: "published",
    }.get(p.status, "removed")
    return {
        "channel": WEBSITE,
        "state": state,
        "raw": p.status.value,
        "created_at": p.created_at,
        "published_at": p.published_at if state == "published" else None,
        "external_url": facts.store_url(facts.product_path(p)) if state == "published" else None,
    }


def _drop_web(d: Drop) -> dict[str, Any]:
    state = {
        DropStatus.DRAFT: "drafting",
        DropStatus.PENDING_REVIEW: "pending",
        DropStatus.SCHEDULED: "scheduled",
        DropStatus.CANCELLED: "removed",
    }.get(d.status, "published")
    return {
        "channel": WEBSITE,
        "state": state,
        "raw": d.status.value,
        "created_at": d.created_at,
        "scheduled_at": d.opens_at if state == "scheduled" else None,
        "published_at": d.opens_at if state == "published" else None,
        "external_url": facts.store_url(facts.drop_path(d)) if state == "published" else None,
    }


def stage(cells: list[dict[str, Any]]) -> str:
    """Bước công việc của một món (mỗi món đúng một tab): việc chờ chị trước, rồi kênh chưa có bài, rồi chờ giờ."""
    states = {c["state"] for c in cells if c["state"] != "na"}
    if states & {"pending", "failed"}:
        return "review"
    if states & {"none", "drafting"}:
        return "todo"
    if "scheduled" in states:
        return "scheduled"
    return "published"


async def board(
    db: AsyncSession,
    *,
    tab: str = "all",
    q: str | None = None,
    channel: str | None = None,
    page: int = 1,
    size: int = 50,
) -> dict[str, Any]:
    products, drops = await _refs(db)
    return _page(await _rows(db, products, drops), tab=tab, q=q, channel=channel, page=page, size=size)


async def one(db: AsyncSession, kind: str, ref_id: uuid.UUID) -> dict[str, Any] | None:
    """Một dòng của bảng (Hồ sơ nội dung): kể cả món đã ngừng bán / đợt đã đóng."""
    obj = await db.get(Drop if kind == "drop" else Product, ref_id)
    if obj is None:
        return None
    rows = await _rows(db, [obj] if kind == "product" else [], [obj] if kind == "drop" else [])  # type: ignore[list-item]
    rows[0]["stage"] = stage(rows[0]["channels"])
    return rows[0]


async def _refs(db: AsyncSession) -> tuple[list[Product], list[Drop]]:
    products = list(
        (
            await db.execute(
                select(Product)
                .where(Product.status.in_(_PRODUCT_STATUSES))
                .order_by(Product.published_at.desc().nulls_last(), Product.created_at.desc())
            )
        ).scalars()
    )
    drop_has = select(ContentDraft.drop_id).where(ContentDraft.drop_id.is_not(None))
    drops = list(
        (
            await db.execute(
                select(Drop)
                .where(or_(Drop.status.in_(_DROP_STATUSES), Drop.id.in_(drop_has)))
                .order_by(Drop.opens_at.desc().nulls_last())
                .limit(20)
            )
        ).scalars()
    )
    return products, drops


async def _rows(db: AsyncSession, products: list[Product], drops: list[Drop]) -> list[dict[str, Any]]:
    pids = [p.id for p in products]
    dids = [d.id for d in drops]

    # mọi bản nháp của các món (cả bản đã lưu trữ — bài cũ vẫn có số liệu)
    drafts = list(
        (
            await db.execute(
                select(ContentDraft)
                .where(
                    or_(
                        ContentDraft.drop_id.in_(dids),
                        ContentDraft.product_id.in_(pids) & ContentDraft.drop_id.is_(None),
                    )
                )
                .order_by(ContentDraft.created_at)
            )
        ).scalars()
    )
    by_id = {d.id: d for d in drafts}
    current: dict[tuple[uuid.UUID, str], ContentDraft] = {}  # (món, kênh) → bản hiện tại (mới nhất, chưa lưu trữ)
    for d in drafts:
        if d.status != DraftStatus.ARCHIVED:
            current[(d.drop_id or d.product_id, d.channel.value)] = d  # type: ignore[index]

    posts = list(
        (
            await db.execute(
                select(ScheduledPost)
                .where(ScheduledPost.draft_id.in_(list(by_id)), ScheduledPost.status != PostStatus.CANCELLED)
                .order_by(ScheduledPost.created_at)
            )
        ).scalars()
    )
    latest: dict[uuid.UUID, ScheduledPost] = {}
    live_by_ref: dict[uuid.UUID, list[ScheduledPost]] = {}
    for p in posts:
        latest[p.draft_id] = p
        if p.status in _LIVE:
            d = by_id[p.draft_id]
            live_by_ref.setdefault(d.drop_id or d.product_id, []).append(p)  # type: ignore[arg-type]
    live = [p for ps in live_by_ref.values() for p in ps]
    metrics = await latest_metrics(db, [p.id for p in live])
    attrs = await attribution(db, live)
    item_ids = [d.approval_item_id for d in current.values() if d.approval_item_id]
    decided = (
        dict(
            (
                await db.execute(select(ApprovalItem.id, ApprovalItem.decided_at).where(ApprovalItem.id.in_(item_ids)))
            ).all()
        )
        if item_ids
        else {}
    )

    def cells(ref: uuid.UUID, web: dict[str, Any], allowed: set[str]) -> list[dict[str, Any]]:
        out = [web]
        for ch in BOARD_CHANNELS[1:]:
            if ch not in allowed:
                out.append({"channel": ch, "state": "na"})
                continue
            d = current.get((ref, ch))
            p = latest.get(d.id) if d else None
            kpi = _kpi([p], metrics, attrs) if p is not None and p.status in _LIVE else None
            out.append(_social_cell(ch, d, p, decided.get(d.approval_item_id) if d else None, kpi))
        return out

    def updated(ref: uuid.UUID, default: datetime) -> datetime:
        return max([d.updated_at for (r, _), d in current.items() if r == ref], default=default)

    product_chs = {c.value for c, _ in PRODUCT_CHANNELS}
    drop_chs = {c.value for c, _ in DROP_CHANNELS}
    rows: list[dict[str, Any]] = []
    for d in drops:
        cs = cells(d.id, _drop_web(d), drop_chs)
        rows.append(
            {
                "kind": "drop",
                "id": d.id,
                "name": d.title,
                "subtitle": f"Đợt {d.code}",
                "image_url": None,
                "status": d.status.value,
                "channels": cs,
                "kpi": _kpi(live_by_ref.get(d.id, []), metrics, attrs),
                "updated_at": updated(d.id, d.updated_at),
            }
        )
    for p in products:
        keys = facts.image_keys(p)
        cs = cells(p.id, _product_web(p), product_chs)
        rows.append(
            {
                "kind": "product",
                "id": p.id,
                "name": p.name,
                "subtitle": p.subtitle,
                "image_url": facts.file_url(keys[0]) if keys else None,
                "status": p.status.value,
                "channels": cs,
                "kpi": _kpi(live_by_ref.get(p.id, []), metrics, attrs),
                "updated_at": updated(p.id, p.updated_at),
            }
        )

    return rows


def _page(rows: list[dict[str, Any]], *, tab: str, q: str | None, channel: str | None, page: int, size: int):
    if q:
        rows = [r for r in rows if matches_vi(r["name"], q)]
    if channel in BOARD_CHANNELS:
        rows = [r for r in rows if any(c["channel"] == channel and c["state"] != "na" for c in r["channels"])]
    for r in rows:
        r["stage"] = stage([c for c in r["channels"] if not channel or c["channel"] == channel])
    counts = {t: sum(r["stage"] == t for r in rows) for t in TABS[:-1]}
    counts["all"] = len(rows)
    shown = rows if tab not in TABS[:-1] else [r for r in rows if r["stage"] == tab]
    total = len(shown)
    start = (page - 1) * size
    return {
        "items": shown[start : start + size],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
        "counts": counts,
    }
