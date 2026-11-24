"""Kịch bản livestream (f8): từ một đợt bán hoặc danh sách món → dàn ý, thứ tự món, điểm nhấn, câu khách hay hỏi
(đọc hộp thư + trợ lý web, chỉ đọc) và câu trả lời gợi ý. Chị là người lên hình (không tạo người số)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core.errors import BadRequest, Conflict, NotFound
from app.modules.assistant.models import AssistantConversation, AssistantMessage, AssistantRole
from app.modules.catalog.models import Drop, Product
from app.modules.content import facts
from app.modules.content.ai_io import LiveIn, LiveOut, LiveQuestion
from app.modules.content.models import LivestreamScript, ScriptStatus
from app.modules.content.service import ACTION_LIVE
from app.modules.control.models import ApprovalItem, User
from app.modules.inbox.models import Direction, Message, Thread

MAX_QUESTIONS = 30


async def customer_questions(db: AsyncSession, product_ids: list[uuid.UUID]) -> list[LiveQuestion]:
    """Câu khách đã hỏi về các món này (tin nhắn/bình luận + trợ lý web) — chỉ đọc, chỉ lấy câu có dấu hỏi."""
    if not product_ids:
        return []
    rows = (
        await db.execute(
            select(Message.body, Thread.product_id)
            .join(Thread, Thread.id == Message.thread_id)
            .where(Thread.product_id.in_(product_ids), Message.direction == Direction.INBOUND)
            .order_by(Message.sent_at.desc())
            .limit(MAX_QUESTIONS)
        )
    ).all()
    rows += (
        await db.execute(
            select(AssistantMessage.content, AssistantConversation.product_id)
            .join(AssistantConversation, AssistantConversation.id == AssistantMessage.conversation_id)
            .where(AssistantConversation.product_id.in_(product_ids), AssistantMessage.role == AssistantRole.USER)
            .order_by(AssistantMessage.created_at.desc())
            .limit(MAX_QUESTIONS)
        )
    ).all()
    seen: set[str] = set()
    out: list[LiveQuestion] = []
    for body, pid in rows:
        q = (body or "").strip()
        key = q.lower()
        if "?" not in q or len(q) > 300 or key in seen:
            continue
        seen.add(key)
        out.append(LiveQuestion(question=q, product_id=str(pid) if pid else None))
    return out[:MAX_QUESTIONS]


async def create(
    db: AsyncSession,
    *,
    title: str | None,
    drop_id: uuid.UUID | None,
    product_ids: list[uuid.UUID],
    minutes: int,
    scheduled_for: datetime | None,
    instruction: str | None,
    user: User | None,
) -> LivestreamScript:
    drop = await db.get(Drop, drop_id) if drop_id else None
    if drop_id and drop is None:
        raise NotFound("Không tìm thấy đợt bán.")
    ids = list(dict.fromkeys([*(it.product_id for it in (drop.items if drop else [])), *product_ids]))
    if not ids:
        raise BadRequest("Chị chọn một đợt bán hoặc vài món để soạn kịch bản.")
    products = {p.id: p for p in (await db.execute(select(Product).where(Product.id.in_(ids)))).scalars()}
    ordered = [products[i] for i in ids if i in products]
    if not ordered:
        raise NotFound("Không tìm thấy món đã chọn.")
    minutes = max(10, min(120, minutes))
    title = (title or "").strip() or (f"Live {drop.title}" if drop else f"Live {len(ordered)} món đã thử")
    row = LivestreamScript(
        title=title[:200],
        scheduled_for=scheduled_for,
        drop_id=drop.id if drop else None,
        status=ScriptStatus.DRAFTING,
        notes=instruction,
    )
    db.add(row)
    await db.flush()
    await generate(db, row, ordered, drop, minutes, instruction)
    return row


async def generate(
    db: AsyncSession,
    row: LivestreamScript,
    products: list[Product],
    drop: Drop | None,
    minutes: int,
    instruction: str | None,
) -> None:
    pfs = [facts.product_facts(p) for p in products]
    res = await ai.run(
        "content.livestream",
        LiveIn(
            title=row.title + (f" — ý chị: {instruction}" if instruction else ""),
            minutes=minutes,
            products=pfs,
            drop=await facts.drop_facts(db, drop) if drop else None,
            questions=await customer_questions(db, [p.id for p in products]),
            voice=facts.voice_card(await facts.active_voice(db)),
        ),
        LiveOut,
    )
    out = res.output
    valid = {str(p.id) for p in products}
    row.outline = [s.model_dump() for s in out.outline]
    row.items = sorted([it.model_dump() for it in out.items if it.product_id in valid], key=lambda it: it["order"]) or [
        {"product_id": str(p.id), "order": i + 1, "name": p.name, "talking_points": [], "demo": "", "price_note": ""}
        for i, p in enumerate(products)
    ]
    row.faq = [f.model_dump() for f in out.faq]
    row.ai_generated = True
    row.ai_run_id = res.run_id
    row.status = ScriptStatus.PENDING_REVIEW
    await db.flush()
    o = await control.propose(
        ACTION_LIVE,
        f"Kịch bản livestream: {row.title}",
        {"script_id": str(row.id), "minutes": minutes},
        preview={"outline": row.outline, "items": [i["name"] for i in row.items], "faq_count": len(row.faq)},
        db=db,
        summary=f"{len(row.items)} món, {len(row.faq)} câu hỏi gợi ý, {minutes} phút",
        rationale="Soạn từ hồ sơ chọn của từng món và câu khách đã hỏi trong hộp thư/trợ lý.",
        ref_type="livestream_scripts",
        ref_id=row.id,
        ai_run_id=res.run_id,
        dedupe_key=f"live:{row.id}",
    )
    row.approval_item_id = o.item_id
    if o.status == "applied":
        row.status = ScriptStatus.APPROVED
    await db.flush()


async def apply_approve(db: AsyncSession, payload: dict[str, Any], item: ApprovalItem | None) -> control.HandlerResult:
    row = await db.get(LivestreamScript, uuid.UUID(payload["script_id"]))
    if row is None:
        raise Conflict("Kịch bản không còn.", code="not_found")
    for k in ("outline", "items", "faq", "notes"):
        if k in payload:
            setattr(row, k, payload[k])
    row.status = ScriptStatus.APPROVED
    if item is not None:
        row.approval_item_id = item.id
    await db.flush()
    return control.HandlerResult(
        result={"script_id": str(row.id)},
        summary=f"Duyệt kịch bản «{row.title}»",
        ref_type="livestream_scripts",
        ref_id=row.id,
    )


async def regenerate(db: AsyncSession, row: LivestreamScript, note: str) -> None:
    ids = [uuid.UUID(i["product_id"]) for i in row.items if i.get("product_id")]
    products = {p.id: p for p in (await db.execute(select(Product).where(Product.id.in_(ids)))).scalars()}
    drop = await db.get(Drop, row.drop_id) if row.drop_id else None
    minutes = sum(int(s.get("minutes") or 0) for s in row.outline) or 30
    row.notes = note
    await generate(db, row, [products[i] for i in ids if i in products], drop, minutes, note)
