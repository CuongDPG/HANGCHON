"""Dữ liệu mẫu khu Khách + hộp thư: chạy được trên CSDL trống, chạy lại không sinh trùng."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modules.control.models import AutonomySetting
from app.modules.crm import models as crm
from app.modules.crm.seed import seed_demo as crm_demo
from app.modules.inbox.models import Message, Thread, ThreadStatus
from app.modules.inbox.seed import seed_demo as inbox_demo
from app.seed import seed as base_seed


async def _count(db, model, *where):
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_demo_seed_is_idempotent():
    for _ in range(2):
        async with SessionLocal() as db:
            await base_seed(db)
            await crm_demo(db)
            await inbox_demo(db)
            await db.commit()
    async with SessionLocal() as db:
        assert await _count(db, Thread) == 9
        assert await _count(db, Message, Message.direction == "inbound") == 9
        assert await _count(db, Thread, Thread.status == ThreadStatus.AI_HANDLED) == 4
        assert await _count(db, Thread, Thread.needs_owner.is_(True)) >= 2
        assert await _count(db, crm.Broadcast) == 1
        assert await _count(db, crm.ReferralUse) == 1
        assert await _count(db, crm.ReorderReminder) >= 3
        assert await _count(db, crm.TesterInvite) == 2
        assert await db.get(AutonomySetting, "inbox.reply_faq") is None  # mức tự chủ của chị không bị đổi
