"""Lịch đăng (f3): giờ đăng theo kênh (mặc định → học từ số liệu), tìm ô trống, xếp lại bài trùng chỗ."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Channel
from app.core.timeutil import VN_TZ, now_utc, to_local
from app.modules.content.channels import CONTENT_CHANNELS, DEFAULT_TIMES, MAX_POSTS_PER_DAY, POSTING_WEEKDAYS
from app.modules.content.models import PostMetric, PostStatus, ScheduledPost

ACTIVE = (
    PostStatus.PLANNED,
    PostStatus.APPROVED,
    PostStatus.PUBLISHING,
    PostStatus.PUBLISHED,
    PostStatus.DRAFT_PUSHED,
    PostStatus.FAILED,
)
MIN_POSTS_TO_LEARN = 4
WEEKDAY_LABELS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
WEEKDAY_NAMES = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]


def src_code(post: ScheduledPost) -> str:
    """Mã bài trong link (?src=): 8 ký tự đầu của id — không cần thêm cột."""
    return post.id.hex[:8]


async def best_times(db: AsyncSession) -> dict[Channel, tuple[tuple[int, int], str]]:
    """Giờ đăng tốt nhất từng kênh: đủ số liệu thì lấy giờ có điểm trung bình cao nhất, chưa đủ thì giờ mặc định."""
    latest = (
        select(PostMetric.scheduled_post_id, func.max(PostMetric.captured_at).label("at"))
        .group_by(PostMetric.scheduled_post_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(ScheduledPost.channel, ScheduledPost.published_at, PostMetric)
            .join(latest, latest.c.scheduled_post_id == ScheduledPost.id)
            .join(
                PostMetric,
                (PostMetric.scheduled_post_id == latest.c.scheduled_post_id) & (PostMetric.captured_at == latest.c.at),
            )
            .where(ScheduledPost.published_at.is_not(None))
        )
    ).all()
    scores: dict[Channel, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[Channel, int] = defaultdict(int)
    for ch, published_at, m in rows:
        hour = to_local(published_at).hour
        scores[ch][hour].append(m.reach / 100 + m.clicks / 5 + m.comments / 2 + m.orders_attributed * 20)
        counts[ch] += 1
    out: dict[Channel, tuple[tuple[int, int], str]] = {}
    for ch in CONTENT_CHANNELS:
        if counts[ch] >= MIN_POSTS_TO_LEARN:
            hour = max(scores[ch], key=lambda h: sum(scores[ch][h]) / len(scores[ch][h]))
            out[ch] = ((hour, 0), "metrics")
        else:
            out[ch] = (DEFAULT_TIMES.get(ch, (20, 0)), "default")
    return out


def at_local(day: date, hm: tuple[int, int]) -> datetime:
    return datetime.combine(day, time(hm[0], hm[1]), tzinfo=VN_TZ)


async def _day_load(db: AsyncSession, start: datetime, end: datetime, exclude: set) -> dict[date, list[Channel]]:
    rows = (
        await db.execute(
            select(ScheduledPost.id, ScheduledPost.scheduled_at, ScheduledPost.channel).where(
                ScheduledPost.status.in_(ACTIVE),
                ScheduledPost.scheduled_at >= start,
                ScheduledPost.scheduled_at < end,
            )
        )
    ).all()
    load: dict[date, list[Channel]] = defaultdict(list)
    for pid, at, ch in rows:
        if pid not in exclude:
            load[to_local(at).date()].append(ch)
    return load


async def next_slot(
    db: AsyncSession,
    channel: Channel,
    *,
    earliest: datetime | None = None,
    exclude: set | None = None,
    times: dict | None = None,
) -> datetime:
    """Ô đăng gần nhất còn trống cho kênh: Thứ Hai–Thứ Bảy, mỗi kênh tối đa một bài/ngày, tối đa 3 bài/ngày."""
    now = now_utc() + timedelta(minutes=10)
    earliest = max(earliest or now, now)
    times = times or await best_times(db)
    hm = times.get(channel, (DEFAULT_TIMES.get(channel, (20, 0)), "default"))[0]
    day = to_local(earliest).date()
    horizon = 28
    load = await _day_load(
        db, at_local(day, (0, 0)), at_local(day + timedelta(days=horizon + 1), (0, 0)), exclude or set()
    )
    for i in range(horizon):
        d = day + timedelta(days=i)
        if d.weekday() not in POSTING_WEEKDAYS:
            continue
        at = at_local(d, hm)
        if at < earliest:
            continue
        chans = load.get(d, [])
        if channel in chans or len(chans) >= MAX_POSTS_PER_DAY:
            continue
        return at
    return at_local(day + timedelta(days=horizon), hm)


def week_bounds(ws: date) -> tuple[datetime, datetime]:
    return at_local(ws, (0, 0)), at_local(ws + timedelta(days=7), (0, 0))


def week_label(ws: date) -> str:
    return f"Tuần {ws.isocalendar().week} ({ws:%d/%m}–{ws + timedelta(days=6):%d/%m})"
