"""Khai báo của crm với control: hành động AI (sổ khách, tin báo đợt, nhắc mua lại), cài đặt, số liệu «Hôm nay»."""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.money import format_vnd
from app.core.timeutil import VN_TZ, local_today
from app.modules.crm import cotrial, service
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


control.register_action(
    cotrial.ACTION_REFUND,
    "Hoàn tiền cho người dùng thử cùng",
    GROUP,
    locked=True,
    customer_facing=True,
    description="Người dùng thử gửi cảm nhận đủ trước hạn → đề xuất hoàn tiền theo lời mời. Chị chuyển khoản tay rồi "
    "duyệt để ghi «đã hoàn» (sửa được số tiền); trả lại = chưa hoàn.",
)


@control.handler(cotrial.ACTION_REFUND)
async def _cotrial_refund(ctx: control.ActionContext) -> control.HandlerResult:
    inv = await cotrial.apply_refund(
        ctx.db, uuid.UUID(str(ctx.payload["tester_invite_id"])), int(ctx.payload["refund_vnd"])
    )
    return control.HandlerResult(
        result={"tester_invite_id": str(inv.id), "refund_vnd": inv.refund_vnd},
        summary=f"Đã hoàn {format_vnd(inv.refund_vnd)} cho người dùng thử", ref_type="tester_invites", ref_id=inv.id,
    )  # fmt: skip


@control.on_returned(cotrial.ACTION_REFUND)
async def _cotrial_refund_returned(ctx: control.ReturnContext) -> None:
    await cotrial.refund_returned(ctx.db, uuid.UUID(str(ctx.item.payload["tester_invite_id"])))


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


# ---- lệnh bằng lời (i6) ------------------------------------------------------------------------------------------


class FindCustomerParams(BaseModel):
    query: str | None = Field(default=None, description="Tên hoặc số điện thoại khách, đúng như chị nói")


@control.intent(
    "crm.find_customer",
    "Tìm khách theo tên hoặc số điện thoại",
    "Mở sổ khách của một người: đã mua mấy đơn, tổng tiền, lần mua gần nhất.",
    params=FindCustomerParams,
    examples=["tìm khách tên Lan", "khách số 0912 345 678 là ai", "mở sổ khách chị Hoa"],
)
async def _find_customer(ctx: control.CommandContext, params: FindCustomerParams | None) -> control.CommandResult:
    from app.modules.orders.models import Customer

    query = (params.query if params and params.query else None) or ctx.text
    digits = re.sub(r"\D", "", query)
    base = select(Customer).where(Customer.merged_into_id.is_(None))
    if len(digits) >= 6:  # có số điện thoại: so phần số (bỏ dấu cách, chấm)
        tail = digits[-9:]
        rows = list((await ctx.db.execute(base.where(Customer.phone.contains(tail)).limit(5))).scalars())
    else:
        pool = list(
            (await ctx.db.execute(base.where(Customer.name.is_not(None)).order_by(Customer.last_order_at.desc().nulls_last()).limit(2000))).scalars()
        )  # fmt: skip
        ids = control.match_names(query, [(c.id, c.name or "") for c in pool])
        rows = [c for c in pool if c.id in ids][:5]
    if not rows:
        return control.CommandResult(
            message="Em không thấy khách nào như vậy trong sổ. Chị nói rõ tên hoặc số điện thoại nhé.",
            status="needs_clarification",
        )
    if len(rows) > 1:
        names = "; ".join(f"{c.name or 'Chưa có tên'} ({c.phone or 'không số'})" for c in rows)
        return control.CommandResult(
            message=f"Có {len(rows)} khách gần giống: {names}. Chị muốn xem ai?",
            status="needs_clarification",
            href="/desk/khach/so-khach",
            data={"customer_ids": [str(c.id) for c in rows]},
        )
    c = rows[0]
    last = f", lần gần nhất {c.last_order_at.astimezone(VN_TZ):%d/%m/%Y}" if c.last_order_at else ""
    return control.CommandResult(
        message=f"{c.name or 'Khách'} ({c.phone or 'không số'}): {c.order_count} đơn, "
        f"tổng {format_vnd(c.total_spent_vnd)}{last}.",
        href=f"/desk/khach/so-khach/{c.id}",
        data={"customer_id": str(c.id)},
    )
