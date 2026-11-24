"""Việc nền của control."""

from __future__ import annotations

from typing import Any

from sqlalchemy import update

from app.core.jobs import cron
from app.core.timeutil import now_utc
from app.modules.control.models import ApprovalItem, ApprovalStatus


@cron("control.expire_approvals", minute={5})
async def expire_approvals(ctx: dict[str, Any]) -> int:
    """Mỗi giờ: việc chờ duyệt quá `expires_at` → expired (vd đề xuất giá đã cũ, đợt đã đóng)."""
    async with ctx["db"]() as db:
        res = await db.execute(
            update(ApprovalItem)
            .where(
                ApprovalItem.status == ApprovalStatus.PENDING,
                ApprovalItem.expires_at.is_not(None),
                ApprovalItem.expires_at < now_utc(),
            )
            .values(status=ApprovalStatus.EXPIRED, decided_at=now_utc())
        )
        await db.commit()
        return res.rowcount or 0
