"""Dữ liệu mẫu chạy được và chạy lại không sinh trùng."""

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.content.models import ContentDraft, ContentInsight, PostMetric, PostStatus, ScheduledPost
from app.modules.content.seed import seed_demo


async def test_seed_demo_idempotent(owner):
    async with SessionLocal() as db:
        first = await seed_demo(db)
        await db.commit()
    assert first["products"] == 3 and first["published"] >= 4 and first["livestreams"] == 1
    async with SessionLocal() as db:
        drafts = await db.scalar(select(func.count(ContentDraft.id)))
        again = await seed_demo(db)
        await db.commit()
        assert again["products"] == 0
        assert await db.scalar(select(func.count(ContentDraft.id))) == drafts
        assert await db.scalar(select(func.count(ContentInsight.id))) == 1
        assert await db.scalar(select(func.count(PostMetric.id))) >= 4
        published = await db.scalar(
            select(func.count(ScheduledPost.id)).where(ScheduledPost.status == PostStatus.PUBLISHED)
        )
        assert published >= 4
