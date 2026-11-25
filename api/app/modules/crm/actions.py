"""Khai báo của crm với control: hành động AI (sổ khách, tin báo đợt, nhắc mua lại), cài đặt, số liệu «Hôm nay»."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.timeutil import local_today
from app.modules.crm import service
from app.modules.crm.models import CustomerNote, NoteKind, NoteSource, ReminderStatus, ReorderReminder
from app.modules.crm.service import (
    ACTION_BROADCAST,
    ACTION_PROFILE,
    ACTION_REFERRAL_REWARD,
    ACTION_REORDER,
    REFERRAL_REWARD_KEY,
    REGULAR_MIN_KEY,
    REORDER_CYCLES_KEY,
)

GROUP = "Khách"

control.register_action(
    ACTION_PROFILE,
    "Cập nhật tóm tắt sổ khách",
    GROUP,
    default="auto",
    description="Sau mỗi hội thoại hay đơn mới, AI ghi lại khách đã mua gì, hỏi gì, quan tâm gì. Chỉ chị xem.",
)
control.register_action(
    ACTION_BROADCAST,
    "Gửi tin báo đợt mới cho khách quen",
    GROUP,
    default="ask",
    customer_facing=True,
    description="Khi mở đợt, AI soạn tin cho nhóm khách quen. Chị xem rồi gửi.",
)
control.register_action(
    ACTION_REORDER,
    "Nhắn nhắc mua lại món tiêu hao",
    GROUP,
    default="ask",
    customer_facing=True,
    description="Món tiêu hao sắp hết thì AI soạn tin nhắc riêng từng khách. Không nhắc quá một lần mỗi chu kỳ.",
)

control.register_setting(REGULAR_MIN_KEY, "Khách quen: số đơn tối thiểu", 2, group="Khách")
control.register_setting(
    REORDER_CYCLES_KEY, "Chu kỳ dùng của món tiêu hao (nhắc mua lại)", {}, group="Khách",
    description='{"<product_id>": {"days": 60, "active": true}} — đặt trên màn hình Nhắc mua lại.',
)  # fmt: skip
control.register_setting(REFERRAL_REWARD_KEY, "Quà giới thiệu bạn cho mỗi bên (VND)", 30_000, group="Khách")
control.register_action(
    ACTION_REFERRAL_REWARD,
    "Tặng quà giới thiệu bạn cho người giới thiệu",
    GROUP,
    default="auto",
    description="Đơn đầu của bạn được giới thiệu đã trả tiền và đã giao: AI tặng người giới thiệu phần giảm cho đơn "
    "kế tiếp (tự trừ khi đặt). Không nhắn gì cho khách. Hoàn tác được khi phần quà chưa dùng.",
)


@control.handler(ACTION_REFERRAL_REWARD)
async def _reward(ctx: control.ActionContext) -> control.HandlerResult:
    return await service.grant_reward(ctx.db, uuid.UUID(str(ctx.payload["referral_use_id"])))


@control.undoer(ACTION_REFERRAL_REWARD)
async def _unreward(ctx: control.UndoContext) -> None:
    await service.revoke_reward(ctx.db, uuid.UUID(str(ctx.undo["referral_use_id"])))


@control.handler(ACTION_PROFILE)
async def _profile(ctx: control.ActionContext) -> control.HandlerResult:
    cid = uuid.UUID(str(ctx.payload["customer_id"]))
    undo = await service.apply_profile(ctx.db, cid, str(ctx.payload["summary"]), list(ctx.payload.get("interests", [])))
    return control.HandlerResult(
        result={"customer_id": str(cid)}, undo={"customer_id": str(cid), **undo},
        summary=str(ctx.payload["summary"])[:200], ref_type="customers", ref_id=cid,
    )  # fmt: skip


@control.undoer(ACTION_PROFILE)
async def _profile_undo(ctx: control.UndoContext) -> None:
    cid = uuid.UUID(str(ctx.undo["customer_id"]))
    if ctx.undo.get("summary") is None:
        for n in (
            await ctx.db.execute(
                select(CustomerNote).where(
                    CustomerNote.customer_id == cid,
                    CustomerNote.source == NoteSource.AI,
                    CustomerNote.kind.in_([NoteKind.AI_SUMMARY, NoteKind.INTEREST]),
                )
            )
        ).scalars():
            await ctx.db.delete(n)
        return
    await service.apply_profile(ctx.db, cid, ctx.undo["summary"], ctx.undo.get("interests", []))


@control.handler(ACTION_BROADCAST)
async def _broadcast(ctx: control.ActionContext) -> control.HandlerResult:
    b = await service.send_broadcast(ctx.db, uuid.UUID(str(ctx.payload["broadcast_id"])), ctx.payload.get("body"))
    return control.HandlerResult(
        result={"broadcast_id": str(b.id), "delivered": b.delivered_count, "recipients": b.recipient_count},
        summary=f"Đã gửi «{b.title}» tới {b.delivered_count}/{b.recipient_count} khách quen",
        ref_type="broadcasts", ref_id=b.id,
    )  # fmt: skip


@control.handler(ACTION_REORDER)
async def _reorder(ctx: control.ActionContext) -> control.HandlerResult:
    r = await service.send_reminder(ctx.db, uuid.UUID(str(ctx.payload["reminder_id"])), ctx.payload.get("body"))
    return control.HandlerResult(
        result={"reminder_id": str(r.id)}, summary=f"Đã nhắc mua lại: «{(r.message_body or '')[:80]}»",
        ref_type="reorder_reminders", ref_id=r.id,
    )  # fmt: skip


@control.stat_provider("crm.reorder", order=40)
async def _stats(db: AsyncSession) -> list[control.Stat]:
    due = (
        await db.execute(
            select(func.count()).where(
                ReorderReminder.status == ReminderStatus.SCHEDULED, ReorderReminder.due_on <= local_today()
            )
        )
    ).scalar_one()
    return [control.Stat(key="crm.reorder_due", label="Khách sắp hết đồ", value=due, href="/desk/khach/nhac-mua-lai",
                         order=30)]  # fmt: skip
