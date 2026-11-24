"""Việc nền của xưởng nội dung (giờ cron là giờ Việt Nam)."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from app import ai
from app.core.jobs import cron, job
from app.core.timeutil import local_today, week_start
from app.modules.content import planner, publishing, service, video

log = logging.getLogger("app.content.jobs")


@cron("content.compose_pending", minute=set(range(0, 60, 2)))
async def compose_pending(ctx: dict[str, Any]) -> int:
    """Soạn các bản `drafting` (tạo khi sản phẩm lên web / mở đợt)."""
    async with ctx["db"]() as db:
        n = await service.compose_pending(db)
        await db.commit()
    return n


@cron("content.publish_due", second={10})
async def publish_due(ctx: dict[str, Any]) -> int:
    """Mỗi phút: đăng bài đã duyệt tới giờ (thử lại có giới hạn khi lỗi)."""
    async with ctx["db"]() as db:
        n = await publishing.publish_due(db)
        await db.commit()
    return n


@cron("content.pull_metrics", minute={15})
async def pull_metrics(ctx: dict[str, Any]) -> int:
    """Mỗi giờ: kéo số liệu bài đã đăng + gắn đơn theo mã nguồn trong link."""
    async with ctx["db"]() as db:
        n = await publishing.pull_metrics(db)
        await db.commit()
    return n


@cron("content.weekly_learn", weekday="mon", hour={7}, minute={0})
async def weekly_learn(ctx: dict[str, Any]) -> None:
    """Sáng thứ Hai: rút kinh nghiệm tuần qua (dùng cho gợi ý lịch tuần này)."""
    async with ctx["db"]() as db:
        try:
            await publishing.learn(db)
        except ai.AIError as e:
            log.warning("Rút kinh nghiệm lỗi: %s", e)
        await db.commit()


@cron("content.plan_next_week", weekday="sun", hour={20}, minute={0})
async def plan_next_week(ctx: dict[str, Any]) -> None:
    """Tối Chủ nhật: xếp lịch tuần tới, gợi ý ô trống (chị gật mới soạn)."""
    async with ctx["db"]() as db:
        await planner.plan_week(db, week_start(local_today() + timedelta(days=1)))
        await db.commit()


@job("content.render_video")
async def render_video(ctx: dict[str, Any], asset_id: str) -> str | None:
    async with ctx["db"]() as db:
        asset = await video.render_job(db, uuid.UUID(asset_id))
        await db.commit()
        return asset.edit_spec.get("render") if asset else None
