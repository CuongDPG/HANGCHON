"""Khai báo của trợ lý với control: chuyển câu hỏi chưa có căn cứ cho chị (luôn hỏi chị)."""

from __future__ import annotations

import uuid

from app import control
from app.core.enums import Channel
from app.integrations import notify as notify_api
from app.integrations.notify import OutboundNotification
from app.modules.assistant import service
from app.modules.assistant.models import AssistantConversation

control.register_action(
    "assistant.forward_to_owner",
    "Chuyển câu hỏi khách cho chị (trợ lý không có căn cứ)",
    "Website",
    locked=True,
    customer_facing=True,
    description="Trợ lý không đoán. Chị gõ câu trả lời rồi duyệt: câu trả lời hiện trong khung hỏi của khách.",
)


@control.handler("assistant.forward_to_owner")
async def _forward(ctx: control.ActionContext) -> control.HandlerResult:
    conv = await ctx.db.get(AssistantConversation, uuid.UUID(str(ctx.payload["conversation_id"])))
    if conv is None:
        raise ValueError("Cuộc trò chuyện đã bị xoá.")
    msg = await service.owner_reply(ctx.db, conv, str(ctx.payload.get("reply") or ""))
    notified = False
    if conv.contact:
        text = f"Hàng Chọn trả lời bạn: {msg.content}"
        res = await notify_api.send(
            OutboundNotification(
                channel=Channel.ZALO_OA, to=conv.contact, text=text, kind="assistant_reply",
                data={"phone": conv.contact, "noi_dung": msg.content},
            )
        )  # fmt: skip
        notified = res.status != "failed"
    return control.HandlerResult(
        result={"message_id": str(msg.id), "notified": notified},
        summary="Chị đã trả lời khách" + (" (đã nhắn cho khách)" if notified else ""),
        ref_type="assistant_conversations",
        ref_id=conv.id,
    )
