"""Việc nền của catalog: AI viết trang sản phẩm, tự mở/đóng đợt theo giờ."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from arq import Retry
from sqlalchemy import select

from app import ai
from app.core.jobs import cron, job
from app.core.timeutil import now_utc
from app.modules.catalog import drops as drop_svc
from app.modules.catalog import products as product_svc
from app.modules.catalog.models import Product, ProductStatus

log = logging.getLogger("app.catalog")


# Việc được xếp lúc chị bấm «Đã chọn», nhưng yêu cầu đó còn chạy AI (viết lý do chọn) rồi mới commit — có khi
# hơn 10 giây. Chưa thấy sản phẩm thì hẹn chạy lại (arq Retry) thay vì lặng lẽ bỏ qua tới lượt cron.
NOT_FOUND_RETRIES = 5  # = max_tries mặc định của worker arq
NOT_FOUND_DELAY_SECONDS = 10


@job("catalog.write_product_page")
async def write_product_page(ctx: dict[str, Any], product_id: str, note: str | None = None) -> str | None:
    async with ctx["db"]() as db:
        p = await db.get(Product, uuid.UUID(product_id))
        if p is None:
            tries = int(ctx.get("job_try") or 0)  # chỉ có khi chạy trong worker arq
            if tries and tries < NOT_FOUND_RETRIES:
                log.info("Chưa thấy sản phẩm %s (giao dịch chưa commit?), thử lại lần %d", product_id, tries + 1)
                raise Retry(defer=NOT_FOUND_DELAY_SECONDS * tries)
            log.warning("Không thấy sản phẩm %s để AI viết trang (đã thử %d lần)", product_id, tries or 1)
            return None
        if p.status not in (ProductStatus.DRAFT, ProductStatus.PENDING_REVIEW):
            return None
        try:
            out = await product_svc.write_page(db, p, note=note)
        except ai.AIError as e:  # không lặp lại vô hạn; cron sẽ thử lại sau
            log.warning("AI chưa viết được trang %s: %s", product_id, e)
            await db.rollback()
            return None
        await db.commit()
        return out.status


@cron("catalog.write_missing_pages", minute={7, 22, 37, 52})
async def write_missing_pages(ctx: dict[str, Any]) -> int:
    """Lưới an toàn: sản phẩm nháp chưa được AI viết (việc nền bị lỡ) thì viết bù."""
    async with ctx["db"]() as db:
        ids = list(
            (
                await db.execute(
                    select(Product.id).where(
                        Product.status == ProductStatus.DRAFT,
                        Product.ai_generated.is_(False),
                        Product.candidate_id.is_not(None),
                        Product.created_at < now_utc() - timedelta(minutes=2),
                    )
                )
            ).scalars()
        )
    done = 0
    for pid in ids[:20]:
        if await write_product_page({**ctx, "job_try": None}, str(pid)):  # cron: không Retry cả lượt
            done += 1
    return done


@cron("catalog.drop_tick", minute=set(range(0, 60, 5)))
async def drop_tick(ctx: dict[str, Any]) -> dict[str, int]:
    """Mở đợt đã tới giờ, đóng đợt hết hạn / hết suất (phát drop.opened / drop.closed)."""
    async with ctx["db"]() as db:
        out = await drop_svc.tick(db)
        await db.commit()
    return out
