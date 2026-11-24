"""Việc nền của finance: báo cáo tuần (sáng thứ Hai) và sao lưu CSDL hằng ngày. Giờ là giờ Việt Nam."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from app.core.jobs import cron
from app.core.timeutil import local_today, week_start
from app.modules.finance import service
from app.modules.finance.models import BackupStatus, BackupTrigger

log = logging.getLogger("app.finance")


@cron("finance.weekly_report", weekday="mon", hour={6}, minute={0})
async def weekly_report(ctx: dict[str, Any]) -> str:
    """6 giờ sáng thứ Hai: lập báo cáo tuần trước (Thứ Hai → Chủ nhật)."""
    ws = week_start(local_today()) - timedelta(days=7)
    async with ctx["db"]() as db:
        report = await service.generate_report(db, ws)
        await db.commit()
        return str(report.id)


@cron("finance.daily_backup", hour={3}, minute={15})
async def daily_backup(ctx: dict[str, Any]) -> str:
    async with ctx["db"]() as db:
        b = await service.run_backup(db, BackupTrigger.SCHEDULE)
        await db.commit()
    if b.status != BackupStatus.SUCCEEDED:
        log.error("Sao lưu hằng ngày lỗi: %s", b.error)
    return str(b.status)
