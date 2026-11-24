"""Khai báo của hộp thư với control: hành động trả lời khách (h2), chuyển chị (h3), cài đặt, số liệu «Hôm nay»."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.enums import Actor
from app.core.errors import NotFound
from app.modules.inbox import service
from app.modules.inbox.context import SHIPPING_POLICY_KEY
from app.modules.inbox.models import ReplyDraft, Thread, ThreadStatus
from app.modules.inbox.service import (
    ACK_TEXT_KEY,
    ACTION_ACK,
    ACTION_ESCALATE,
    ACTION_FAQ,
    ACTION_GENERAL,
    DEFAULT_ACK_TEXT,
)

GROUP = "Khách"

control.register_action(
    ACTION_FAQ,
    "Trả lời câu thường gặp (giá, còn hàng, phí giao, hàng về)",
    GROUP,
    default="ask",
    customer_facing=True,
    description="AI trả lời từ dữ liệu sản phẩm, đợt và chính sách phí giao. Đặt «AI tự làm» thì gửi ngay và ghi nhật ký.",
)
control.register_action(
    ACTION_GENERAL,
    "Trả lời tin khác (AI soạn nháp)",
    GROUP,
    locked=True,
    customer_facing=True,
    description="Câu về cách dùng, muốn mua, hỏi đơn... AI soạn nháp, chị sửa rồi gửi.",
)
control.register_action(
    ACTION_ESCALATE,
    "Việc khó chuyển cho chị (khiếu nại, hàng lỗi, sức khoẻ)",
    GROUP,
    locked=True,
    customer_facing=True,
    description="AI không tự trả lời: tóm tắt và gợi ý 1–2 phương án, chị chọn và gửi.",
)
control.register_action(
    ACTION_ACK,
    "Báo khách «chị sẽ trả lời trong hôm nay»",
    GROUP,
    default="off",
    customer_facing=True,
    description="Khi chuyển việc khó cho chị, gửi khách một câu báo đã nhận tin. Mặc định tắt.",
)

control.register_setting(
    SHIPPING_POLICY_KEY,
    "Chính sách phí giao (AI dùng để trả lời khách)",
    None,
    group="Khách",
    description="Ví dụ: «Phí giao 25.000–35.000đ tuỳ tỉnh, đơn từ 500.000đ miễn phí». Bỏ trống thì AI chuyển câu hỏi cho chị.",
)
control.register_setting(ACK_TEXT_KEY, "Câu báo khách khi chuyển việc cho chị", DEFAULT_ACK_TEXT, group="Khách")


async def _draft(ctx: control.ActionContext) -> ReplyDraft:
    draft = await ctx.db.get(ReplyDraft, uuid.UUID(str(ctx.payload["draft_id"])))
    if draft is None:
        raise NotFound("Không tìm thấy bản nháp.")
    return draft


async def _send(ctx: control.ActionContext) -> control.HandlerResult:
    draft = await _draft(ctx)
    msg = await service.send_draft(
        ctx.db, draft, ctx.payload.get("body"), mode=ctx.mode, user=ctx.user, private=bool(ctx.payload.get("private"))
    )
    thread = await ctx.db.get(Thread, draft.thread_id)
    who = thread.participant_name if thread else "khách"
    if msg is None:
        return control.HandlerResult(
            result={"thread_id": str(draft.thread_id)}, summary=f"Đã xử lý việc của {who}",
            ref_type="threads", ref_id=draft.thread_id,
        )  # fmt: skip
    return control.HandlerResult(
        result={"message_id": str(msg.id), "thread_id": str(draft.thread_id)},
        summary=f"Đã trả lời {who}: «{msg.body[:80]}»",
        ref_type="threads",
        ref_id=draft.thread_id,
    )


for _action in (ACTION_FAQ, ACTION_GENERAL, ACTION_ESCALATE):
    control.handler(_action)(_send)


async def _redo(ctx: control.ReturnContext) -> None:
    """Chị trả lại bản nháp kèm lời dặn → AI soạn lại theo lời dặn."""
    draft = await ctx.db.get(ReplyDraft, uuid.UUID(str(ctx.item.payload["draft_id"])))
    if draft is None or draft.reply_to_message_id is None:
        return
    await service.triage(ctx.db, draft.reply_to_message_id, owner_note=ctx.note)


for _action in (ACTION_FAQ, ACTION_GENERAL):
    control.on_returned(_action)(_redo)


@control.handler(ACTION_ACK)
async def _ack(ctx: control.ActionContext) -> control.HandlerResult:
    thread = await service.get_thread(ctx.db, uuid.UUID(str(ctx.payload["thread_id"])))
    human = ctx.mode == "approved"
    msg = await service.deliver(
        ctx.db, thread, str(ctx.payload["body"]), sender=Actor.OWNER if human else Actor.AI, ai_generated=False,
        human=human,
    )  # fmt: skip
    return control.HandlerResult(
        result={"message_id": str(msg.id)}, summary=f"Đã báo {thread.participant_name}: chị sẽ trả lời trong hôm nay",
        ref_type="threads", ref_id=thread.id,
    )  # fmt: skip


@control.stat_provider("inbox.waiting", order=20)
async def _stats(db: AsyncSession) -> list[control.Stat]:
    waiting = (await db.execute(select(func.count()).where(Thread.status == ThreadStatus.NEEDS_OWNER))).scalar_one()
    return [control.Stat(key="inbox.waiting", label="Tin chờ chị", value=waiting, href="/desk/khach", order=5)]
