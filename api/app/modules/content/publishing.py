"""Đăng tự động (f4) và Đo và học (f7).

- Bài `approved` tới giờ → job đăng qua tích hợp `social`. TikTok chỉ đẩy bản nháp vào app (`draft_pushed`), chị bấm
  đăng trong app rồi báo «Đã đăng» (hoặc cron số liệu nhận ra).
- Lỗi → thử lại tối đa 3 lần (5 phút, 15 phút) → `failed` + việc chờ chị `content.retry_publish`.
- Số liệu: cron kéo `post_metrics`; đơn gắn với bài qua mã nguồn trong link `?src=<mã bài>` — đọc `orders.raw["src"]`
  (chỉ đọc bảng orders; module orders lưu tham số `src` của trang đặt hàng vào `raw`).

Chọn driver theo kênh: biến môi trường `SOCIAL_PUBLISH_DRIVERS="facebook=meta_publish,instagram=meta_publish,
threads=meta_publish,tiktok=tiktok_draft_publish,zalo_oa=zalo_oa_publish"`; kênh không khai báo dùng driver
`SOCIAL_DRIVER` chung (mặc định `mock`).
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.enums import Channel
from app.core.errors import AppError, BadRequest, Conflict
from app.core.timeutil import local_today, now_utc, to_local
from app.integrations import get_driver
from app.integrations.social import SocialPost
from app.modules.catalog.models import Drop, Product
from app.modules.content import facts
from app.modules.content.ai_io import InsightIn, InsightOut, PostStat
from app.modules.content.channels import channel_label
from app.modules.content.checks import money_mentions
from app.modules.content.models import (
    ContentDraft,
    ContentInsight,
    DraftStatus,
    MediaAsset,
    MediaStatus,
    PostMetric,
    PostStatus,
    ScheduledPost,
)
from app.modules.content.schedule import WEEKDAY_NAMES, src_code
from app.modules.content.service import ACTION_INSIGHT, ACTION_RETRY
from app.modules.orders.models import Order, OrderStatus

log = logging.getLogger("app.content.publish")

MAX_ATTEMPTS = 3
BACKOFF_MINUTES = [0, 5, 15]
AI_LABEL = "Nội dung có sự hỗ trợ của AI, mình đã đọc và duyệt."
LINK_IN_BIO = (Channel.INSTAGRAM, Channel.TIKTOK)  # link trong chú thích không bấm được


def driver_for(channel: Channel) -> Any:
    spec = os.environ.get("SOCIAL_PUBLISH_DRIVERS", "")
    mapping = dict(p.split("=", 1) for p in spec.replace(" ", "").split(",") if "=" in p)
    name = mapping.get(channel.value)
    return get_driver("social", name) if name else get_driver("social")


async def _video_url(db: AsyncSession, draft: ContentDraft) -> str | None:
    for mid in draft.media_asset_ids:
        try:
            asset = await db.get(MediaAsset, uuid.UUID(str(mid)))
        except ValueError:
            continue
        if asset and asset.status == MediaStatus.APPROVED and asset.kind.value == "video":
            return facts.file_url(asset.storage_key)
    return None


async def build_social_post(db: AsyncSession, draft: ContentDraft, post: ScheduledPost) -> SocialPost:
    product = await db.get(Product, draft.product_id) if draft.product_id else None
    keys = facts.image_keys(product) if product else []
    parts = [draft.body.strip()]
    if draft.hashtags:
        parts.append(" ".join(str(h) for h in draft.hashtags))
    link = draft.link_url
    if link and draft.channel not in LINK_IN_BIO and draft.channel != Channel.FACEBOOK:
        parts.append(link)
    if draft.ai_generated:
        parts.append(AI_LABEL)
    text = "\n\n".join(p for p in parts if p)
    video = await _video_url(db, draft)
    urls: list[str] = []
    kind = "none"
    if video and draft.channel in (Channel.TIKTOK, Channel.INSTAGRAM, Channel.FACEBOOK):
        urls, kind = [video], "video"
    elif keys:
        if draft.channel == Channel.INSTAGRAM:
            order = [int(s.get("image_index", 0)) for s in draft.script if isinstance(s, dict) and "caption" in s]
            picked = [keys[i] for i in order if 0 <= i < len(keys)] or keys
            urls = [facts.file_url(k) for k in picked[:10]]
        elif draft.channel == Channel.FACEBOOK:
            urls = [facts.file_url(k) for k in keys[:4]]
        else:
            urls = [facts.file_url(keys[0])]
        kind = "carousel" if len(urls) > 1 else "image"
    return SocialPost(
        channel=draft.channel,
        text=text,
        media_urls=urls,
        media_kind=kind,  # type: ignore[arg-type]
        link_url=link if draft.channel == Channel.FACEBOOK else None,
        mode="draft" if draft.channel == Channel.TIKTOK else "publish",
        ai_label=draft.ai_generated,
    )


def _due(post: ScheduledPost, now: datetime) -> bool:
    if post.scheduled_at > now:
        return False
    wait = BACKOFF_MINUTES[min(post.attempts, len(BACKOFF_MINUTES) - 1)]
    return post.attempts == 0 or post.updated_at + timedelta(minutes=wait) <= now


async def publish_one(db: AsyncSession, post: ScheduledPost) -> ScheduledPost:
    """Đăng một bài đã duyệt. Lỗi thì đếm lần thử; hết lượt → `failed` + việc chờ chị."""
    draft = await db.get(ContentDraft, post.draft_id)
    if draft is None or post.status not in (PostStatus.APPROVED, PostStatus.PUBLISHING):
        return post
    post.status = PostStatus.PUBLISHING
    await db.flush()
    try:
        sp = await build_social_post(db, draft, post)
        res = await driver_for(post.channel).publish(sp)
    except Exception as e:
        msg = e.message if isinstance(e, AppError) else str(e)
        post.attempts += 1
        post.error = msg[:2000]
        if post.attempts >= MAX_ATTEMPTS:
            post.status = PostStatus.FAILED
            await control.propose(
                ACTION_RETRY,
                f"Đăng {channel_label(post.channel)} lỗi {post.attempts} lần — chị xem lại",
                {"scheduled_post_id": str(post.id)},
                preview={
                    "error": post.error,
                    "channel_label": channel_label(post.channel),
                    "title": draft.title,
                    "body": draft.body,
                },
                db=db,
                summary=post.error[:200],
                rationale="Hệ thống đã thử lại tự động nhưng vẫn lỗi.",
                ref_type="scheduled_posts",
                ref_id=post.id,
                dedupe_key=f"retry:{post.id}",
                ai_generated=False,
            )
        else:
            post.status = PostStatus.APPROVED
        post.updated_at = now_utc()
        await control.audit(
            db,
            "content.publish_failed",
            entity_type="scheduled_posts",
            entity_id=post.id,
            summary=f"Đăng {channel_label(post.channel)} lỗi (lần {post.attempts}): {msg[:200]}",
        )
        await db.flush()
        log.warning("Đăng bài %s lỗi lần %s: %s", post.id, post.attempts, msg)
        return post
    post.external_post_id = res.external_id
    post.external_url = res.url
    post.error = None
    post.ai_label_applied = sp.ai_label
    if res.status == "draft_pushed":
        post.status = PostStatus.DRAFT_PUSHED
        summary = "Đã đẩy bản nháp vào TikTok, chờ chị bấm đăng trong app"
    else:
        post.status = PostStatus.PUBLISHED
        post.published_at = res.published_at or now_utc()
        draft.status = DraftStatus.PUBLISHED
        summary = f"Đã đăng {channel_label(post.channel)}"
    await control.audit(
        db,
        "content.published",
        entity_type="scheduled_posts",
        entity_id=post.id,
        summary=summary,
        data={"external_id": res.external_id, "url": res.url, "ai_label": sp.ai_label},
    )
    await db.flush()
    if post.status == PostStatus.PUBLISHED:
        await events.emit("post.published", {"scheduled_post_id": str(post.id)}, db=db)
    return post


async def publish_due(db: AsyncSession, *, limit: int = 20) -> int:
    now = now_utc()
    rows = list(
        (
            await db.execute(
                select(ScheduledPost)
                .where(ScheduledPost.status == PostStatus.APPROVED, ScheduledPost.scheduled_at <= now)
                .order_by(ScheduledPost.scheduled_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    n = 0
    for post in rows:
        if _due(post, now):
            await publish_one(db, post)
            n += 1
    return n


async def apply_retry(db: AsyncSession, payload: dict[str, Any]) -> control.HandlerResult:
    post = await db.get(ScheduledPost, uuid.UUID(payload["scheduled_post_id"]))
    if post is None or post.status not in (PostStatus.FAILED, PostStatus.APPROVED):
        raise Conflict("Bài này không còn ở trạng thái lỗi.", code="not_failed")
    post.status = PostStatus.APPROVED
    post.attempts = 0
    if post.scheduled_at < now_utc():
        post.scheduled_at = now_utc()
    await db.flush()
    await publish_one(db, post)
    if post.status not in (PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED):
        raise Conflict(f"Vẫn chưa đăng được: {post.error}", code="publish_failed")
    return control.HandlerResult(
        result={"status": post.status.value, "url": post.external_url},
        summary=f"Đã đăng lại {channel_label(post.channel)}",
        ref_type="scheduled_posts",
        ref_id=post.id,
    )


async def mark_published(db: AsyncSession, post: ScheduledPost, user: Any, url: str | None = None) -> ScheduledPost:
    """TikTok: chị đã bấm đăng bản nháp trong app."""
    if post.status != PostStatus.DRAFT_PUSHED:
        raise Conflict("Chỉ bài TikTok đã đẩy bản nháp mới cần báo «Đã đăng».", code="not_draft_pushed")
    if url and not url.startswith("https://"):
        raise BadRequest("Link bài phải bắt đầu bằng https://")
    post.status = PostStatus.PUBLISHED
    post.published_at = now_utc()
    post.external_url = url or post.external_url
    draft = await db.get(ContentDraft, post.draft_id)
    if draft:
        draft.status = DraftStatus.PUBLISHED
    await control.audit(
        db,
        "content.marked_published",
        user=user,
        entity_type="scheduled_posts",
        entity_id=post.id,
        summary="Chị báo đã đăng bản nháp TikTok",
        data={"url": url},
    )
    await db.flush()
    await events.emit("post.published", {"scheduled_post_id": str(post.id)}, db=db)
    return post


# ---- đo và học (f7) ----------------------------------------------------------------------------------------------


async def attribution(db: AsyncSession, posts: list[ScheduledPost]) -> dict[uuid.UUID, tuple[int, int]]:
    """Đơn gắn với bài qua `orders.raw->>'src'` = mã bài. Trả {post_id: (số đơn, doanh thu)} (bỏ đơn huỷ/nháp)."""
    codes = {src_code(p): p.id for p in posts}
    if not codes:
        return {}
    src = func.lower(Order.raw["src"].astext)
    rows = (
        await db.execute(
            select(src, func.count(Order.id), func.coalesce(func.sum(Order.total_vnd), 0))
            .where(src.in_(list(codes)), Order.status.not_in((OrderStatus.CANCELLED, OrderStatus.DRAFT)))
            .group_by(src)
        )
    ).all()
    return {codes[c]: (int(n), int(rev)) for c, n, rev in rows if c in codes}


async def pull_metrics(db: AsyncSession, *, days: int = 30) -> int:
    since = now_utc() - timedelta(days=days)
    posts = list(
        (
            await db.execute(
                select(ScheduledPost).where(
                    ScheduledPost.status.in_((PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED)),
                    ScheduledPost.external_post_id.is_not(None),
                    ScheduledPost.updated_at >= since,
                )
            )
        ).scalars()
    )
    attrs = await attribution(db, posts)
    n = 0
    for p in posts:
        try:
            m = await driver_for(p.channel).post_metrics(p.channel, p.external_post_id or "")
        except Exception as e:
            log.warning("Lấy số liệu bài %s lỗi: %s", p.id, e)
            continue
        orders, revenue = attrs.get(p.id, (0, 0))
        db.add(
            PostMetric(
                scheduled_post_id=p.id,
                captured_at=now_utc(),
                impressions=m.impressions,
                reach=m.reach,
                likes=m.likes,
                comments=m.comments,
                shares=m.shares,
                saves=m.saves,
                clicks=m.clicks,
                video_views=m.video_views,
                orders_attributed=orders,
                revenue_attributed_vnd=revenue,
            )
        )
        n += 1
    await db.flush()
    return n


async def latest_metrics(db: AsyncSession, post_ids: list[uuid.UUID]) -> dict[uuid.UUID, PostMetric]:
    if not post_ids:
        return {}
    sub = (
        select(PostMetric.scheduled_post_id, func.max(PostMetric.captured_at).label("at"))
        .where(PostMetric.scheduled_post_id.in_(post_ids))
        .group_by(PostMetric.scheduled_post_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(PostMetric).join(
                sub, (PostMetric.scheduled_post_id == sub.c.scheduled_post_id) & (PostMetric.captured_at == sub.c.at)
            )
        )
    ).scalars()
    return {m.scheduled_post_id: m for m in rows}


async def performance(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """Bảng «bài nào ra đơn»: bài đã đăng trong kỳ, số liệu mới nhất, số đơn/doanh thu gắn được (tính lại từ orders)."""
    since = now_utc() - timedelta(days=days)
    posts = list(
        (
            await db.execute(
                select(ScheduledPost)
                .where(
                    ScheduledPost.status.in_((PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED)),
                    ScheduledPost.scheduled_at >= since,
                )
                .order_by(ScheduledPost.scheduled_at.desc())
            )
        ).scalars()
    )
    attrs = await attribution(db, posts)
    metrics = await latest_metrics(db, [p.id for p in posts])
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
    rows = []
    for p in posts:
        d = drafts.get(p.draft_id)
        m = metrics.get(p.id)
        orders, revenue = attrs.get(p.id, (0, 0))
        rows.append(
            {
                "scheduled_post_id": p.id,
                "channel": p.channel.value,
                "channel_label": channel_label(p.channel),
                "status": p.status.value,
                "title": (d.title if d else None) or "Bài đăng",
                "name": names.get(d.product_id) if d and d.product_id else (dnames.get(d.drop_id) if d else None),
                "product_id": d.product_id if d else None,
                "published_at": p.published_at or p.scheduled_at,
                "external_url": p.external_url,
                "src_code": src_code(p),
                "reach": m.reach if m else 0,
                "likes": m.likes if m else 0,
                "comments": m.comments if m else 0,
                "shares": m.shares if m else 0,
                "clicks": m.clicks if m else 0,
                "video_views": m.video_views if m else 0,
                "orders": orders,
                "revenue_vnd": revenue,
                "measured_at": m.captured_at if m else None,
            }
        )
    rows.sort(key=lambda r: (r["orders"], r["revenue_vnd"], r["clicks"], r["reach"]), reverse=True)
    insight = await db.scalar(select(ContentInsight).order_by(ContentInsight.created_at.desc()).limit(1))
    return {
        "days": days,
        "posts": rows,
        "totals": {
            "posts": len(rows),
            "orders": sum(r["orders"] for r in rows),
            "revenue_vnd": sum(r["revenue_vnd"] for r in rows),
            "reach": sum(r["reach"] for r in rows),
        },
        "insight": insight,
    }


async def learn(db: AsyncSession, *, days: int = 14) -> control.ProposeOutcome:
    """AI đọc số liệu kỳ qua, rút 2–3 nhận xét → `content_insights` (dùng cho gợi ý lịch tuần sau)."""
    perf = await performance(db, days=days)
    drafts = {
        d.id: d
        for d in (
            await db.execute(
                select(ContentDraft)
                .join(ScheduledPost, ScheduledPost.draft_id == ContentDraft.id)
                .where(ScheduledPost.id.in_([r["scheduled_post_id"] for r in perf["posts"]]))
            )
        ).scalars()
    }
    post_draft = dict(
        (
            await db.execute(
                select(ScheduledPost.id, ScheduledPost.draft_id).where(
                    ScheduledPost.id.in_([r["scheduled_post_id"] for r in perf["posts"]])
                )
            )
        ).all()
    )
    stats = []
    for r in perf["posts"]:
        d = drafts.get(post_draft.get(r["scheduled_post_id"]))
        local = to_local(r["published_at"])
        stats.append(
            PostStat(
                post_id=str(r["scheduled_post_id"]),
                title=r["title"],
                channel=r["channel"],
                format=d.format.value if d else "post",
                weekday=WEEKDAY_NAMES[local.weekday()],
                hour=local.hour,
                length=len(d.body) if d else 0,
                has_price=bool(d and money_mentions(d.body)),
                reach=r["reach"],
                likes=r["likes"],
                comments=r["comments"],
                shares=r["shares"],
                clicks=r["clicks"],
                orders=r["orders"],
                revenue_vnd=r["revenue_vnd"],
            )
        )
    end = local_today()
    start = end - timedelta(days=days)
    res = await ai.run(
        "content.insights", InsightIn(period_label=f"{start:%d/%m}–{end:%d/%m}", posts=stats), InsightOut
    )
    out = res.output
    valid = {s.post_id for s in stats}
    payload = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "summary": out.summary,
        "findings": [f.model_dump() for f in out.findings[:3]],
        "top_post_ids": [p for p in out.top_post_ids if p in valid][:5],
        "ai_run_id": str(res.run_id),
    }
    return await control.propose(
        ACTION_INSIGHT,
        "Rút kinh nghiệm từ số liệu bài",
        payload,
        preview={"summary": out.summary},
        db=db,
        summary=out.summary,
        rationale=f"Đọc {len(stats)} bài trong {days} ngày",
        ai_run_id=res.run_id,
    )


async def apply_insight(db: AsyncSession, payload: dict[str, Any]) -> ContentInsight:
    row = ContentInsight(
        period_start=date.fromisoformat(payload["period_start"]),
        period_end=date.fromisoformat(payload["period_end"]),
        summary=payload["summary"],
        findings=list(payload.get("findings") or []),
        top_post_ids=list(payload.get("top_post_ids") or []),
        ai_run_id=uuid.UUID(payload["ai_run_id"]) if payload.get("ai_run_id") else None,
    )
    db.add(row)
    await db.flush()
    return row


def channel_order_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[r["channel"]] += r["orders"]
    return dict(out)
