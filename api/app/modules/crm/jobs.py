"""Việc nền của crm: tóm tắt sổ khách (hoãn ~10 phút sau tin cuối), quét nhắc mua lại mỗi sáng 9 giờ (giờ VN),
hạn cảm nhận «Mời thử cùng» lúc 9 giờ 10."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.jobs import cron, job
from app.modules.crm import cotrial, service

log = logging.getLogger("app.crm")


@job("crm.refresh_profile")
async def refresh_profile(ctx: dict[str, Any], customer_id: str) -> None:
    async with ctx["db"]() as db:
        await service.refresh_profile(db, uuid.UUID(customer_id))
        await db.commit()


@cron("crm.reorder_due", hour={9}, minute={0})
async def reorder_due(ctx: dict[str, Any]) -> dict[str, int]:
    async with ctx["db"]() as db:
        stats = await service.run_due(db)
        await db.commit()
    log.info("Nhắc mua lại: %s", stats)
    return stats


@cron("crm.cotrial_deadlines", hour={9}, minute={10})
async def cotrial_deadlines(ctx: dict[str, Any]) -> dict[str, int]:
    """«Mời thử cùng»: nhắc người dùng thử trước hạn cảm nhận 2 ngày; quá hạn → lỡ hạn, gắn loại trừ trong sổ."""
    async with ctx["db"]() as db:
        stats = await cotrial.run_deadlines(db)
        await db.commit()
    log.info("Hạn cảm nhận dùng thử: %s", stats)
    return stats
