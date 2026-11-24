"""Khai báo của chính module control: hành động k2, số liệu «Hôm nay», lệnh bằng lời, cài đặt chung."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai
from app.core.db import SessionLocal
from app.core.money import format_vnd
from app.core.timeutil import local_day_bounds_utc
from app.modules.control import service
from app.modules.control.models import AIActivity, ApprovalItem, ApprovalStatus, AutonomyLevel
from app.modules.control.registry import (
    ACTIONS,
    ActionContext,
    CommandContext,
    CommandResult,
    HandlerResult,
    Stat,
    handler,
    intent,
    register_action,
    register_setting,
    stat_provider,
)

# ---- k2: chạm trần chi phí AI ------------------------------------------------------------------------------------

register_action(
    "control.raise_ai_budget",
    "Nâng trần chi phí AI tháng này",
    "Hệ thống",
    locked=True,
    description="AI đã dừng vì chạm trần. Duyệt để nâng trần và cho AI chạy tiếp; trả lại để giữ nguyên.",
)


@handler("control.raise_ai_budget")
async def _raise_budget(ctx: ActionContext) -> HandlerResult:
    new = int(ctx.payload["new_budget_vnd"])
    old = await ai.monthly_budget_vnd()
    await service.set_budget(ctx.db, new, ctx.user)
    return HandlerResult(result={"budget_vnd": new}, summary=f"Trần chi phí AI: {format_vnd(old)} → {format_vnd(new)}")


@ai.on_budget_exceeded
async def _on_budget_exceeded(month: str, spent: int, budget: int) -> None:
    suggested = max(budget + 500_000, int(budget * 1.5))
    async with SessionLocal() as db:
        returned = (
            await db.execute(
                select(func.count()).where(
                    ApprovalItem.action == "control.raise_ai_budget",
                    ApprovalItem.dedupe_key == f"ai-budget-{month}",
                    ApprovalItem.status == ApprovalStatus.RETURNED,
                )
            )
        ).scalar_one()
        if returned:  # chị đã quyết giữ nguyên trần tháng này → không hỏi lại
            return
        await service.propose(
            "control.raise_ai_budget",
            f"AI đã chạm trần chi phí tháng {month}",
            {"month": month, "new_budget_vnd": suggested},
            {"spent_vnd": spent, "budget_vnd": budget, "suggested_vnd": suggested},
            db=db,
            summary=f"Đã dùng {format_vnd(spent)} / trần {format_vnd(budget)}. Đề xuất nâng lên {format_vnd(suggested)}.",
            dedupe_key=f"ai-budget-{month}",
            priority=10,
            ai_generated=False,
        )
        await db.commit()


# ---- cài đặt chung -----------------------------------------------------------------------------------------------

register_setting("ai.monthly_budget_vnd", "Trần chi phí AI mỗi tháng (VND)", None, group="AI",
                 description="Bỏ trống = dùng AI_MONTHLY_BUDGET_VND. 0 = không giới hạn.")  # fmt: skip
register_setting("store.name", "Tên cửa hàng", "Hàng Chọn", group="Cửa hàng")
register_setting("store.tagline", "Câu giới thiệu", "Đồ gia dụng nhỏ, chọn từng món", group="Cửa hàng")


# ---- số liệu «Hôm nay» -------------------------------------------------------------------------------------------


@stat_provider("control.overview", order=90)
async def _control_stats(db: AsyncSession) -> list[Stat]:
    start, end = local_day_bounds_utc()
    pending = (await db.execute(select(func.count()).where(ApprovalItem.status == ApprovalStatus.PENDING))).scalar_one()
    done = (
        await db.execute(select(func.count()).where(AIActivity.created_at >= start, AIActivity.created_at < end))
    ).scalar_one()
    return [
        Stat(key="control.pending", label="Việc chờ chị", value=pending, order=1),
        Stat(key="control.ai_done_today", label="Việc AI đã làm hôm nay", value=done, order=2),
    ]


# ---- lệnh bằng lời -----------------------------------------------------------------------------------------------


@intent(
    "control.pending_summary",
    "Xem việc đang chờ duyệt",
    "Cho chị biết có bao nhiêu việc đang chờ duyệt và mấy việc đầu tiên.",
    examples=["có việc gì chờ chị duyệt không", "xem hàng chờ duyệt", "việc đang chờ"],
)
async def _pending_summary(ctx: CommandContext, _: None) -> CommandResult:
    rows = list(
        (
            await ctx.db.execute(
                select(ApprovalItem)
                .where(ApprovalItem.status == ApprovalStatus.PENDING)
                .order_by(ApprovalItem.priority.desc(), ApprovalItem.created_at)
                .limit(5)
            )
        ).scalars()
    )
    total = (
        await ctx.db.execute(select(func.count()).where(ApprovalItem.status == ApprovalStatus.PENDING))
    ).scalar_one()
    if not total:
        return CommandResult(message="Không có việc nào đang chờ chị duyệt.", data={"total": 0})
    titles = "; ".join(r.title for r in rows)
    return CommandResult(
        message=f"Có {total} việc đang chờ chị: {titles}.", data={"total": total, "ids": [str(r.id) for r in rows]}
    )


class SetAutonomyParams(BaseModel):
    action: str = Field(description="Khoá hành động trong bảng mức tự chủ, vd content.publish_post")
    level: Literal["auto", "ask", "off"]


@intent(
    "control.set_autonomy",
    "Đổi mức tự chủ của AI cho một việc",
    "Chị cho AI tự làm (auto), phải hỏi (ask) hoặc tắt (off) một việc. Chỉ dùng khoá hành động có trong bảng.",
    params=SetAutonomyParams,
    examples=["cho AI tự đăng bài", "từ giờ trả lời tin nhắn phải hỏi chị", "tắt việc nhắc mua lại"],
)
async def _set_autonomy(ctx: CommandContext, params: SetAutonomyParams) -> CommandResult:
    spec = ACTIONS.get(params.action)
    if spec is None:
        return CommandResult(message="Em không thấy việc đó trong bảng mức tự chủ.")
    level = await service.set_level(ctx.db, params.action, AutonomyLevel(params.level), ctx.user)
    words = {"auto": "AI tự làm", "ask": "hỏi chị trước", "off": "tắt"}
    return CommandResult(
        message=f"Đã đặt «{spec.label}»: {words[level.value]}.", data={"action": spec.key, "level": level.value}
    )
