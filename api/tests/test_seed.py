from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.db import SessionLocal
from app.seed import seed


async def test_seed_is_idempotent_and_owner_can_login(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "owner_email", "seed@test.local")
    monkeypatch.setattr(settings, "owner_password", "seed-pass-123")
    async with SessionLocal() as db:
        first = await seed(db)
        await db.commit()
    async with SessionLocal() as db:
        second = await seed(db)
        await db.commit()
    assert first["owner"] == 1 and first["categories"] == 5 and first["scoring_profiles"] == 1
    assert all(v == 0 for v in second.values())
    r = await client.post("/api/desk/auth/login", json={"email": "seed@test.local", "password": "seed-pass-123"})
    assert r.status_code == 200 and r.json()["role"] == "owner"


async def test_demo_story_covers_every_module_and_is_idempotent(owner, monkeypatch) -> None:
    """`python -m app.seed --demo`: một câu chuyện chung cho mọi module, chạy lại không sinh trùng."""
    from sqlalchemy import func, select

    from app.demo import seed_demo
    from app.modules.assessment.models import ScoringProfile
    from app.modules.catalog.models import Drop, Product, Review
    from app.modules.content.models import ScheduledPost
    from app.modules.control.models import AIActivity, ApprovalItem
    from app.modules.finance.models import LedgerEntry, WeeklyReport
    from app.modules.inbox.models import Thread
    from app.modules.orders.models import Order
    from app.modules.sourcing.models import Candidate
    from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD

    monkeypatch.setattr(settings, "owner_email", OWNER_EMAIL)
    monkeypatch.setattr(settings, "owner_password", OWNER_PASSWORD)
    async with SessionLocal() as db:
        await seed(db)
        await db.commit()
    counts = await seed_demo()
    assert counts["products"] == 7 and counts["candidates"] >= 25 and counts["drops"] == 3
    assert await seed_demo() == {}  # đã dựng rồi thì bỏ qua
    async with SessionLocal() as s:
        prof = (await s.execute(select(ScoringProfile).where(ScoringProfile.is_default.is_(True)))).scalar_one()
        assert [c["weight"] for c in prof.criteria] == [25, 20, 15, 15, 10, 10, 5]
        stages = set((await s.execute(select(Candidate.stage))).scalars())
        assert {st.value for st in stages} == {"candidate", "sample", "trial", "selected", "rejected"}
        assert await s.scalar(select(func.count(Product.id)).where(Product.status == "published")) == 7
        drops = {d.code: d.status.value for d in (await s.execute(select(Drop))).scalars()}
        assert set(drops.values()) >= {"open", "scheduled"} and drops["D1"] in ("fulfilling", "completed")
        statuses = {o.status.value for o in (await s.execute(select(Order))).scalars()}
        assert statuses >= {"draft", "pending_payment", "awaiting_stock", "ready_to_ship", "shipping", "completed",
                            "cancelled"}  # fmt: skip
        assert await s.scalar(select(func.count(Review.id)).where(Review.status == "published")) >= 2
        assert await s.scalar(select(func.count(ScheduledPost.id)).where(ScheduledPost.status == "published")) >= 3
        assert {t.status.value for t in (await s.execute(select(Thread))).scalars()} >= {"needs_owner", "ai_handled"}
        modules = set((await s.execute(select(ApprovalItem.module).where(ApprovalItem.status == "pending"))).scalars())
        assert len(modules) >= 5
        assert await s.scalar(select(func.count(AIActivity.id))) > 20
        assert await s.scalar(select(func.count(LedgerEntry.id)).where(LedgerEntry.kind == "revenue")) >= 8
        assert await s.scalar(select(func.count(WeeklyReport.id))) >= 3
        from app.modules.control.models import AppSetting, User
        from app.modules.selection.models import TasteProfile

        assert (await s.get(AppSetting, "store.picker_name")).value == "Thu (tên ví dụ)"
        assert await s.scalar(select(func.count(User.id)).where(User.role == "helper")) == 1
        assert max((await s.execute(select(TasteProfile.sample_count))).scalars()) >= 10
