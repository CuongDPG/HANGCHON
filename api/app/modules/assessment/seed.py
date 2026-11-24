"""Dữ liệu mẫu cho Thẩm định: khung chấm mặc định theo bản thiết kế + hồ sơ cho vài ứng viên đứng đầu mỗi đề.

`await seed_demo(db)` chạy lại không sinh trùng. Ép AI giả + nguồn giả trong lúc seed (xem sourcing.seed.demo_mode)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment import service
from app.modules.assessment.models import Assessment
from app.modules.sourcing.models import Candidate, SourcingBrief

TOP_PER_BRIEF = 3


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    from app.modules.sourcing.seed import demo_mode

    n = 0
    with demo_mode():
        await service.ensure_seeded_profile(db)
        await db.commit()
        briefs = (await db.execute(select(SourcingBrief.id))).scalars().all()
        for bid in briefs:
            top = (
                (
                    await db.execute(
                        select(Candidate)
                        .where(Candidate.brief_id == bid)
                        .order_by(Candidate.ai_score.desc().nulls_last())
                        .limit(TOP_PER_BRIEF)
                    )
                )
                .scalars()
                .all()
            )
            done = await db.scalar(
                select(func.count()).select_from(Assessment).join(Candidate).where(Candidate.brief_id == bid)
            )
            if done:  # đề đã có hồ sơ mẫu → không thêm (điểm thay đổi sau thẩm định làm «top» đổi chỗ)
                continue
            for c in top:
                await service.request_run(db, c, None)
                await db.commit()
                await service.execute(db, c.id)
                n += 1
    return {"assessments": n}
