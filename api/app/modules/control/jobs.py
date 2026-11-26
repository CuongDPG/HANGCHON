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


async def record_ai_cost(db: Any, key: str) -> int:
    """k1/k2: tiền AI của một tháng (giờ VN) → `expense.recorded` (finance tự ghi chi phí, khoá theo tháng nên chạy
    lặp lại không sinh trùng). Trả số tiền đã báo."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.core import events
    from app.core.timeutil import local_month_bounds_utc, to_local
    from app.modules.control.models import AIRun

    start, end = local_month_bounds_utc(key)
    total = int(
        await db.scalar(
            select(func.coalesce(func.sum(AIRun.cost_vnd), 0)).where(AIRun.created_at >= start, AIRun.created_at < end)
        )
        or 0
    )
    if total <= 0:
        return 0
    await events.emit(
        "expense.recorded",
        {
            "expense_id": None,
            "source": "control",
            "source_key": f"ai-cost:{key}",
            "amount_vnd": total,
            "category": "ai",
            "incurred_on": to_local(end - timedelta(seconds=1)).date().isoformat(),
            "description": f"Chi phí AI tháng {key[5:]}/{key[:4]}",
            "vendor": "Anthropic",
        },
        db=db,
    )
    return total


@cron("control.ai_cost_expense", day={1}, hour={2}, minute={30})
async def ai_cost_expense(ctx: dict[str, Any]) -> int:
    """Ngày 1 hằng tháng: ghi tiền AI tháng trước vào sổ chi phí."""
    from datetime import timedelta

    from app.core.timeutil import local_month_bounds_utc, month_key

    start, _ = local_month_bounds_utc(month_key())
    async with ctx["db"]() as db:
        total = await record_ai_cost(db, month_key(start - timedelta(days=1)))
        await db.commit()
        return total


@cron("control.refresh_channel_tokens", hour={4}, minute={20})
async def refresh_channel_tokens(ctx: dict[str, Any]) -> dict[str, str]:
    """Hằng ngày 4:20: làm mới token các kênh đã «Kết nối» (TikTok, Shopee, TikTok Shop) và mã Threads cũ hơn 7 ngày,
    để token không chết khi lâu không đăng (refresh token Shopee chỉ sống 30 ngày)."""
    from app.integrations.channel_oauth import refresh_due_tokens

    return await refresh_due_tokens()
