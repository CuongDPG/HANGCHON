"""Việc nền của sourcing. Cron không gọi được bằng tên trong worker (arq chỉ nhận job thường), nên mỗi cron gọi lại
cùng hàm với job chạy tay."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.jobs import cron, job
from app.modules.sourcing import service
from app.modules.sourcing.models import RunKind

log = logging.getLogger("app.sourcing.jobs")


@job("sourcing.scan_brief")
async def scan_brief(ctx: dict[str, Any], run_id: str) -> str:
    async with ctx["db"]() as db:
        run = await service.execute_scan(db, uuid.UUID(run_id))
        await db.commit()
        await service.after_save(db, run)
        return run.status.value


@job("sourcing.import_link")
async def import_link(ctx: dict[str, Any], run_id: str) -> str:
    async with ctx["db"]() as db:
        run = await service.execute_import(db, uuid.UUID(run_id))
        await db.commit()
        await service.after_save(db, run)
        return run.status.value


@job("sourcing.image_search")
async def image_search(ctx: dict[str, Any], run_id: str) -> str:
    async with ctx["db"]() as db:
        run = await service.execute_image_search(db, uuid.UUID(run_id))
        await db.commit()
        await service.after_save(db, run)
        return run.status.value


@job("sourcing.fetch_details")
async def fetch_details(ctx: dict[str, Any], candidate_id: str) -> str | None:
    """«Lấy ảnh và chi tiết» một ứng viên (chị bấm, hoặc tự lấy cho món điểm cao sau lượt quét)."""
    async with ctx["db"]() as db:
        c = await service.execute_fetch_details(db, uuid.UUID(candidate_id))
        await db.commit()
        return (service.detail_state(c) or {}).get("status")


@job("sourcing.trend_radar")
async def trend_radar(ctx: dict[str, Any], run_id: str) -> str:
    async with ctx["db"]() as db:
        run = await service.execute_trends(db, uuid.UUID(run_id))
        await db.commit()
        return run.status.value


@job("sourcing.demand_digest")
async def demand_digest(ctx: dict[str, Any], run_id: str) -> str:
    async with ctx["db"]() as db:
        run = await service.execute_demand_digest(db, uuid.UUID(run_id))
        await db.commit()
        return run.status.value


@cron("sourcing.trend_radar_daily", hour={7}, minute={0})
async def trend_radar_daily(ctx: dict[str, Any]) -> None:
    """a5: mỗi sáng 7:00 giờ Việt Nam."""
    async with ctx["db"]() as db:
        run = await service.start_run(db, RunKind.TREND_RADAR)
        await db.commit()
        await service.execute_trends(db, run.id)
        await db.commit()


@cron("sourcing.scheduled_scans", hour={6}, minute={30})
async def scheduled_scans(ctx: dict[str, Any]) -> None:
    """a7: mỗi sáng chạy các đề đã lưu đến hạn (mặc định 7 ngày một lần)."""
    async with ctx["db"]() as db:
        runs = await service.run_due_scheduled(db)
        await db.commit()
        log.info("Săn theo lịch: %d đề", len(runs))


@cron("sourcing.demand_sweep", hour={22}, minute={0})
async def demand_sweep(ctx: dict[str, Any]) -> None:
    """a6: lưới an toàn mỗi tối — rà lời khách chưa được ghi nhận."""
    async with ctx["db"]() as db:
        run = await service.start_run(db, RunKind.DEMAND_DIGEST)
        await db.commit()
        await service.execute_demand_digest(db, run.id)
        await db.commit()
