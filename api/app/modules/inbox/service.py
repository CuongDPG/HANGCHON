"""Nghiệp vụ hộp thư gộp (h1–h3).

Luồng một tin đến:  webhook / giả lập → `ingest` (lưu tin, gắn khách, phát `message.received`) → `triage`
(AI phân loại + soạn từ dữ liệu thật) → một trong ba đường:
  - câu thường gặp (giá / còn hàng / phí giao / hàng về) → `inbox.reply_faq` (mặc định hỏi chị; `auto` thì gửi ngay)
  - câu khác → `inbox.reply_general` (luôn là nháp chờ chị)
  - khiếu nại / hàng lỗi / sức khoẻ / thiếu dữ liệu → `inbox.escalate` (khoá «luôn hỏi chị»), không tự trả lời
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.enums import Actor, Channel
from app.core.errors import AppError, BadRequest, Conflict, NotFound
from app.core.pagination import PageParams, Paginated, paginate
from app.core.timeutil import now_utc
from app.integrations.social import InboundEvent
from app.modules.control.models import ApprovalItem, ApprovalStatus, User
from app.modules.inbox import context, rules
from app.modules.inbox.ai_tasks import DraftReplyIn, DraftReplyOut, EscalationOption
from app.modules.inbox.channels import messaging_driver
from app.modules.inbox.models import (
    AccountStatus,
    ChannelAccount,
    Direction,
    EscalationReason,
    Intent,
    Message,
    MessageStatus,
    ReplyDraft,
    ReplyKind,
    ReplyStatus,
    Thread,
    ThreadKind,
    ThreadStatus,
)
from app.modules.inbox.policy import META_CHANNELS, reply_window
from app.modules.inbox.textsearch import digits, email_local, like_pattern, sql_fold
from app.modules.orders.models import Customer, CustomerIdentity

log = logging.getLogger("app.inbox")

ACTION_FAQ = "inbox.reply_faq"
ACTION_GENERAL = "inbox.reply_general"
ACTION_ESCALATE = "inbox.escalate"
ACTION_ACK = "inbox.ack_escalation"
REPLY_ACTIONS = (ACTION_FAQ, ACTION_GENERAL, ACTION_ESCALATE)
ACK_TEXT_KEY = "inbox.escalation_ack_text"
DEFAULT_ACK_TEXT = (
    "Dạ mình đã nhận được tin của bạn. Việc này mình muốn tự xem kỹ, mình sẽ trả lời bạn trong hôm nay nhé."
)

FAQ_INTENTS = {Intent.ASK_PRICE, Intent.ASK_STOCK, Intent.ASK_SHIPPING, Intent.ASK_ARRIVAL}
ALWAYS_ESCALATE = {Intent.COMPLAINT, Intent.HEALTH_SAFETY}
MIN_CONFIDENCE = 0.5

KIND_MAP = {
    "comment": ThreadKind.COMMENT,
    "direct_message": ThreadKind.DIRECT_MESSAGE,
    "group_message": ThreadKind.GROUP,
}
INTENT_LABELS = {
    Intent.ASK_PRICE: "Hỏi giá",
    Intent.ASK_STOCK: "Hỏi còn hàng",
    Intent.ASK_SHIPPING: "Hỏi phí giao",
    Intent.ASK_ARRIVAL: "Hỏi hàng về",
    Intent.ASK_PRODUCT: "Hỏi cách dùng",
    Intent.PURCHASE: "Muốn mua",
    Intent.ORDER_STATUS: "Hỏi đơn",
    Intent.COMPLAINT: "Khiếu nại",
    Intent.HEALTH_SAFETY: "Sức khoẻ, an toàn",
    Intent.FIND_REQUEST: "Nhờ tìm",
    Intent.SMALL_TALK: "Chào hỏi",
    Intent.OTHER: "Khác",
}
REASON_LABELS = {
    EscalationReason.COMPLAINT: "Khiếu nại",
    EscalationReason.DEFECT: "Hàng lỗi",
    EscalationReason.HEALTH: "Sức khoẻ, an toàn",
    EscalationReason.REFUND: "Đòi hoàn tiền",
    EscalationReason.LOW_CONFIDENCE: "AI chưa đủ dữ liệu",
    EscalationReason.OTHER: "Cần chị xem",
}
CHANNEL_LABELS = {
    Channel.FACEBOOK: "Facebook",
    Channel.INSTAGRAM: "Instagram",
    Channel.ZALO_OA: "Zalo",
    Channel.ZALO: "Zalo",
    Channel.ZALO_GROUP: "Nhóm Zalo",
    Channel.TIKTOK: "TikTok",
    Channel.WEB: "Website",
}


def thread_key(thread_id: uuid.UUID) -> str:
    return f"thread:{thread_id}"


def thread_href(thread_id: uuid.UUID) -> str:
    return f"/desk/khach/hoi-thoai/{thread_id}"


# ---- nhận tin ----------------------------------------------------------------------------------------------------


async def get_or_create_account(db: AsyncSession, channel: Channel, external_id: str, driver: str) -> ChannelAccount:
    acc = (
        await db.execute(
            select(ChannelAccount).where(ChannelAccount.channel == channel, ChannelAccount.external_id == external_id)
        )
    ).scalar_one_or_none()
    if acc is None:
        label = CHANNEL_LABELS.get(channel, str(channel))
        acc = ChannelAccount(
            channel=channel,
            external_id=external_id,
            name=f"{label} ({'giả' if driver == 'mock' else external_id})",
            driver=driver,
            status=AccountStatus.MOCK if driver == "mock" else AccountStatus.CONNECTED,
        )
        db.add(acc)
        await db.flush()
    return acc


async def _resolve_customer(db: AsyncSession, customer_id: uuid.UUID | None) -> uuid.UUID | None:
    seen = set()
    while customer_id and customer_id not in seen:
        seen.add(customer_id)
        c = await db.get(Customer, customer_id)
        if c is None:
            return None
        if not c.merged_into_id:
            return c.id
        customer_id = c.merged_into_id
    return customer_id


async def _find_customer(db: AsyncSession, channel: Channel, author_id: str, text: str) -> uuid.UUID | None:
    """Nhận ra khách: định danh kênh (customer_identities) → hội thoại khác cùng người → số điện thoại trong tin."""
    cid = (
        await db.execute(
            select(CustomerIdentity.customer_id).where(
                CustomerIdentity.channel == channel, CustomerIdentity.external_id == author_id
            )
        )
    ).scalar_one_or_none()
    if cid is None and author_id:
        cid = (
            await db.execute(
                select(Thread.customer_id)
                .where(
                    Thread.channel == channel,
                    Thread.participant_external_id == author_id,
                    Thread.customer_id.is_not(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    if cid is None:
        phone = rules.extract_phone(text)
        if phone:
            cid = (await db.execute(select(Customer.id).where(Customer.phone == phone))).scalar_one_or_none()
    return await _resolve_customer(db, cid)


async def ingest(db: AsyncSession, ev: InboundEvent, *, driver_name: str = "mock") -> Message | None:
    """Lưu một bình luận/tin nhắn đến. Trả None nếu tin đã có (webhook gửi lại) — chạy lặp lại không sinh trùng."""
    acc = await get_or_create_account(db, ev.channel, ev.account_external_id, driver_name)
    thread = (
        await db.execute(
            select(Thread).where(
                Thread.channel_account_id == acc.id, Thread.external_thread_id == ev.thread_external_id
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        thread = Thread(
            channel_account_id=acc.id,
            channel=ev.channel,
            kind=KIND_MAP.get(ev.kind, ThreadKind.DIRECT_MESSAGE),
            external_thread_id=ev.thread_external_id,
            external_post_id=ev.post_external_id,
            participant_name=ev.author_name,
            participant_external_id=ev.author_external_id,
        )
        db.add(thread)
        await db.flush()
    else:
        dup = (
            await db.execute(
                select(Message.id).where(
                    Message.thread_id == thread.id, Message.external_message_id == ev.message_external_id
                )
            )
        ).scalar_one_or_none()
        if dup:
            return None

    if thread.customer_id is None:
        thread.customer_id = await _find_customer(db, ev.channel, ev.author_external_id, ev.text)

    extracted: dict[str, Any] = {}
    if phone := rules.extract_phone(ev.text):
        extracted["phone"] = phone
    if code := rules.extract_order_code(ev.text):
        extracted["order_code"] = code
    msg = Message(
        thread_id=thread.id,
        direction=Direction.INBOUND,
        sender=Actor.CUSTOMER,
        external_message_id=ev.message_external_id,
        author_name=ev.author_name,
        body=ev.text,
        attachments=[{"url": u} for u in ev.attachments],
        sent_at=ev.sent_at,
        status=MessageStatus.RECEIVED,
        extracted=extracted,
    )
    db.add(msg)
    thread.snippet = ev.text[:300]
    thread.last_message_at = max(filter(None, [thread.last_message_at, ev.sent_at]))
    thread.last_inbound_at = max(filter(None, [thread.last_inbound_at, ev.sent_at]))
    thread.unread_count += 1
    if not thread.participant_name:
        thread.participant_name = ev.author_name
    if thread.status != ThreadStatus.SPAM and not thread.needs_owner:
        thread.status = ThreadStatus.OPEN
    await db.flush()
    await events.emit("message.received", {"thread_id": str(thread.id), "message_id": str(msg.id)}, db=db)
    return msg


# ---- AI soạn -----------------------------------------------------------------------------------------------------


async def _supersede(db: AsyncSession, thread: Thread, *, include_escalation: bool) -> None:
    kinds = [ReplyKind.INSTANT, ReplyKind.DRAFT] + ([ReplyKind.ESCALATION] if include_escalation else [])
    await db.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.thread_id == thread.id,
            ReplyDraft.status == ReplyStatus.PENDING_REVIEW,
            ReplyDraft.kind.in_(kinds),
        )
        .values(status=ReplyStatus.SUPERSEDED, updated_at=now_utc())
    )
    actions = [ACTION_FAQ, ACTION_GENERAL] + ([ACTION_ESCALATE] if include_escalation else [])
    for a in actions:
        await control.cancel_pending(db, action=a, dedupe_key=thread_key(thread.id))


def _name(thread: Thread, inp: DraftReplyIn | None = None) -> str:
    return (inp.customer_name if inp and inp.customer_name else None) or thread.participant_name or "Khách"


def _preview(thread: Thread, msg: Message, inp: DraftReplyIn, **extra: Any) -> dict[str, Any]:
    return {
        "customer": _name(thread, inp),
        "channel": str(thread.channel),
        "channel_label": CHANNEL_LABELS.get(thread.channel, str(thread.channel)),
        "kind": str(thread.kind),
        "message": msg.body,
        "thread_id": str(thread.id),
        "href": thread_href(thread.id),
        **extra,
    }


async def triage(db: AsyncSession, message_id: uuid.UUID, *, owner_note: str | None = None) -> ReplyDraft | None:
    """Phân loại tin đến và soạn trả lời / chuyển chị. Chạy lại cho cùng tin thì thay bản nháp cũ."""
    msg = await db.get(Message, message_id)
    if msg is None or msg.direction != Direction.INBOUND:
        return None
    thread = await db.get(Thread, msg.thread_id)
    if thread is None or thread.status == ThreadStatus.SPAM:
        return None
    was_escalated = thread.needs_owner
    prev_esc = None
    if was_escalated:
        prev = (
            await db.execute(
                select(ReplyDraft)
                .where(
                    ReplyDraft.thread_id == thread.id,
                    ReplyDraft.kind == ReplyKind.ESCALATION,
                    ReplyDraft.status == ReplyStatus.PENDING_REVIEW,
                )
                .order_by(ReplyDraft.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if prev is not None:
            opts = [EscalationOption.model_validate(o) for o in await draft_options(db, prev)]
            prev_esc = (prev.body.split(" — Khách nhắn thêm")[0], opts)
    await _supersede(db, thread, include_escalation=True)

    inp = await context.build(db, thread, msg, owner_note=owner_note)
    run_id = None
    try:
        res = await ai.run("inbox.draft_reply", inp, DraftReplyOut)
        out, run_id = res.output, res.run_id
    except ai.AIError as e:
        log.warning("AI không soạn được trả lời cho tin %s: %s", msg.id, e)
        out = DraftReplyOut(
            intent="other", confidence=0, enough_data=False, reply="", escalate=True,
            escalation_reason="low_confidence", summary=f"AI chưa xử lý được tin này ({e.message}).",
        )  # fmt: skip

    intent = Intent(out.intent)
    msg.intent = intent
    msg.intent_confidence = round(out.confidence, 2)  # type: ignore[assignment]
    thread.last_intent = intent
    if out.product_id and any(p.id == out.product_id for p in inp.products):
        thread.product_id = uuid.UUID(out.product_id)

    risk = rules.risk_reason(msg.body)
    reason: EscalationReason | None = None
    if intent == Intent.HEALTH_SAFETY or risk == "health":
        reason = EscalationReason.HEALTH
    elif risk == "defect" or out.escalation_reason == "defect":
        reason = EscalationReason.DEFECT
    elif intent == Intent.COMPLAINT or risk == "complaint":
        reason = EscalationReason.REFUND if out.escalation_reason == "refund" else EscalationReason.COMPLAINT
    elif out.escalate or not out.enough_data or out.confidence < MIN_CONFIDENCE or not out.reply.strip():
        reason = EscalationReason(out.escalation_reason or "low_confidence")
    elif was_escalated:  # đang chờ chị: tin mới không làm AI tự trả lời
        reason = thread.escalation_reason or EscalationReason.OTHER
    if reason is not None:
        if was_escalated and prev_esc is not None:
            out.summary = f"{prev_esc[0]} — Khách nhắn thêm: «{msg.body.strip()[:100]}»"
            out.options = out.options or prev_esc[1]
            if thread.escalation_reason and reason == EscalationReason.LOW_CONFIDENCE:
                reason = thread.escalation_reason
        return await _escalate(db, thread, msg, inp, out, reason, run_id, first=not was_escalated)

    kind = ReplyKind.INSTANT if intent in FAQ_INTENTS else ReplyKind.DRAFT
    action = ACTION_FAQ if kind == ReplyKind.INSTANT else ACTION_GENERAL
    draft = ReplyDraft(
        thread_id=thread.id,
        reply_to_message_id=msg.id,
        kind=kind,
        intent=intent,
        body=out.reply.strip(),
        confidence=round(out.confidence, 2),
        sources=[{"fact": f} for f in out.facts],
        ai_run_id=run_id,
    )
    db.add(draft)
    thread.status = ThreadStatus.NEEDS_OWNER
    await db.flush()
    name = _name(thread, inp)
    outcome = await control.propose(
        action,
        f"Trả lời {name}: {INTENT_LABELS.get(intent, 'tin nhắn').lower()}",
        {"draft_id": str(draft.id), "thread_id": str(thread.id), "body": draft.body},
        _preview(thread, msg, inp, reply=draft.body, intent=str(intent), intent_label=INTENT_LABELS.get(intent)),
        db=db,
        summary=out.summary,
        rationale="; ".join(out.facts) or None,
        sources=[{"fact": f} for f in out.facts],
        ref_type="threads",
        ref_id=thread.id,
        ai_run_id=run_id,
        dedupe_key=thread_key(thread.id),
    )
    if outcome.status == "pending":
        draft.approval_item_id = outcome.item_id
    elif outcome.status == "blocked":  # chị tắt việc này: không soạn, để chị tự trả lời
        await db.delete(draft)
        draft = None  # type: ignore[assignment]
    elif outcome.status == "failed":
        log.warning("AI tự gửi lỗi (%s), để nháp chờ chị: %s", action, outcome.error)
    await db.flush()
    return draft


async def _escalate(
    db: AsyncSession,
    thread: Thread,
    msg: Message,
    inp: DraftReplyIn,
    out: DraftReplyOut,
    reason: EscalationReason,
    run_id: uuid.UUID | None,
    *,
    first: bool,
) -> ReplyDraft:
    thread.needs_owner = True
    thread.status = ThreadStatus.NEEDS_OWNER
    thread.escalation_reason = reason
    summary = out.summary.strip() or f"{_name(thread, inp)} nhắn: «{msg.body[:120]}»"
    draft = ReplyDraft(
        thread_id=thread.id,
        reply_to_message_id=msg.id,
        kind=ReplyKind.ESCALATION,
        intent=msg.intent,
        body=summary,
        confidence=round(out.confidence, 2),
        sources=[{"fact": f} for f in out.facts],
        ai_run_id=run_id,
    )
    db.add(draft)
    await db.flush()
    options = [o.model_dump() for o in out.options[:2]]
    outcome = await control.propose(
        ACTION_ESCALATE,
        f"Chờ chị: {_name(thread, inp)} — {REASON_LABELS[reason].lower()}",
        {"draft_id": str(draft.id), "thread_id": str(thread.id), "body": ""},
        _preview(thread, msg, inp, summary=summary, reason=str(reason), reason_label=REASON_LABELS[reason],
                 options=options),
        db=db,
        summary=summary,
        rationale=REASON_LABELS[reason],
        ref_type="threads",
        ref_id=thread.id,
        ai_run_id=run_id,
        dedupe_key=thread_key(thread.id),
        priority=10 if reason != EscalationReason.LOW_CONFIDENCE else 5,
    )  # fmt: skip
    draft.approval_item_id = outcome.item_id
    if first and thread.kind != ThreadKind.GROUP:
        text = await control.get_setting(db, ACK_TEXT_KEY) or DEFAULT_ACK_TEXT
        await control.propose(
            ACTION_ACK,
            f"Báo {_name(thread, inp)}: chị sẽ trả lời trong hôm nay",
            {"thread_id": str(thread.id), "body": text},
            _preview(thread, msg, inp, reply=text),
            db=db,
            ref_type="threads",
            ref_id=thread.id,
            dedupe_key=thread_key(thread.id),
            ai_generated=False,
        )
    await db.flush()
    return draft


# ---- gửi ---------------------------------------------------------------------------------------------------------


async def _last_inbound(db: AsyncSession, thread: Thread) -> Message | None:
    return (
        await db.execute(
            select(Message)
            .where(Message.thread_id == thread.id, Message.direction == Direction.INBOUND)
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def driver_for(db: AsyncSession, thread: Thread) -> Any:
    acc = await db.get(ChannelAccount, thread.channel_account_id) if thread.channel_account_id else None
    return messaging_driver(acc.driver if acc else "mock", thread.channel)


async def capabilities(db: AsyncSession, thread: Thread) -> dict[str, Any]:
    try:
        driver = await driver_for(db, thread)
    except AppError:
        driver = None
    w = reply_window(thread, human=True)
    private = (
        thread.kind == ThreadKind.COMMENT
        and thread.channel in META_CHANNELS
        and bool(getattr(driver, "supports_private_reply", False))
    )
    return {"can_reply": w.allowed, "reason": w.reason, "human_agent_tag": w.tag is not None, "private_reply": private}


async def deliver(
    db: AsyncSession,
    thread: Thread,
    body: str,
    *,
    sender: Actor,
    ai_generated: bool,
    human: bool,
    private: bool = False,
) -> Message:
    """Gửi một câu trả lời qua kênh của hội thoại, theo luật cửa sổ trả lời, rồi ghi vào hội thoại."""
    body = body.strip()
    if not body:
        raise BadRequest("Câu trả lời đang trống.")
    driver = await driver_for(db, thread)
    if thread.kind == ThreadKind.COMMENT:
        last = await _last_inbound(db, thread)
        if last is None or not last.external_message_id:
            raise BadRequest("Không tìm thấy bình luận để trả lời.")
        w = reply_window(thread, human=human, private=private, comment_at=last.sent_at)
        if not w.allowed:
            raise BadRequest(w.reason, code="outside_window")
        if private:
            fn = getattr(driver, "send_private_reply", None)
            if fn is None or not getattr(driver, "supports_private_reply", False):
                raise BadRequest("Kênh này chưa nhắn riêng từ bình luận được.", code="not_supported")
            sent = await fn(thread.channel, last.external_message_id, body)
        else:
            target = (
                thread.external_thread_id.removeprefix("c:")
                if thread.external_thread_id.startswith("c:")
                else last.external_message_id
            )
            sent = await driver.reply_comment(thread.channel, target, body)
    else:
        w = reply_window(thread, human=human)
        if not w.allowed:
            raise BadRequest(w.reason, code="outside_window")
        if w.tag and getattr(driver, "supports_message_tags", False):
            sent = await driver.send_message(thread.channel, thread.external_thread_id, body, tag=w.tag)
        else:
            sent = await driver.send_message(thread.channel, thread.external_thread_id, body)
    now = now_utc()
    msg = Message(
        thread_id=thread.id,
        direction=Direction.OUTBOUND,
        sender=sender,
        external_message_id=sent.external_id or None,
        author_name="Chị" if sender in (Actor.OWNER, Actor.HELPER) else "AI",
        body=body,
        sent_at=sent.sent_at or now,
        status=MessageStatus.SENT,
        ai_generated=ai_generated,
        read_at=now,
        extracted={"private_reply": True} if private else {},
    )
    db.add(msg)
    thread.snippet = body[:300]
    thread.last_message_at = msg.sent_at
    thread.unread_count = 0
    await db.flush()
    return msg


def _actor(user: User | None) -> Actor:
    return Actor(user.role.value) if user else Actor.OWNER


async def send_draft(
    db: AsyncSession,
    draft: ReplyDraft,
    body: str | None,
    *,
    mode: str,
    user: User | None,
    private: bool = False,
) -> Message | None:
    """Thực thi một bản nháp (handler của control dùng). Bản nháp chuyển chị gửi khi có `body`, không thì chỉ đóng."""
    if draft.status not in (ReplyStatus.PENDING_REVIEW, ReplyStatus.APPROVED):
        raise Conflict("Bản nháp này không còn dùng được (khách đã nhắn thêm hoặc đã gửi rồi).", code="draft_stale")
    thread = await db.get(Thread, draft.thread_id)
    if thread is None:
        raise NotFound("Không tìm thấy hội thoại.")
    auto = mode == "auto"
    text = (body if body is not None else ("" if draft.kind == ReplyKind.ESCALATION else draft.body)).strip()
    msg = None
    if text:
        ai_text = draft.kind != ReplyKind.ESCALATION or any(
            text == o.get("reply") for o in await draft_options(db, draft)
        )
        sender = Actor.AI if auto else _actor(user)
        msg = await deliver(db, thread, text, sender=sender, ai_generated=ai_text, human=not auto, private=private)
        draft.sent_message_id = msg.id
        if draft.kind != ReplyKind.ESCALATION:
            draft.body = text
    elif draft.kind != ReplyKind.ESCALATION:
        raise BadRequest("Câu trả lời đang trống.")
    draft.status = ReplyStatus.AUTO_SENT if auto else (ReplyStatus.SENT if msg else ReplyStatus.APPROVED)
    if draft.kind == ReplyKind.ESCALATION:
        thread.needs_owner = False
        thread.escalation_reason = None
        thread.status = ThreadStatus.WAITING_CUSTOMER if msg else ThreadStatus.CLOSED
    else:
        thread.status = ThreadStatus.AI_HANDLED if auto else ThreadStatus.WAITING_CUSTOMER
    await db.flush()
    return msg


async def draft_options(db: AsyncSession, draft: ReplyDraft) -> list[dict[str, Any]]:
    """Phương án gợi ý của việc chuyển chị nằm ở preview của việc chờ duyệt."""
    if draft.kind != ReplyKind.ESCALATION or not draft.approval_item_id:
        return []
    item = await db.get(ApprovalItem, draft.approval_item_id)
    return list((item.preview or {}).get("options", [])) if item else []


async def send_draft_now(
    db: AsyncSession, draft_id: uuid.UUID, body: str | None, user: User, *, private: bool = False
) -> ReplyDraft:
    """Chị bấm Gửi (hoặc «Đã xử lý») trên bản nháp: đi qua hàng chờ duyệt để có nhật ký; không còn việc chờ thì gửi
    thẳng và ghi lưu vết."""
    draft = await db.get(ReplyDraft, draft_id)
    if draft is None:
        raise NotFound("Không tìm thấy bản nháp.")
    item = await db.get(ApprovalItem, draft.approval_item_id) if draft.approval_item_id else None
    if item and item.status in (ApprovalStatus.PENDING, ApprovalStatus.FAILED):
        edited: dict[str, Any] = {
            "body": body if body is not None else ("" if draft.kind == ReplyKind.ESCALATION else draft.body)
        }
        if private:
            edited["private"] = True
        item = await control.approve(db, item.id, user, edited_payload=edited)
        if item.status == ApprovalStatus.FAILED:
            raise BadRequest(item.error or "Chưa gửi được.", code="send_failed")
    else:
        await send_draft(db, draft, body, mode="approved", user=user, private=private)
        await control.audit(
            db, "inbox.reply_sent", user=user, entity_type="threads", entity_id=draft.thread_id,
            summary="Chị gửi câu trả lời từ bản nháp", data={"draft_id": str(draft.id)},
        )  # fmt: skip
    await db.refresh(draft)
    return draft


async def dismiss_draft(db: AsyncSession, draft_id: uuid.UUID, user: User) -> ReplyDraft:
    draft = await db.get(ReplyDraft, draft_id)
    if draft is None:
        raise NotFound("Không tìm thấy bản nháp.")
    if draft.kind == ReplyKind.ESCALATION:
        raise BadRequest("Việc chuyển chị: chị trả lời khách hoặc bấm «Đã xử lý».")
    if draft.status != ReplyStatus.PENDING_REVIEW:
        raise Conflict("Bản nháp này đã được xử lý.", code="draft_stale")
    draft.status = ReplyStatus.REJECTED
    for a in (ACTION_FAQ, ACTION_GENERAL):
        await control.cancel_pending(db, action=a, dedupe_key=thread_key(draft.thread_id))
    await control.audit(db, "inbox.draft_dismissed", user=user, entity_type="reply_drafts", entity_id=draft.id)
    await db.flush()
    return draft


async def owner_reply(
    db: AsyncSession, thread_id: uuid.UUID, body: str, user: User, *, private: bool = False
) -> Message:
    """Chị tự gõ trả lời: gửi ngay, thay mọi bản nháp đang chờ, coi như việc chuyển chị đã xử lý."""
    thread = await get_thread(db, thread_id)
    msg = await deliver(db, thread, body, sender=_actor(user), ai_generated=False, human=True, private=private)
    await _supersede(db, thread, include_escalation=True)
    await control.cancel_pending(db, action=ACTION_ACK, dedupe_key=thread_key(thread.id))
    thread.needs_owner = False
    thread.escalation_reason = None
    thread.status = ThreadStatus.WAITING_CUSTOMER
    await control.audit(
        db, "inbox.owner_replied", user=user, entity_type="threads", entity_id=thread.id, summary=body[:200]
    )
    await db.flush()
    return msg


async def redraft(db: AsyncSession, thread_id: uuid.UUID, note: str | None) -> ReplyDraft | None:
    thread = await get_thread(db, thread_id)
    last = await _last_inbound(db, thread)
    if last is None:
        raise BadRequest("Hội thoại chưa có tin của khách.")
    if thread.needs_owner and not note:
        raise BadRequest("Việc này đang chờ chị quyết, AI không tự soạn lại.")
    return await triage(db, last.id, owner_note=note)


# ---- đọc ---------------------------------------------------------------------------------------------------------


async def get_thread(db: AsyncSession, thread_id: uuid.UUID) -> Thread:
    t = await db.get(Thread, thread_id)
    if t is None:
        raise NotFound("Không tìm thấy hội thoại.")
    return t


def _search(q: str) -> Any:
    pat = like_pattern(q)
    local = like_pattern(q.split("@", 1)[0]) if "@" in q else pat
    conds = [
        sql_fold(Thread.participant_name).like(pat),
        exists().where(Message.thread_id == Thread.id, sql_fold(Message.body).like(pat)),
        exists().where(
            Customer.id == Thread.customer_id,
            or_(sql_fold(Customer.name).like(pat), sql_fold(email_local(Customer.email)).like(local)),
        ),
    ]
    d = digits(q)
    if len(d) >= 4:
        conds.append(exists().where(Customer.id == Thread.customer_id, Customer.phone.like(f"%{d}%")))
    return or_(*conds)


async def list_threads(
    db: AsyncSession, page: PageParams, *, tab: str = "waiting", q: str | None = None, channel: Channel | None = None
) -> Paginated[Thread]:
    stmt = select(Thread).where(Thread.status != ThreadStatus.SPAM)
    if tab == "waiting":
        stmt = stmt.where(Thread.status == ThreadStatus.NEEDS_OWNER)
    elif tab == "ai":
        stmt = stmt.where(Thread.status == ThreadStatus.AI_HANDLED)
    if channel:
        stmt = stmt.where(Thread.channel == channel)
    if q and q.strip():
        stmt = stmt.where(_search(q.strip()))
    stmt = stmt.order_by(Thread.needs_owner.desc(), Thread.last_message_at.desc().nulls_last())
    return await paginate(db, stmt, page)


async def counts(db: AsyncSession) -> dict[str, int]:
    rows = dict(
        (
            await db.execute(
                select(Thread.status, func.count()).where(Thread.status != ThreadStatus.SPAM).group_by(Thread.status)
            )
        ).all()
    )
    return {
        "waiting": rows.get(ThreadStatus.NEEDS_OWNER, 0),
        "ai": rows.get(ThreadStatus.AI_HANDLED, 0),
        "all": sum(rows.values()),
    }


async def active_drafts(db: AsyncSession, thread_ids: list[uuid.UUID]) -> dict[uuid.UUID, ReplyDraft]:
    if not thread_ids:
        return {}
    rows = (
        await db.execute(
            select(ReplyDraft)
            .where(ReplyDraft.thread_id.in_(thread_ids), ReplyDraft.status == ReplyStatus.PENDING_REVIEW)
            .order_by(ReplyDraft.created_at)
        )
    ).scalars()
    return {d.thread_id: d for d in rows}  # bản mới nhất thắng


async def last_messages(
    db: AsyncSession, thread_ids: list[uuid.UUID], direction: Direction | None = None
) -> dict[uuid.UUID, Message]:
    if not thread_ids:
        return {}
    cond = [Message.thread_id.in_(thread_ids)] + ([Message.direction == direction] if direction else [])
    sub = (
        select(Message.thread_id, func.max(Message.sent_at).label("mx"))
        .where(*cond)
        .group_by(Message.thread_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Message)
            .join(sub, (Message.thread_id == sub.c.thread_id) & (Message.sent_at == sub.c.mx))
            .where(*cond[1:])
        )
    ).scalars()
    return {m.thread_id: m for m in rows}


async def messages_of(db: AsyncSession, thread_id: uuid.UUID) -> list[Message]:
    return list(
        (await db.execute(select(Message).where(Message.thread_id == thread_id).order_by(Message.sent_at))).scalars()
    )


async def mark_read(db: AsyncSession, thread: Thread) -> None:
    if thread.unread_count:
        now = now_utc()
        await db.execute(
            update(Message)
            .where(Message.thread_id == thread.id, Message.direction == Direction.INBOUND, Message.read_at.is_(None))
            .values(read_at=now)
        )
        thread.unread_count = 0
        await db.flush()


async def link_customer(db: AsyncSession, thread_id: uuid.UUID, customer_id: uuid.UUID | None, user: User) -> Thread:
    thread = await get_thread(db, thread_id)
    if customer_id is not None and await db.get(Customer, customer_id) is None:
        raise NotFound("Không tìm thấy khách.")
    thread.customer_id = customer_id
    if customer_id and thread.participant_external_id:  # các hội thoại khác của cùng người trên cùng kênh
        await db.execute(
            update(Thread)
            .where(
                Thread.channel == thread.channel,
                Thread.participant_external_id == thread.participant_external_id,
                Thread.customer_id.is_(None),
            )
            .values(customer_id=customer_id)
        )
    await control.audit(
        db, "inbox.customer_linked", user=user, entity_type="threads", entity_id=thread.id,
        data={"customer_id": str(customer_id) if customer_id else None},
    )  # fmt: skip
    await db.flush()
    return thread


async def set_status(db: AsyncSession, thread_id: uuid.UUID, status: ThreadStatus, user: User) -> Thread:
    thread = await get_thread(db, thread_id)
    if status in (ThreadStatus.CLOSED, ThreadStatus.SPAM):
        await _supersede(db, thread, include_escalation=True)
        await control.cancel_pending(db, action=ACTION_ACK, dedupe_key=thread_key(thread.id))
        thread.needs_owner = False
        thread.escalation_reason = None
    thread.status = status
    await control.audit(db, "inbox.status_changed", user=user, entity_type="threads", entity_id=thread.id,
                        data={"status": str(status)})  # fmt: skip
    await db.flush()
    return thread
