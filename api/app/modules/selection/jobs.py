"""Việc nền của bàn chọn: định kỳ học lại gu của chị (c6)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.jobs import cron, job
from app.modules.selection import service

log = logging.getLogger("app.selection")


@job("selection.retrain_taste")
async def retrain_taste(ctx: dict[str, Any], category_id: str | None = None, force: bool = False) -> int:
    """Học lại hồ sơ gu có món mới chọn/loại. `category_id` = chỉ một nhóm; bỏ trống = mọi hồ sơ đang chờ."""
    done = 0
    async with ctx["db"]() as db:
        cats = [uuid.UUID(category_id)] if category_id else await service.taste_categories(db)
        for cat in cats or [None]:
            if await service.retrain_taste(db, cat, force=force):
                done += 1
        await db.commit()
    return done


@cron("selection.retrain_taste_hourly", minute={15})
async def retrain_taste_hourly(ctx: dict[str, Any]) -> None:
    n = await retrain_taste(ctx)
    if n:
        log.info("Đã học lại %d hồ sơ gu", n)
