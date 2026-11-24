"""Dữ liệu mẫu cho Săn hàng: `await seed_demo(db)` (chạy lại không sinh trùng).

Chạy đúng đường đi thật (hiểu đề → quét → xếp hạng → lưu qua control) nhưng **ép** AI giả và nguồn hàng giả trong lúc
seed, để máy có khoá AI thật cũng không tốn tiền. Tên món, lời khách đều là ví dụ."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timeutil import now_utc
from app.modules.sourcing import service
from app.modules.sourcing.models import DemandSource, RunKind, SourcingBrief, TrendSignal

DEMO_BRIEFS = [
    # (lời chị, chạy quét?, lưu lịch hằng tuần?)
    (
        "Tìm giá phơi đồ gấp gọn cho ban công nhỏ, inox không gỉ, dưới 300k, ưu tiên hàng Nhật hoặc xưởng "
        "Trung Quốc có đánh giá tốt",
        True,
        True,
    ),
    ("Săn bình giữ nhiệt giữ nóng lâu, hàng Nhật hoặc xưởng Trung Quốc, dưới 400k, đánh giá từ 4,5 sao", True, False),
    ("Tìm hộp cơm inox hai tầng cho dân văn phòng, dưới 200k", False, False),
]

DEMO_DEMAND = [
    "Shop có bán giá phơi gấp gọn không ạ, nhà em ban công bé lắm",
    "Chị ơi có loại giá phơi gấp gọn inox không, em cần gấp",
    "Có giá phơi gấp gọn loại treo lan can không shop",
    "Chị tìm giúp em hộp đựng gia vị có nắp kín nhé",
    "Có bình giữ nhiệt cho bé đi học không ạ",
    "Shop có bán bình giữ nhiệt nhỏ không, loại 350ml",
    "Nhờ chị tìm thảm chùi chân phòng tắm khô nhanh",
]
_NS = uuid.UUID("6f7c1c1e-0000-4000-8000-00000000a6a6")


@contextmanager
def demo_mode() -> Iterator[None]:
    """Ép AI giả + nguồn hàng giả trong lúc seed (khôi phục sau)."""
    saved = (settings.ai_provider, settings.sources_driver)
    settings.ai_provider, settings.sources_driver = "fake", "mock"
    try:
        yield
    finally:
        settings.ai_provider, settings.sources_driver = saved


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    counts = {"briefs": 0, "runs": 0, "demand": 0}
    with demo_mode():
        for text, scan, scheduled in DEMO_BRIEFS:
            if await db.scalar(select(SourcingBrief.id).where(SourcingBrief.raw_text == text)):
                continue
            brief = await service.create_brief(db, text)
            counts["briefs"] += 1
            await db.commit()
            if scan:
                run = await service.start_scan(db, brief)
                await db.commit()
                await service.execute_scan(db, run.id)
                counts["runs"] += 1
                brief = await service.get_brief(db, brief.id)
                if scheduled:
                    brief.is_scheduled = True
                    brief.schedule_interval_days = 7
                    brief.alert_min_score = 80
                    brief.next_run_at = now_utc() + timedelta(days=7)
                await db.commit()
        if not await db.scalar(select(TrendSignal.id).limit(1)):
            run = await service.start_run(db, RunKind.TREND_RADAR)
            await db.commit()
            await service.execute_trends(db, run.id)
            counts["runs"] += 1
        for i, text in enumerate(DEMO_DEMAND):
            out = await service.record_demand(
                db, text, source=DemandSource.MANUAL, source_type="seed", source_id=uuid.uuid5(_NS, str(i))
            )
            counts["demand"] += 1 if out else 0
        await db.commit()
        from app.modules.assessment.seed import seed_demo as seed_assessment

        await seed_assessment(db)
    return counts
