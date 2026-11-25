"""Trợ lý hỏi đáp (e7). Đọc hồ sơ sản phẩm từ bảng của catalog / assessment (CHỈ ĐỌC), gọi AI, kiểm dẫn nguồn,
không biết thì chuyển chị qua control.propose (luôn hỏi chị). Giới hạn tần suất theo phiên, lưu hội thoại."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import ratelimit
from app.core.errors import AppError, BadRequest, NotFound
from app.core.timeutil import now_utc
from app.modules.assessment.models import Assessment, ReviewDigest
from app.modules.assistant.ai_tasks import AnswerIn, AnswerOut, Fact, Turn
from app.modules.assistant.models import (
    AnswerBasis,
    AssistantConversation,
    AssistantMessage,
    AssistantRole,
    ConversationStatus,
    Feedback,
)
from app.modules.catalog.models import Product, ProductStatus

log = logging.getLogger("app.assistant")

PER_MINUTE = 6
PER_DAY = 40
# Bỏ cookie là có phiên mới → thêm trần theo IP mỗi ngày để một máy không đốt hết trần chi phí AI của chị.
PER_DAY_IP = 120
MAX_QUESTION = 500
HANDOFF_TEXT = (
    "Câu này mình chưa có thông tin chắc chắn nên đã ghi lại, mình sẽ trả lời bạn sớm (thường trong buổi tối). "
    "Bạn để lại số điện thoại hoặc Zalo nếu muốn mình nhắn lại."
)
OFFLINE_TEXT = "Trợ lý đang tạm nghỉ. Mình đã ghi lại câu hỏi và sẽ trả lời bạn sớm."


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Bạn hỏi nhanh quá, đợi một chút rồi hỏi tiếp nhé."


async def _check_burst(key: str) -> None:
    """Tối đa PER_MINUTE câu mỗi phút (đếm chung trên Redis, xem app.core.ratelimit)."""
    if not await ratelimit.hit(f"assistant:{key}", PER_MINUTE, 60):
        raise RateLimited()


def reset_limits() -> None:
    ratelimit.reset()


# ---- hồ sơ làm căn cứ ------------------------------------------------------------------------------------------


def _flat(v: Any) -> str:
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_flat(x)}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(_flat(x) for x in v)
    return "" if v is None else str(v).strip()


async def product_facts(db: AsyncSession, p: Product) -> list[Fact]:
    """Dữ kiện có mã nguồn cho một món — câu trả lời chỉ được dẫn về các mục này."""
    pid = str(p.id)
    facts: list[Fact] = []

    def add(ref: str, label: str, text: str | None) -> None:
        if text and text.strip():
            facts.append(Fact(ref=f"product:{pid}:{ref}", label=label, text=text.strip()[:1500]))

    add("name", "Tên món", f"{p.name}{' — ' + p.subtitle if p.subtitle else ''}")
    add("short_description", "Mô tả ngắn", p.short_description)
    add("description", "Mô tả", p.description)
    for i, s in enumerate(p.specs or []):
        if isinstance(s, dict):
            add(f"specs:{i}", f"Thông số · {s.get('label', '')}", f"{s.get('label', '')}: {s.get('value', '')}")
    for i, f in enumerate(p.faq or []):
        if isinstance(f, dict):
            add(f"faq:{i}", f"Hỏi–đáp · {f.get('q', '')}", f"Hỏi: {f.get('q', '')} — Đáp: {f.get('a', '')}")
    add("reason_selected", "Vì sao mình chọn", p.reason_selected)
    add("not_satisfied", "Điều mình chưa ưng", p.not_satisfied)
    if p.trial_days:
        add("trial_days", "Thời gian thử", f"Mình đã dùng thử {p.trial_days} ngày trước khi chọn.")
    if p.considered_count:
        add("seal", "Con dấu", f"Mình xem {p.considered_count} mẫu cùng loại, chọn {p.selected_count}.")
    if p.weight_grams:
        add("weight", "Thông số · Khối lượng", f"{p.weight_grams} g")
    if p.shipping_notes:
        add("shipping_notes", "Lưu ý vận chuyển", _flat(p.shipping_notes))
    add("price", "Giá bán", f"{p.price_vnd:,} đồng".replace(",", ".") if p.price_vnd else None)
    if p.candidate_id:
        a = (await db.execute(select(Assessment).where(Assessment.candidate_id == p.candidate_id))).scalar_one_or_none()
        if a is not None:
            add("assessment.summary", "Hồ sơ thẩm định · Tóm tắt", a.summary)
            for i, s in enumerate(a.strengths or []):
                add(f"assessment.strengths:{i}", "Hồ sơ thẩm định · Điểm mạnh", _flat(s))
            for i, s in enumerate(a.weaknesses or []):
                add(f"assessment.weaknesses:{i}", "Hồ sơ thẩm định · Điểm yếu", _flat(s))
        for dg in (await db.execute(select(ReviewDigest).where(ReviewDigest.candidate_id == p.candidate_id))).scalars():
            for i, c in enumerate(dg.complaints or []):
                point = c.get("point") if isinstance(c, dict) else _flat(c)
                add(f"reviews.complaints:{i}", "Người mua chê (hồ sơ thẩm định)", point)
            for i, c in enumerate(dg.praise or []):
                point = c.get("point") if isinstance(c, dict) else _flat(c)
                add(f"reviews.praise:{i}", "Người mua khen (hồ sơ thẩm định)", point)
    return facts


async def shelf_facts(db: AsyncSession) -> list[Fact]:
    """Khi khách hỏi chung ở /hoi: mỗi món trên kệ một dữ kiện tóm tắt."""
    rows = (
        await db.execute(
            select(Product)
            .where(Product.status == ProductStatus.PUBLISHED)
            .order_by(Product.published_at.desc())
            .limit(40)
        )
    ).scalars()
    facts = []
    for p in rows:
        specs = "; ".join(f"{s.get('label')}: {s.get('value')}" for s in (p.specs or [])[:4] if isinstance(s, dict))
        text = " ".join(
            filter(None, [p.name, p.subtitle, p.short_description, specs, f"Giá {p.price_vnd:,}đ".replace(",", ".")])
        )
        facts.append(Fact(ref=f"product:{p.id}:card", label=f"Món trên kệ · {p.name}", text=text[:800]))
    return facts


# ---- hội thoại ---------------------------------------------------------------------------------------------------


async def get_conversation(db: AsyncSession, conversation_id: uuid.UUID, session_key: str) -> AssistantConversation:
    conv = await db.get(AssistantConversation, conversation_id)
    if conv is None or conv.session_key != session_key:
        raise NotFound("Không tìm thấy cuộc trò chuyện.")
    return conv


async def messages(db: AsyncSession, conv: AssistantConversation) -> list[AssistantMessage]:
    return list(
        (
            await db.execute(
                select(AssistantMessage)
                .where(AssistantMessage.conversation_id == conv.id)
                .order_by(AssistantMessage.created_at)
            )
        ).scalars()
    )


async def _day_count(db: AsyncSession, session_key: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(AssistantMessage)
            .join(AssistantConversation, AssistantConversation.id == AssistantMessage.conversation_id)
            .where(
                AssistantConversation.session_key == session_key,
                AssistantMessage.role == AssistantRole.USER,
                AssistantMessage.created_at >= now_utc() - timedelta(days=1),
            )
        )
    ).scalar_one()


def _basis(refs: list[str]) -> AnswerBasis:
    if any(".assessment" in r or ":assessment" in r for r in refs):
        return AnswerBasis.ASSESSMENT
    if any(":reviews" in r for r in refs):
        return AnswerBasis.REVIEWS
    return AnswerBasis.PRODUCT if refs else AnswerBasis.NONE


async def ask(
    db: AsyncSession,
    *,
    session_key: str,
    ip_hash: str | None,
    question: str,
    product_slug: str | None = None,
    conversation_id: uuid.UUID | None = None,
    page_path: str | None = None,
) -> tuple[AssistantConversation, AssistantMessage, AssistantMessage]:
    question = " ".join((question or "").split())
    if len(question) < 2:
        raise BadRequest("Bạn gõ câu hỏi giúp mình nhé.")
    if len(question) > MAX_QUESTION:
        raise BadRequest(f"Câu hỏi dài quá {MAX_QUESTION} chữ, bạn hỏi gọn lại giúp mình.")
    await _check_burst(f"s:{session_key}")
    if ip_hash:
        await _check_burst(f"ip:{ip_hash}")
        if not await ratelimit.hit(f"assistant:day:{ip_hash}", PER_DAY_IP, 86400):
            raise RateLimited("Hôm nay bạn đã hỏi nhiều rồi. Bạn nhắn thẳng cho mình qua Zalo nhé.")
    if await _day_count(db, session_key) >= PER_DAY:
        raise RateLimited("Hôm nay bạn đã hỏi nhiều rồi. Bạn nhắn thẳng cho mình qua Zalo nhé.")

    product: Product | None = None
    if product_slug:
        product = (
            await db.execute(
                select(Product).where(Product.slug == product_slug, Product.status == ProductStatus.PUBLISHED)
            )
        ).scalar_one_or_none()
        if product is None:
            raise NotFound("Không tìm thấy món này.")

    conv: AssistantConversation | None = None
    if conversation_id:
        conv = await get_conversation(db, conversation_id, session_key)
        if product is None and conv.product_id:
            product = await db.get(Product, conv.product_id)
    if conv is None:
        conv = AssistantConversation(
            session_key=session_key, ip_hash=ip_hash, product_id=product.id if product else None, page_path=page_path
        )
        db.add(conv)
        await db.flush()
    history = [Turn(role=m.role.value, content=m.content) for m in (await messages(db, conv))[-6:]]
    user_msg = AssistantMessage(conversation_id=conv.id, role=AssistantRole.USER, content=question)
    db.add(user_msg)
    await db.flush()

    facts = await product_facts(db, product) if product else await shelf_facts(db)
    by_ref = {f.ref: f for f in facts}
    run_id = None
    try:
        res = await ai.run(
            "assistant.answer",
            AnswerIn(question=question, product_name=product.name if product else None, facts=facts, history=history),
            AnswerOut,
        )
        out, run_id = res.output, res.run_id
        refs = [r for r in dict.fromkeys(out.citations) if r in by_ref]
        unknown = out.unknown or not refs  # không dẫn được nguồn thật → coi như không biết
        answer = out.answer.strip() if not unknown else HANDOFF_TEXT
        confidence = out.confidence if not unknown else min(out.confidence, 0.3)
    except ai.AIError as e:
        log.warning("Trợ lý không trả lời được: %s", e)
        refs, unknown, answer, confidence = [], True, OFFLINE_TEXT, 0.0

    bot = AssistantMessage(
        conversation_id=conv.id,
        role=AssistantRole.ASSISTANT,
        content=answer,
        citations=[
            {
                "type": "product",
                "id": str(product.id) if product else r.split(":")[1],
                "ref": r,
                "label": by_ref[r].label,
                "quote": by_ref[r].text[:300],
            }
            for r in refs
        ],
        basis=_basis(refs),
        confidence=Decimal(str(round(confidence, 2))),
        unknown=unknown,
        ai_run_id=run_id,
    )
    db.add(bot)
    conv.message_count += 2
    conv.last_message_at = now_utc()
    await db.flush()
    if unknown:
        await hand_off(db, conv, question, product)
    return conv, user_msg, bot


async def hand_off(db: AsyncSession, conv: AssistantConversation, question: str, product: Product | None) -> None:
    """Chuyển câu hỏi cho chị: một việc chờ cho mỗi cuộc trò chuyện (gom các câu chưa trả lời)."""
    conv.status = ConversationStatus.HANDED_OFF
    conv.handed_off_at = conv.handed_off_at or now_utc()
    pending = [m.content for m in await messages(db, conv) if m.role == AssistantRole.USER][-5:]
    conv.handoff_reason = "Trợ lý không có căn cứ để trả lời"
    await db.flush()
    await control.propose(
        "assistant.forward_to_owner",
        f"Khách hỏi{' về ' + product.name if product else ''}: {question[:80]}",
        {"conversation_id": str(conv.id), "reply": ""},
        {
            "question": question,
            "recent_questions": pending,
            "product": product.name if product else None,
            "contact": conv.contact,
            "hint": "Chị gõ câu trả lời vào ô «reply» rồi duyệt; khách mở lại khung hỏi sẽ thấy.",
        },
        db=db,
        summary="Trợ lý không có căn cứ trong hồ sơ nên không tự trả lời.",
        ref_type="assistant_conversations",
        ref_id=conv.id,
        dedupe_key=f"assistant:{conv.id}",
        priority=5,
    )


async def owner_reply(db: AsyncSession, conv: AssistantConversation, reply: str) -> AssistantMessage:
    reply = reply.strip()
    if not reply:
        raise BadRequest("Chị gõ câu trả lời cho khách vào ô «reply» trước khi duyệt.", code="empty_reply")
    msg = AssistantMessage(conversation_id=conv.id, role=AssistantRole.OWNER, content=reply)
    db.add(msg)
    conv.message_count += 1
    conv.last_message_at = now_utc()
    conv.status = ConversationStatus.OPEN
    await db.flush()
    return msg


async def set_contact(db: AsyncSession, conv: AssistantConversation, contact: str) -> AssistantConversation:
    conv.contact = contact.strip()[:200]
    await db.flush()
    return conv


async def set_feedback(db: AsyncSession, conv: AssistantConversation, message_id: uuid.UUID, value: Feedback) -> None:
    msg = await db.get(AssistantMessage, message_id)
    if msg is None or msg.conversation_id != conv.id or msg.role != AssistantRole.ASSISTANT:
        raise NotFound("Không tìm thấy câu trả lời.")
    msg.feedback = value
    await db.flush()
