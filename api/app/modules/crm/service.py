"""Nghiệp vụ chăm khách (h4–h8).

Ranh giới dữ liệu: `customers`, `customer_identities`, `orders` thuộc module orders; `products`, `drops`, `categories`
thuộc catalog; `candidates` thuộc sourcing; `trial_notes` thuộc selection — ở đây chỉ ĐỌC. Mọi thứ crm ghi nằm trong
bảng của crm (ghi chú, nhãn, tin gửi, nhắc mua lại, mã giới thiệu, lời mời thử hàng) và `app_settings` (qua control).
- «Khách quen» tính theo số đơn ≥ ngưỡng chị đặt (`crm.regular_min_orders`), cờ `customers.is_regular` hoặc nhãn
  `khach-quen`.
- «Từ chối nhận tin» là nhãn `tu-choi-nhan-tin` (không gửi tin báo đợt, nhắc mua lại, mời thử hàng).
- Chu kỳ dùng của từng món (h6) lưu ở cài đặt `crm.reorder_cycles`; không đặt thì theo `products.reorder_days` /
  `categories.default_reorder_days` của món tiêu hao.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from slugify import slugify
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, control
from app.core import events
from app.core.config import settings
from app.core.enums import Actor, Channel
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.money import format_vnd
from app.core.security import random_token
from app.core.timeutil import local_today, now_utc, to_local
from app.integrations import IntegrationError
from app.integrations import notify as notify_api
from app.integrations.notify import OutboundNotification
from app.modules.catalog.models import Category, Drop, DropItem, Product, ProductStatus
from app.modules.content.models import VoiceProfile
from app.modules.control.models import AIActivity, ApprovalItem, ApprovalStatus, User
from app.modules.crm.ai_tasks import (
    DropAnnouncementIn,
    DropAnnouncementOut,
    DropItemFact,
    GroupDigestIn,
    GroupDigestOut,
    ReorderIn,
    ReorderOut,
    SummarizeCustomerIn,
    SummarizeCustomerOut,
    SummaryOrder,
)
from app.modules.crm.models import (
    Broadcast,
    BroadcastKind,
    BroadcastStatus,
    CustomerNote,
    CustomerTag,
    GroupDigest,
    NoteKind,
    NoteSource,
    Referral,
    ReferralUse,
    ReferralUseStatus,
    ReminderStatus,
    ReorderReminder,
    TesterInvite,
    TesterInviteStatus,
)
from app.modules.inbox.models import Direction, Message, Thread, ThreadKind
from app.modules.inbox.textsearch import digits, email_local, like_pattern, sql_fold
from app.modules.orders.models import Customer, CustomerIdentity, Order, OrderItem, OrderStatus
from app.modules.selection.models import NoteAuthor, TrialNote
from app.modules.sourcing.models import Candidate, CandidateStage

log = logging.getLogger("app.crm")

OPT_OUT_TAG = "tu-choi-nhan-tin"
REGULAR_TAG = "khach-quen"
REGULAR_MIN_KEY = "crm.regular_min_orders"
REORDER_CYCLES_KEY = "crm.reorder_cycles"
REFERRAL_REWARD_KEY = "crm.referral_reward_vnd"
ACTION_REFERRAL_REWARD = "crm.reward_referral"

ACTION_PROFILE = "crm.update_profile"
ACTION_BROADCAST = "crm.send_broadcast"
ACTION_REORDER = "crm.send_reorder_reminder"

DEAD_ORDER = (OrderStatus.CANCELLED, OrderStatus.DRAFT)


# ---- tiện ích ----------------------------------------------------------------------------------------------------


async def get_customer(db: AsyncSession, customer_id: uuid.UUID) -> Customer:
    c = await db.get(Customer, customer_id)
    if c is None:
        raise NotFound("Không tìm thấy khách.")
    return c


async def regular_min_orders(db: AsyncSession) -> int:
    return max(1, int(await control.get_setting(db, REGULAR_MIN_KEY) or 2))


def _regular_cond(min_orders: int) -> Any:
    return or_(
        Customer.is_regular.is_(True),
        Customer.order_count >= min_orders,
        exists().where(CustomerTag.customer_id == Customer.id, CustomerTag.tag == REGULAR_TAG),
    )


def _opted_out_cond() -> Any:
    return exists().where(CustomerTag.customer_id == Customer.id, CustomerTag.tag == OPT_OUT_TAG)


async def tags_of(db: AsyncSession, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    out: dict[uuid.UUID, list[str]] = {i: [] for i in customer_ids}
    if customer_ids:
        rows = await db.execute(
            select(CustomerTag.customer_id, CustomerTag.tag)
            .where(CustomerTag.customer_id.in_(customer_ids))
            .order_by(CustomerTag.created_at)
        )
        for cid, tag in rows.all():
            out[cid].append(tag)
    return out


async def is_opted_out(db: AsyncSession, customer_id: uuid.UUID) -> bool:
    return bool(
        await db.scalar(
            select(CustomerTag.id).where(CustomerTag.customer_id == customer_id, CustomerTag.tag == OPT_OUT_TAG)
        )
    )


async def voice(db: AsyncSession) -> dict[str, Any]:
    v = (
        await db.execute(
            select(VoiceProfile).where(VoiceProfile.is_active.is_(True)).order_by(VoiceProfile.updated_at.desc())
        )
    ).scalar_one_or_none()
    return {"style_summary": v.style_summary, "rules": v.rules[:10]} if v else {}


async def recipient(db: AsyncSession, customer: Customer) -> tuple[Channel, str] | None:
    """Kênh nhắn riêng cho khách: Zalo OA (định danh / hội thoại) → email → SMS."""
    zalo = await db.scalar(
        select(CustomerIdentity.external_id).where(
            CustomerIdentity.customer_id == customer.id, CustomerIdentity.channel == Channel.ZALO_OA
        )
    ) or await db.scalar(
        select(Thread.participant_external_id).where(
            Thread.customer_id == customer.id,
            Thread.channel == Channel.ZALO_OA,
            Thread.kind == ThreadKind.DIRECT_MESSAGE,
            Thread.participant_external_id.is_not(None),
        )
    )
    if zalo:
        return Channel.ZALO_OA, zalo
    if customer.email:
        return Channel.EMAIL, customer.email
    if customer.phone:
        return Channel.SMS, customer.phone
    return None


async def can_market_to(db: AsyncSession, customer: Customer) -> bool:
    """Tin quảng cáo / chăm sóc (báo đợt, nhắc mua lại): chỉ khách đã đồng ý nhận (`marketing_opt_in`, ô đánh dấu
    khi đặt hàng) và chưa từ chối (nhãn `tu-choi-nhan-tin`), không bị chặn. Tin giao dịch (mốc đơn) không cần."""
    return bool(customer.marketing_opt_in) and not customer.is_blocked and not await is_opted_out(db, customer.id)


OPT_OUT_FOOTER = "Không muốn nhận tin như này nữa, bạn nhắn «TỪ CHỐI» cho mình nhé."
OPT_OUT_REPLIES = {"tu choi", "tu choi nhan tin", "huy nhan tin", "dung nhan tin", "khong nhan tin", "stop"}


def is_opt_out_reply(text: str) -> bool:
    return slugify(text or "", separator=" ") in OPT_OUT_REPLIES


async def notify(
    db: AsyncSession,
    customer: Customer,
    text: str,
    *,
    link: str | None = None,
    subject: str | None = None,
    kind: str | None = None,
    promotional: bool = False,
    data: dict[str, Any] | None = None,
) -> str:
    """Gửi tin riêng qua tích hợp notify. Trả mã tin; lỗi thì raise IntegrationError (câu tiếng Việt).
    `promotional=True`: kiểm sự đồng ý và thêm câu hướng dẫn từ chối nhận tin."""
    if promotional and not await can_market_to(db, customer):
        raise BadRequest(
            f"{customer.name or 'Khách'} chưa đồng ý nhận tin quảng cáo hoặc đã từ chối.", code="no_consent"
        )
    to = await recipient(db, customer)
    if to is None:
        raise BadRequest(f"{customer.name or 'Khách'} chưa có kênh nhận tin (Zalo, email hay số điện thoại).")
    if promotional and OPT_OUT_FOOTER not in text:
        text = f"{text}\n{OPT_OUT_FOOTER}"
    values = {"ten": customer.name or "bạn", "noi_dung": text, "link": link or "", "phone": customer.phone or ""}
    res = await notify_api.send(
        OutboundNotification(
            channel=to[0], to=to[1], text=text, link_url=link, subject=subject, kind=kind, promotional=promotional,
            data={**values, **(data or {})},
        )
    )  # fmt: skip
    if res.status == "failed":
        raise IntegrationError(f"Gửi cho {customer.name or 'khách'} không được: {res.error or 'lỗi không rõ'}")
    return res.external_id or ""


def store_link(path: str) -> str:
    return f"{settings.web_base_url.rstrip('/')}{path}"


# ---- h4: sổ khách ------------------------------------------------------------------------------------------------


def _customer_search(q: str) -> Any:
    pat = like_pattern(q)
    local = like_pattern(q.split("@", 1)[0]) if "@" in q else pat
    conds = [
        sql_fold(Customer.name).like(pat),
        sql_fold(email_local(Customer.email)).like(local),
        exists().where(CustomerTag.customer_id == Customer.id, sql_fold(CustomerTag.tag).like(pat)),
        exists().where(CustomerIdentity.customer_id == Customer.id, sql_fold(CustomerIdentity.display_name).like(pat)),
        exists().where(CustomerNote.customer_id == Customer.id, sql_fold(CustomerNote.body).like(pat)),
    ]
    d = digits(q)
    if len(d) >= 3:
        conds.append(Customer.phone.like(f"%{d}%"))
    return or_(*conds)


async def customers_query(db: AsyncSession, *, q: str | None, segment: str, tag: str | None) -> Any:
    stmt = select(Customer).where(Customer.merged_into_id.is_(None))
    if segment == "regular":
        stmt = stmt.where(_regular_cond(await regular_min_orders(db)))
    elif segment == "optout":
        stmt = stmt.where(_opted_out_cond())
    elif segment == "new":
        stmt = stmt.where(Customer.order_count == 0)
    if tag:
        stmt = stmt.where(exists().where(CustomerTag.customer_id == Customer.id, CustomerTag.tag == tag))
    if q and q.strip():
        stmt = stmt.where(_customer_search(q.strip()))
    return stmt.order_by(Customer.last_order_at.desc().nulls_last(), Customer.created_at.desc())


async def ai_summaries(db: AsyncSession, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, CustomerNote]:
    if not customer_ids:
        return {}
    rows = (
        await db.execute(
            select(CustomerNote).where(
                CustomerNote.customer_id.in_(customer_ids), CustomerNote.kind == NoteKind.AI_SUMMARY
            )
        )
    ).scalars()
    return {n.customer_id: n for n in rows}


async def channels_of(db: AsyncSession, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    out: dict[uuid.UUID, set[str]] = {i: set() for i in customer_ids}
    if customer_ids:
        for cid, ch in (
            await db.execute(
                select(CustomerIdentity.customer_id, CustomerIdentity.channel).where(
                    CustomerIdentity.customer_id.in_(customer_ids)
                )
            )
        ).all():
            out[cid].add(str(ch))
        for cid, ch in (
            await db.execute(
                select(Thread.customer_id, Thread.channel).where(Thread.customer_id.in_(customer_ids)).distinct()
            )
        ).all():
            out[cid].add(str(ch))
    return {k: sorted(v) for k, v in out.items()}


async def add_note(
    db: AsyncSession, customer_id: uuid.UUID, body: str, kind: NoteKind, user: User | None, *, pinned: bool = False
) -> CustomerNote:
    await get_customer(db, customer_id)
    if kind == NoteKind.AI_SUMMARY:
        raise BadRequest("Tóm tắt do AI viết, chị ghi chú loại khác nhé.")
    n = CustomerNote(
        customer_id=customer_id,
        kind=kind,
        source=NoteSource.OWNER,
        body=body.strip(),
        pinned=pinned,
        created_by_id=user.id if user else None,
    )
    db.add(n)
    await db.flush()
    return n


async def add_tag(db: AsyncSession, customer_id: uuid.UUID, tag: str, *, source: NoteSource = NoteSource.OWNER) -> str:
    await get_customer(db, customer_id)
    t = slugify(tag, max_length=60) or tag.strip().lower()[:60]
    if not t:
        raise BadRequest("Nhãn đang trống.")
    if not await db.scalar(select(CustomerTag.id).where(CustomerTag.customer_id == customer_id, CustomerTag.tag == t)):
        db.add(CustomerTag(customer_id=customer_id, tag=t, source=source))
        await db.flush()
    return t


async def remove_tag(db: AsyncSession, customer_id: uuid.UUID, tag: str) -> None:
    row = (
        await db.execute(select(CustomerTag).where(CustomerTag.customer_id == customer_id, CustomerTag.tag == tag))
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("Khách không có nhãn này.")
    await db.delete(row)
    await db.flush()


async def set_opt_out(db: AsyncSession, customer_id: uuid.UUID, opt_out: bool, user: User | None) -> None:
    if opt_out:
        await add_tag(db, customer_id, OPT_OUT_TAG)
        # huỷ mọi tin sắp gửi cho khách này
        for r in (
            await db.execute(
                select(ReorderReminder).where(
                    ReorderReminder.customer_id == customer_id,
                    ReorderReminder.status.in_([ReminderStatus.SCHEDULED, ReminderStatus.PENDING_REVIEW]),
                )
            )
        ).scalars():
            r.status = ReminderStatus.SKIPPED
            r.reason = "Khách từ chối nhận tin"
            await control.cancel_pending(db, action=ACTION_REORDER, dedupe_key=f"reminder:{r.id}")
    else:
        row = (
            await db.execute(
                select(CustomerTag).where(CustomerTag.customer_id == customer_id, CustomerTag.tag == OPT_OUT_TAG)
            )
        ).scalar_one_or_none()
        if row:
            await db.delete(row)
    await control.audit(
        db, "crm.opt_out" if opt_out else "crm.opt_in", user=user, entity_type="customers", entity_id=customer_id
    )
    await db.flush()


async def summary_input(db: AsyncSession, customer: Customer) -> SummarizeCustomerIn:
    orders = list(
        (
            await db.execute(
                select(Order)
                .where(Order.customer_id == customer.id, Order.status.not_in(DEAD_ORDER))
                .order_by(Order.placed_at.desc())
                .limit(10)
            )
        ).scalars()
    )
    questions = list(
        (
            await db.execute(
                select(Message.body)
                .join(Thread, Thread.id == Message.thread_id)
                .where(Thread.customer_id == customer.id, Message.direction == Direction.INBOUND)
                .order_by(Message.sent_at.desc())
                .limit(20)
            )
        ).scalars()
    )
    notes = list(
        (
            await db.execute(
                select(CustomerNote.body)
                .where(CustomerNote.customer_id == customer.id, CustomerNote.source == NoteSource.OWNER)
                .order_by(CustomerNote.created_at.desc())
                .limit(10)
            )
        ).scalars()
    )
    tags = (await tags_of(db, [customer.id]))[customer.id]
    return SummarizeCustomerIn(
        name=customer.name,
        orders=[
            SummaryOrder(
                date=to_local(o.placed_at).date().isoformat(),
                items=[f"{i.name} × {i.quantity}" for i in o.items],
                total_vnd=o.total_vnd,
                status=str(o.status),
            )
            for o in orders
        ],
        questions=[q[:300] for q in questions],
        owner_notes=notes,
        tags=tags,
    )


async def refresh_profile(db: AsyncSession, customer_id: uuid.UUID) -> control.ProposeOutcome | None:
    """AI tóm tắt lại sổ khách (đi qua control: việc nội bộ, mặc định AI tự làm, hoàn tác được)."""
    customer = await db.get(Customer, customer_id)
    if customer is None:
        return None
    inp = await summary_input(db, customer)
    if not inp.orders and not inp.questions:
        return None
    try:
        res = await ai.run("crm.summarize_customer", inp, SummarizeCustomerOut)
    except ai.AIError as e:
        log.warning("Không tóm tắt được sổ khách %s: %s", customer_id, e)
        return None
    return await control.propose(
        ACTION_PROFILE,
        f"Cập nhật sổ khách: {customer.name or customer.phone}",
        {"customer_id": str(customer.id), "summary": res.output.summary, "interests": res.output.interests},
        {"summary": res.output.summary, "interests": res.output.interests},
        db=db,
        ref_type="customers",
        ref_id=customer.id,
        ai_run_id=res.run_id,
        dedupe_key=f"profile:{customer.id}",
    )


async def apply_profile(
    db: AsyncSession, customer_id: uuid.UUID, summary: str, interests: list[str], run_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Ghi tóm tắt AI vào sổ khách; trả dữ liệu cũ để hoàn tác."""
    note = (
        await db.execute(
            select(CustomerNote).where(
                CustomerNote.customer_id == customer_id, CustomerNote.kind == NoteKind.AI_SUMMARY
            )
        )
    ).scalar_one_or_none()
    old_ints = list(
        (
            await db.execute(
                select(CustomerNote).where(
                    CustomerNote.customer_id == customer_id,
                    CustomerNote.kind == NoteKind.INTEREST,
                    CustomerNote.source == NoteSource.AI,
                )
            )
        ).scalars()
    )
    undo = {"summary": note.body if note else None, "interests": [n.body for n in old_ints]}
    if note is None:
        note = CustomerNote(customer_id=customer_id, kind=NoteKind.AI_SUMMARY, source=NoteSource.AI, body=summary)
        db.add(note)
    note.body = summary
    note.ref_type = "ai_runs" if run_id else None
    note.ref_id = run_id
    for n in old_ints:
        await db.delete(n)
    for text in interests[:5]:
        db.add(CustomerNote(customer_id=customer_id, kind=NoteKind.INTEREST, source=NoteSource.AI, body=text[:300]))
    await db.flush()
    return undo


# ---- h5: khách quen, tin báo đợt, tóm tắt nhóm --------------------------------------------------------------------


async def regulars(db: AsyncSession) -> list[Customer]:
    return list(
        (
            await db.execute(
                select(Customer)
                .where(Customer.merged_into_id.is_(None), _regular_cond(await regular_min_orders(db)))
                .order_by(Customer.order_count.desc(), Customer.last_order_at.desc().nulls_last())
            )
        ).scalars()
    )


async def audience(db: AsyncSession) -> list[Customer]:
    """Khách quen nhận tin (tin quảng cáo): chỉ người đã đồng ý nhận, bỏ người từ chối nhận tin và người bị chặn."""
    out = []
    for c in await regulars(db):
        if not await can_market_to(db, c):
            continue
        out.append(c)
    return out


UNSENT = (BroadcastStatus.DRAFT, BroadcastStatus.PENDING_REVIEW, BroadcastStatus.APPROVED, BroadcastStatus.SCHEDULED,
          BroadcastStatus.FAILED)  # fmt: skip


async def reachable_count(db: AsyncSession) -> int:
    """Số khách quen nhận được tin lúc này (có kênh nhận). Tin chưa gửi luôn hiện con số này, không phải số lúc soạn."""
    return len([c for c in await audience(db) if await recipient(db, c)])


async def draft_drop_announcement(db: AsyncSession, drop_id: uuid.UUID) -> Broadcast | None:
    """AI soạn tin báo đợt mới cho khách quen (nghe `drop.opened`). Mỗi đợt một tin — chạy lại không soạn trùng."""
    existing = (
        await db.execute(
            select(Broadcast).where(Broadcast.drop_id == drop_id, Broadcast.kind == BroadcastKind.DROP_ANNOUNCEMENT)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    drop = await db.get(Drop, drop_id)
    if drop is None:
        return None
    rows = (
        await db.execute(
            select(DropItem, Product)
            .join(Product, Product.id == DropItem.product_id)
            .where(DropItem.drop_id == drop.id)
            .order_by(DropItem.position)
        )
    ).all()
    people = await audience(db)
    inp = DropAnnouncementIn(
        drop_title=drop.title,
        closes_at=to_local(drop.closes_at).date().isoformat() if drop.closes_at else None,
        expected_arrival=drop.expected_arrival_date.isoformat() if drop.expected_arrival_date else None,
        items=[
            DropItemFact(
                name=p.name,
                price_vnd=di.price_vnd or p.price_vnd,
                slots_left=(di.slots_total - di.slots_reserved) if di.slots_total is not None else None,
                reason_selected=p.reason_selected,
            )
            for di, p in rows
        ],
        link=store_link(f"/dot/{drop.slug}"),
        audience_size=len(people),
        voice=await voice(db),
    )
    res = await ai.run("crm.draft_drop_announcement", inp, DropAnnouncementOut)
    b = Broadcast(
        kind=BroadcastKind.DROP_ANNOUNCEMENT,
        channel=Channel.ZALO_OA,
        drop_id=drop.id,
        title=res.output.title[:200],
        body=res.output.body,
        audience={"segment": "regulars", "min_orders": await regular_min_orders(db)},
        status=BroadcastStatus.PENDING_REVIEW,
        recipient_count=len(people),
        ai_generated=True,
        ai_run_id=res.run_id,
    )
    db.add(b)
    await db.flush()
    await propose_broadcast(db, b, run_id=res.run_id)
    return b


async def propose_broadcast(db: AsyncSession, b: Broadcast, *, run_id: uuid.UUID | None = None) -> None:
    out = await control.propose(
        ACTION_BROADCAST,
        b.title,
        {"broadcast_id": str(b.id), "body": b.body},
        {"body": b.body, "recipient_count": b.recipient_count, "href": "/desk/khach/khach-quen"},
        db=db,
        summary="Gửi tin cho khách quen",  # số người nhận tính lại lúc xem / gửi, không ghi cứng vào hàng chờ
        ref_type="broadcasts",
        ref_id=b.id,
        ai_run_id=run_id,
        dedupe_key=f"broadcast:{b.id}",
        ai_generated=b.ai_generated,
    )
    if out.status == "pending":
        b.approval_item_id = out.item_id
    elif out.status == "blocked":
        b.status = BroadcastStatus.DRAFT
    await db.flush()


async def create_broadcast(db: AsyncSession, title: str, body: str) -> Broadcast:
    """Chị tự viết tin cho khách quen: vẫn qua hàng chờ để có bước xem lại trước khi gửi hàng loạt."""
    people = await audience(db)
    b = Broadcast(
        kind=BroadcastKind.GENERAL,
        channel=Channel.ZALO_OA,
        title=title.strip()[:200],
        body=body.strip(),
        audience={"segment": "regulars", "min_orders": await regular_min_orders(db)},
        status=BroadcastStatus.PENDING_REVIEW,
        recipient_count=len(people),
    )
    db.add(b)
    await db.flush()
    await propose_broadcast(db, b)
    return b


async def send_broadcast(db: AsyncSession, broadcast_id: uuid.UUID, body: str | None) -> Broadcast:
    b = await db.get(Broadcast, broadcast_id)
    if b is None:
        raise NotFound("Không tìm thấy tin.")
    if b.status in (BroadcastStatus.SENT, BroadcastStatus.SENDING, BroadcastStatus.CANCELLED):
        raise Conflict("Tin này đã gửi hoặc đã huỷ.", code="broadcast_done")
    if body:
        b.body = body.strip()
    people = await audience(db)
    b.status = BroadcastStatus.SENDING
    b.recipient_count = len(people)
    delivered, failed = 0, []
    drop = await db.get(Drop, b.drop_id) if b.drop_id else None
    link = store_link(f"/dot/{drop.slug}") if drop else None
    for c in people:
        try:
            await notify(db, c, b.body, link=link, subject=b.title, kind="broadcast", promotional=True)
            delivered += 1
        except (IntegrationError, BadRequest) as e:
            failed.append(f"{c.name}: {e.message}")
    b.delivered_count = delivered
    b.sent_at = now_utc()
    b.status = BroadcastStatus.FAILED if people and not delivered else BroadcastStatus.SENT
    await db.flush()
    if failed:
        log.info("Tin %s: %d khách không nhận được: %s", b.id, len(failed), "; ".join(failed[:5]))
    return b


async def send_broadcast_now(db: AsyncSession, broadcast_id: uuid.UUID, body: str | None, user: User) -> Broadcast:
    b = await db.get(Broadcast, broadcast_id)
    if b is None:
        raise NotFound("Không tìm thấy tin.")
    item = await db.get(ApprovalItem, b.approval_item_id) if b.approval_item_id else None
    if item and item.status in (ApprovalStatus.PENDING, ApprovalStatus.FAILED):
        item = await control.approve(db, item.id, user, edited_payload={"body": body or b.body})
        if item.status == ApprovalStatus.FAILED:
            raise BadRequest(item.error or "Chưa gửi được.", code="send_failed")
    else:
        await send_broadcast(db, b.id, body)
        await control.audit(db, "crm.broadcast_sent", user=user, entity_type="broadcasts", entity_id=b.id)
    await db.refresh(b)
    return b


async def cancel_broadcast(db: AsyncSession, broadcast_id: uuid.UUID, user: User) -> Broadcast:
    b = await db.get(Broadcast, broadcast_id)
    if b is None:
        raise NotFound("Không tìm thấy tin.")
    if b.status in (BroadcastStatus.SENT, BroadcastStatus.SENDING):
        raise Conflict("Tin đã gửi, không huỷ được.")
    b.status = BroadcastStatus.CANCELLED
    await control.cancel_pending(db, action=ACTION_BROADCAST, dedupe_key=f"broadcast:{b.id}")
    await control.audit(db, "crm.broadcast_cancelled", user=user, entity_type="broadcasts", entity_id=b.id)
    await db.flush()
    return b


async def create_digest(
    db: AsyncSession, text: str, *, period_start: datetime | None, period_end: datetime | None
) -> GroupDigest:
    """Chị dán nội dung nhóm Zalo → AI tóm tắt. Chỉ chị xem, không gửi ai."""
    names = list(
        (await db.execute(select(Product.name).where(Product.status == ProductStatus.PUBLISHED).limit(80))).scalars()
    )
    res = await ai.run("crm.digest_group", GroupDigestIn(text=text[:20000], products=names), GroupDigestOut)
    now = now_utc()
    d = GroupDigest(
        period_start=period_start or now,
        period_end=period_end or now,
        summary=res.output.summary,
        highlights=res.output.highlights,
        open_questions=res.output.open_questions,
        product_mentions=[m.model_dump() for m in res.output.product_mentions],
        ai_run_id=res.run_id,
    )
    db.add(d)
    await db.flush()
    return d


# ---- h6: nhắc mua lại --------------------------------------------------------------------------------------------


async def reorder_cycles(db: AsyncSession) -> dict[str, dict[str, Any]]:
    return dict(await control.get_setting(db, REORDER_CYCLES_KEY) or {})


async def cycle_for(db: AsyncSession, product: Product, cycles: dict[str, dict[str, Any]] | None = None) -> int | None:
    cycles = cycles if cycles is not None else await reorder_cycles(db)
    rule = cycles.get(str(product.id))
    if rule is not None:
        return int(rule["days"]) if rule.get("active", True) and rule.get("days") else None
    if product.is_consumable and product.reorder_days:
        return product.reorder_days
    if product.category_id:
        cat = await db.get(Category, product.category_id)
        if cat and cat.is_consumable and cat.default_reorder_days:
            return cat.default_reorder_days
    return None


async def set_cycle(db: AsyncSession, product_id: uuid.UUID, days: int | None, active: bool, user: User) -> None:
    if await db.get(Product, product_id) is None:
        raise NotFound("Không tìm thấy sản phẩm.")
    cycles = await reorder_cycles(db)
    if days is None and active:
        cycles.pop(str(product_id), None)  # về mặc định theo sản phẩm / nhóm hàng
    else:
        cycles[str(product_id)] = {"days": days, "active": active}
    await control.set_setting(db, REORDER_CYCLES_KEY, cycles, user)


def lead_days(cycle: int) -> int:
    """Nhắc trước khi hết vài ngày."""
    return max(1, min(5, cycle // 6))


async def schedule_reminders(db: AsyncSession, order_id: uuid.UUID) -> list[ReorderReminder]:
    """Nghe `order.delivered`: mỗi dòng hàng tiêu hao một lịch nhắc (duy nhất theo dòng hàng — idempotent)."""
    order = await db.get(Order, order_id)
    if order is None or order.customer_id is None:
        return []
    customer = await _resolve(db, order.customer_id)
    delivered = to_local(order.delivered_at or now_utc()).date()
    cycles = await reorder_cycles(db)
    made = []
    for it in order.items:
        if not it.product_id:
            continue
        if await db.scalar(select(ReorderReminder.id).where(ReorderReminder.order_item_id == it.id)):
            continue
        p = await db.get(Product, it.product_id)
        cycle = await cycle_for(db, p, cycles) if p else None
        if not cycle:
            continue
        days = cycle * max(1, it.quantity)
        r = ReorderReminder(
            customer_id=customer,
            product_id=it.product_id,
            order_id=order.id,
            order_item_id=it.id,
            due_on=delivered + timedelta(days=days - lead_days(cycle)),
            reason=(
                f"Nhận {it.quantity} {p.name} ngày {delivered:%d/%m}, mỗi cái dùng khoảng {cycle} ngày"
                if it.quantity > 1
                else f"Nhận {p.name} ngày {delivered:%d/%m}, dùng khoảng {cycle} ngày"
            ),
        )
        db.add(r)
        made.append(r)
    await db.flush()
    return made


async def _resolve(db: AsyncSession, customer_id: uuid.UUID) -> uuid.UUID:
    seen: set[uuid.UUID] = set()
    cid = customer_id
    while cid not in seen:
        seen.add(cid)
        c = await db.get(Customer, cid)
        if c is None or not c.merged_into_id:
            return cid
        cid = c.merged_into_id
    return cid


async def mark_rebought(db: AsyncSession, order_id: uuid.UUID) -> int:
    """Nghe `order.created`: khách đã mua lại món → nhắc đã gửi thành «converted», nhắc chưa gửi thì bỏ."""
    order = await db.get(Order, order_id)
    if order is None or order.customer_id is None or order.status in DEAD_ORDER:
        return 0
    customer = await _resolve(db, order.customer_id)
    pids = [i.product_id for i in order.items if i.product_id]
    if not pids:
        return 0
    rows = (
        await db.execute(
            select(ReorderReminder).where(
                ReorderReminder.customer_id == customer,
                ReorderReminder.product_id.in_(pids),
                ReorderReminder.order_id != order.id,
                ReorderReminder.status.in_(
                    [ReminderStatus.SCHEDULED, ReminderStatus.PENDING_REVIEW, ReminderStatus.SENT]
                ),
            )
        )
    ).scalars()
    n = 0
    for r in rows:
        if r.status == ReminderStatus.SENT:
            r.status = ReminderStatus.CONVERTED
            r.converted_order_id = order.id
        else:
            r.status = ReminderStatus.SKIPPED
            r.reason = (r.reason or "") + " · Khách đã mua lại trước khi nhắc"
            await control.cancel_pending(db, action=ACTION_REORDER, dedupe_key=f"reminder:{r.id}")
        n += 1
    await db.flush()
    return n


async def run_due(db: AsyncSession, today: date | None = None) -> dict[str, int]:
    """Tới hạn: AI soạn tin nhắc riêng từng khách → control (mặc định hỏi chị). Không nhắc quá một lần mỗi chu kỳ."""
    today = today or local_today()
    due = list(
        (
            await db.execute(
                select(ReorderReminder)
                .where(ReorderReminder.status == ReminderStatus.SCHEDULED, ReorderReminder.due_on <= today)
                .order_by(ReorderReminder.due_on)
            )
        ).scalars()
    )
    stats = {"drafted": 0, "skipped": 0}
    cycles = await reorder_cycles(db)
    for r in due:
        customer = await db.get(Customer, r.customer_id)
        product = await db.get(Product, r.product_id)
        if customer is None or product is None:
            r.status = ReminderStatus.CANCELLED
            continue
        cycle = await cycle_for(db, product, cycles) or 30
        skip = None
        if await is_opted_out(db, customer.id) or customer.is_blocked:
            skip = "Khách từ chối nhận tin"
        elif not customer.marketing_opt_in:
            skip = "Khách chưa đồng ý nhận tin nhắc"
        elif await db.scalar(
            select(ReorderReminder.id).where(
                ReorderReminder.customer_id == customer.id,
                ReorderReminder.product_id == product.id,
                ReorderReminder.id != r.id,
                or_(
                    ReorderReminder.status == ReminderStatus.PENDING_REVIEW,
                    and_(
                        ReorderReminder.status.in_([ReminderStatus.SENT, ReminderStatus.CONVERTED]),
                        ReorderReminder.sent_at >= now_utc() - timedelta(days=cycle),
                    ),
                ),
            )
        ):
            skip = "Đã nhắc món này trong chu kỳ"
        elif await recipient(db, customer) is None:
            skip = "Khách chưa có kênh nhận tin"
        if skip:
            r.status = ReminderStatus.SKIPPED
            r.reason = f"{r.reason or ''} · {skip}".strip(" ·")
            stats["skipped"] += 1
            await db.flush()
            continue
        order = await db.get(Order, r.order_id) if r.order_id else None
        item = await db.get(OrderItem, r.order_item_id) if r.order_item_id else None
        inp = ReorderIn(
            customer_name=customer.name,
            product_name=product.name,
            bought_on=to_local(order.delivered_at or order.placed_at).date().isoformat()
            if order
            else today.isoformat(),
            quantity=item.quantity if item else 1,
            cycle_days=cycle,
            price_vnd=product.price_vnd or None,
            product_link=store_link(f"/san-pham/{product.slug}") if product.status == ProductStatus.PUBLISHED else None,
            voice=await voice(db),
        )
        try:
            res = await ai.run("crm.draft_reorder", inp, ReorderOut)
        except ai.AIError as e:
            log.warning("Không soạn được tin nhắc %s: %s", r.id, e)
            continue
        to = await recipient(db, customer)
        r.message_body = res.output.body
        r.channel = to[0] if to else None
        r.ai_run_id = res.run_id
        r.status = ReminderStatus.PENDING_REVIEW
        await db.flush()
        out = await control.propose(
            ACTION_REORDER,
            f"Nhắc {customer.name or 'khách'} mua lại {product.name}",
            {"reminder_id": str(r.id), "body": r.message_body},
            {"customer": customer.name, "product": product.name, "body": r.message_body, "reason": r.reason,
             "href": "/desk/khach/nhac-mua-lai"},
            db=db,
            summary=r.reason,
            rationale=r.reason,
            ref_type="reorder_reminders",
            ref_id=r.id,
            ai_run_id=res.run_id,
            dedupe_key=f"reminder:{r.id}",
        )  # fmt: skip
        if out.status == "pending":
            r.approval_item_id = out.item_id
        elif out.status == "blocked":
            r.status = ReminderStatus.SCHEDULED
        stats["drafted"] += 1
    await db.flush()
    return stats


async def send_reminder(db: AsyncSession, reminder_id: uuid.UUID, body: str | None) -> ReorderReminder:
    r = await db.get(ReorderReminder, reminder_id)
    if r is None:
        raise NotFound("Không tìm thấy nhắc mua lại.")
    if r.status not in (ReminderStatus.PENDING_REVIEW, ReminderStatus.SCHEDULED):
        raise Conflict("Nhắc này đã xử lý rồi.", code="reminder_done")
    customer = await get_customer(db, r.customer_id)
    if await is_opted_out(db, customer.id):
        raise BadRequest("Khách đã từ chối nhận tin.", code="opted_out")
    text = (body or r.message_body or "").strip()
    if not text:
        raise BadRequest("Tin nhắc đang trống.")
    product = await db.get(Product, r.product_id)
    link = store_link(f"/san-pham/{product.slug}") if product else None
    await notify(
        db, customer, text, link=link, kind="reorder_reminder", promotional=True,
        data={"mon": product.name if product else ""},
    )  # fmt: skip
    r.message_body = text
    r.status = ReminderStatus.SENT
    r.sent_at = now_utc()
    await db.flush()
    return r


async def send_reminder_now(db: AsyncSession, reminder_id: uuid.UUID, body: str | None, user: User) -> ReorderReminder:
    r = await db.get(ReorderReminder, reminder_id)
    if r is None:
        raise NotFound("Không tìm thấy nhắc mua lại.")
    item = await db.get(ApprovalItem, r.approval_item_id) if r.approval_item_id else None
    if item and item.status in (ApprovalStatus.PENDING, ApprovalStatus.FAILED):
        item = await control.approve(db, item.id, user, edited_payload={"body": body or r.message_body})
        if item.status == ApprovalStatus.FAILED:
            raise BadRequest(item.error or "Chưa gửi được.", code="send_failed")
    else:
        await send_reminder(db, r.id, body)
        await control.audit(db, "crm.reminder_sent", user=user, entity_type="reorder_reminders", entity_id=r.id)
    await db.refresh(r)
    return r


async def skip_reminder(db: AsyncSession, reminder_id: uuid.UUID, user: User) -> ReorderReminder:
    r = await db.get(ReorderReminder, reminder_id)
    if r is None:
        raise NotFound("Không tìm thấy nhắc mua lại.")
    if r.status not in (ReminderStatus.SCHEDULED, ReminderStatus.PENDING_REVIEW):
        raise Conflict("Nhắc này đã xử lý rồi.", code="reminder_done")
    r.status = ReminderStatus.SKIPPED
    r.reason = f"{r.reason or ''} · Chị bỏ qua".strip(" ·")
    await control.cancel_pending(db, action=ACTION_REORDER, dedupe_key=f"reminder:{r.id}")
    await control.audit(db, "crm.reminder_skipped", user=user, entity_type="reorder_reminders", entity_id=r.id)
    await db.flush()
    return r


# ---- h7: giới thiệu bạn ------------------------------------------------------------------------------------------

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


async def get_or_create_referral(db: AsyncSession, customer_id: uuid.UUID) -> Referral:
    c = await get_customer(db, customer_id)
    ref = (await db.execute(select(Referral).where(Referral.referrer_customer_id == c.id))).scalar_one_or_none()
    if ref:
        return ref
    base = slugify((c.name or "ban").split()[-1], separator="").upper()[:6] or "BAN"
    for _ in range(20):
        code = f"{base}-{''.join(secrets.choice(_ALPHABET) for _ in range(4))}"
        if not await db.scalar(select(Referral.id).where(func.upper(Referral.code) == code)):
            break
    reward = int(await control.get_setting(db, REFERRAL_REWARD_KEY) or 0)
    ref = Referral(code=code, referrer_customer_id=c.id, reward_referrer_vnd=reward, reward_referred_vnd=reward)
    db.add(ref)
    await db.flush()
    return ref


async def _first_order(db: AsyncSession, order: Order) -> bool:
    earlier = await db.scalar(
        select(func.count()).where(
            Order.customer_id == order.customer_id,
            Order.id != order.id,
            Order.placed_at < order.placed_at,
            Order.status.not_in(DEAD_ORDER),
        )
    )
    return not earlier


async def record_referral(db: AsyncSession, order_id: uuid.UUID) -> ReferralUse | None:
    """Nghe `order.created`: đơn ĐẦU của người được giới thiệu, có mã trên đơn (`orders.referral_code`) → ghi lượt dùng."""
    order = await db.get(Order, order_id)
    if order is None or not order.referral_code or order.customer_id is None or order.status in DEAD_ORDER:
        return None
    ref = (
        await db.execute(select(Referral).where(func.upper(Referral.code) == order.referral_code.strip().upper()))
    ).scalar_one_or_none()
    if ref is None or not ref.is_active or (ref.expires_on and ref.expires_on < local_today()):
        return None
    buyer = await _resolve(db, order.customer_id)
    if buyer == ref.referrer_customer_id:
        return None  # tự giới thiệu chính mình
    existing = (
        await db.execute(select(ReferralUse).where(ReferralUse.referred_customer_id == buyer))
    ).scalar_one_or_none()
    if existing is not None:
        # mỗi người chỉ được giới thiệu một lần; lượt cũ mà đơn đã huỷ (chưa nhận quà) → chuyển sang đơn mới
        old = await db.get(Order, existing.order_id) if existing.order_id else None
        if (
            existing.order_id == order.id
            or existing.status != ReferralUseStatus.PENDING
            or (old is not None and old.status not in DEAD_ORDER)
        ):
            return None
        existing.order_id = order.id
        await db.flush()
        return existing
    if not await _first_order(db, order):
        return None
    use = ReferralUse(referral_id=ref.id, referred_customer_id=buyer, order_id=order.id)
    db.add(use)
    ref.uses_count += 1
    await db.flush()
    return use


async def credit_granted(db: AsyncSession, use_id: uuid.UUID) -> bool:
    """Phần quà của người giới thiệu do AI tặng (dòng Nhật ký AI `crm.reward_referral` chưa hoàn tác).
    Chị ghi quà tay thì không có phần giảm tự áp."""
    return bool(
        await db.scalar(
            select(AIActivity.id).where(
                AIActivity.action == ACTION_REFERRAL_REWARD,
                AIActivity.ref_id == use_id,
                AIActivity.undone_at.is_(None),
            )
        )
    )


async def credit_order(db: AsyncSession, use_id: uuid.UUID) -> Order | None:
    """Đơn còn sống của người giới thiệu đã trừ phần quà (orders ghi `raw.referral_gifts.credit_use_id`)."""
    return (
        await db.execute(
            select(Order)
            .where(
                Order.raw["referral_gifts"]["credit_use_id"].astext == str(use_id),
                Order.status.not_in(DEAD_ORDER),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def manual_referral(
    db: AsyncSession, referral_id: uuid.UUID, customer_id: uuid.UUID, order_id: uuid.UUID | None, user: User
) -> ReferralUse:
    ref = await db.get(Referral, referral_id)
    if ref is None:
        raise NotFound("Không tìm thấy mã giới thiệu.")
    buyer = await _resolve(db, (await get_customer(db, customer_id)).id)
    if buyer == ref.referrer_customer_id:
        raise BadRequest("Khách không tự giới thiệu chính mình được.")
    if await db.scalar(select(ReferralUse.id).where(ReferralUse.referred_customer_id == buyer)):
        raise Conflict("Khách này đã được ghi nhận giới thiệu rồi.", code="already_referred")
    use = ReferralUse(referral_id=ref.id, referred_customer_id=buyer, order_id=order_id)
    db.add(use)
    ref.uses_count += 1
    await control.audit(db, "crm.referral_manual", user=user, entity_type="referrals", entity_id=ref.id,
                        data={"customer_id": str(buyer)})  # fmt: skip
    await db.flush()
    return use


async def qualify_referral(db: AsyncSession, order_id: uuid.UUID) -> int:
    """Nghe `order.delivered`: đơn đầu của người được giới thiệu đã giao → đủ điều kiện nhận quà; đơn đã trả tiền thì
    tặng phần quà cho người giới thiệu (`crm.reward_referral`, mặc định AI tự làm)."""
    rows = list(
        (
            await db.execute(
                select(ReferralUse).where(
                    ReferralUse.order_id == order_id, ReferralUse.status == ReferralUseStatus.PENDING
                )
            )
        ).scalars()
    )
    order = await db.get(Order, order_id)
    n = 0
    for u in rows:
        u.status = ReferralUseStatus.QUALIFIED
        n += 1
    await db.flush()
    if order is not None and order.paid_at is not None:
        for u in rows:
            await propose_reward(db, u, order)
    return n


async def propose_reward(db: AsyncSession, use: ReferralUse, order: Order) -> Any:
    ref = await db.get(Referral, use.referral_id)
    if ref is None or ref.reward_referrer_vnd <= 0:
        return None
    names = dict(
        (
            await db.execute(
                select(Customer.id, Customer.name).where(
                    Customer.id.in_([ref.referrer_customer_id, use.referred_customer_id])
                )
            )
        ).all()
    )
    referrer, friend = names.get(ref.referrer_customer_id) or "Khách", names.get(use.referred_customer_id) or "bạn mới"
    return await control.propose(
        ACTION_REFERRAL_REWARD, f"Quà giới thiệu: {referrer} giới thiệu {friend}",
        {"referral_use_id": str(use.id)},
        {"referrer": referrer, "friend": friend, "code": ref.code, "order_code": order.code,
         "reward_vnd": ref.reward_referrer_vnd},
        db=db, rationale=f"Đơn đầu {order.code} của {friend} đã trả tiền và đã giao.",
        ref_type="referral_uses", ref_id=use.id, dedupe_key=f"referral:{use.id}", ai_generated=False,
    )  # fmt: skip


async def grant_reward(db: AsyncSession, use_id: uuid.UUID) -> control.HandlerResult:
    """Handler của crm.reward_referral: tặng người giới thiệu phần giảm cho đơn kế tiếp (orders tự trừ khi chốt đơn)."""
    use = await db.get(ReferralUse, use_id, with_for_update=True)
    if use is None:
        raise NotFound("Không tìm thấy lượt giới thiệu.")
    if use.status != ReferralUseStatus.QUALIFIED:
        raise Conflict("Lượt này chưa đủ điều kiện hoặc đã tặng quà rồi.", code="not_qualified")
    order = await db.get(Order, use.order_id) if use.order_id else None
    if order is None or order.paid_at is None or order.status in DEAD_ORDER:
        raise Conflict("Đơn đầu của bạn được giới thiệu chưa trả tiền.", code="not_paid")
    ref = await db.get(Referral, use.referral_id)
    if ref is None or use.referred_customer_id == ref.referrer_customer_id:
        raise Conflict("Lượt giới thiệu không hợp lệ.")
    use.status = ReferralUseStatus.REWARDED
    use.rewarded_at = now_utc()
    ref.rewarded_count += 1
    db.add(
        CustomerNote(
            customer_id=ref.referrer_customer_id, kind=NoteKind.NOTE, source=NoteSource.AI,
            body=f"Quà giới thiệu bạn ({ref.code}): giảm {format_vnd(ref.reward_referrer_vnd)}đ cho đơn kế tiếp, tự trừ khi đặt.",
            ref_type="referral_uses", ref_id=use.id,
        )
    )  # fmt: skip
    await db.flush()
    return control.HandlerResult(
        result={"referral_use_id": str(use.id), "credit_vnd": ref.reward_referrer_vnd},
        undo={"referral_use_id": str(use.id)},
        summary=f"Tặng {format_vnd(ref.reward_referrer_vnd)}đ cho đơn kế tiếp của người giới thiệu (mã {ref.code})",
        ref_type="referral_uses", ref_id=use.id,
    )  # fmt: skip


async def revoke_reward(db: AsyncSession, use_id: uuid.UUID) -> None:
    """Hoàn tác tặng quà: chỉ khi người giới thiệu chưa dùng phần giảm."""
    use = await db.get(ReferralUse, use_id, with_for_update=True)
    if use is None:
        raise NotFound("Không tìm thấy lượt giới thiệu.")
    if await credit_order(db, use.id) is not None:
        raise Conflict("Người giới thiệu đã dùng phần quà cho một đơn, không thu hồi được.", code="credit_used")
    if use.status != ReferralUseStatus.REWARDED:
        return
    ref = await db.get(Referral, use.referral_id)
    use.status = ReferralUseStatus.QUALIFIED
    use.rewarded_at = None
    if ref is not None:
        ref.rewarded_count = max(0, ref.rewarded_count - 1)
        db.add(
            CustomerNote(
                customer_id=ref.referrer_customer_id, kind=NoteKind.NOTE, source=NoteSource.OWNER,
                body=f"Thu hồi quà giới thiệu bạn ({ref.code}).", ref_type="referral_uses", ref_id=use.id,
            )
        )  # fmt: skip
    await db.flush()


async def reward_referral(db: AsyncSession, use_id: uuid.UUID, note: str, user: User) -> ReferralUse:
    """Chị xác nhận đã tặng quà cho cả hai (phiếu giảm giá / ghi chú thủ công)."""
    use = await db.get(ReferralUse, use_id)
    if use is None:
        raise NotFound("Không tìm thấy lượt giới thiệu.")
    if use.status == ReferralUseStatus.REWARDED:
        raise Conflict("Lượt này đã tặng quà rồi.", code="already_rewarded")
    if use.status == ReferralUseStatus.VOID:
        raise BadRequest("Lượt này đã huỷ.")
    ref = await db.get(Referral, use.referral_id)
    use.status = ReferralUseStatus.REWARDED
    use.rewarded_at = now_utc()
    ref.rewarded_count += 1
    text = note.strip() or "Đã tặng quà giới thiệu bạn"
    for cid in {ref.referrer_customer_id, use.referred_customer_id}:
        db.add(
            CustomerNote(
                customer_id=cid,
                kind=NoteKind.NOTE,
                source=NoteSource.OWNER,
                body=f"Quà giới thiệu bạn ({ref.code}): {text}",
                ref_type="referral_uses",
                ref_id=use.id,
                created_by_id=user.id,
            )
        )
    await control.audit(db, "crm.referral_rewarded", user=user, entity_type="referral_uses", entity_id=use.id,
                        summary=text)  # fmt: skip
    await db.flush()
    return use


async def void_referral(db: AsyncSession, use_id: uuid.UUID, user: User) -> ReferralUse:
    use = await db.get(ReferralUse, use_id)
    if use is None:
        raise NotFound("Không tìm thấy lượt giới thiệu.")
    if use.status == ReferralUseStatus.REWARDED:
        raise Conflict("Đã tặng quà, không huỷ được.")
    use.status = ReferralUseStatus.VOID
    await control.audit(db, "crm.referral_void", user=user, entity_type="referral_uses", entity_id=use.id)
    await db.flush()
    return use


async def referral_stats(db: AsyncSession) -> dict[str, Any]:
    codes = list((await db.execute(select(func.upper(Referral.code)))).scalars())
    alive = Order.status.not_in(DEAD_ORDER)
    referred = select(ReferralUse.referred_customer_id).where(ReferralUse.status != ReferralUseStatus.VOID)
    from_ref = (  # mọi đơn của người được giới thiệu (đơn đầu + đơn mua lại)
        await db.execute(
            select(func.count(), func.coalesce(func.sum(Order.total_vnd), 0)).where(
                alive, Order.customer_id.in_(referred)
            )
        )
    ).one()
    uses = dict((await db.execute(select(ReferralUse.status, func.count()).group_by(ReferralUse.status))).all())
    per_customer = select(Order.customer_id, func.count().label("n")).where(alive, Order.customer_id.is_not(None))
    per_customer = per_customer.group_by(Order.customer_id).subquery()
    referred_ids = referred
    ref_total = await db.scalar(select(func.count()).select_from(referred_ids.subquery())) or 0
    ref_repeat = (
        await db.scalar(select(func.count()).where(per_customer.c.customer_id.in_(referred_ids), per_customer.c.n >= 2))
        or 0
    )
    all_buyers = await db.scalar(select(func.count()).select_from(per_customer)) or 0
    all_repeat = await db.scalar(select(func.count()).where(per_customer.c.n >= 2)) or 0
    return {
        "codes": len(codes),
        "uses": sum(v for k, v in uses.items() if k != ReferralUseStatus.VOID),
        "pending": uses.get(ReferralUseStatus.PENDING, 0),
        "qualified": uses.get(ReferralUseStatus.QUALIFIED, 0),
        "rewarded": uses.get(ReferralUseStatus.REWARDED, 0),
        "orders_from_referrals": from_ref[0],
        "revenue_from_referrals_vnd": int(from_ref[1]),
        "referred_customers": ref_total,
        "referred_repeat_rate": round(ref_repeat / ref_total, 3) if ref_total else None,
        "overall_repeat_rate": round(all_repeat / all_buyers, 3) if all_buyers else None,
    }


# ---- h8: khách thử hàng ------------------------------------------------------------------------------------------


async def trial_candidates(db: AsyncSession) -> list[Candidate]:
    return list(
        (
            await db.execute(
                select(Candidate)
                .where(Candidate.stage == CandidateStage.TRIAL, Candidate.is_archived.is_(False))
                .order_by(Candidate.board_position, Candidate.stage_changed_at.desc().nulls_last())
            )
        ).scalars()
    )


async def trial_notes(db: AsyncSession, candidate_id: uuid.UUID, limit: int = 10) -> list[TrialNote]:
    """Ghi chú thử của chị (cảm nhận của khách thử hiện riêng ở lời mời)."""
    return list(
        (
            await db.execute(
                select(TrialNote)
                .where(TrialNote.candidate_id == candidate_id, TrialNote.author != NoteAuthor.TESTER)
                .order_by(TrialNote.recorded_at.desc())
                .limit(limit)
            )
        ).scalars()
    )


async def invites_of(db: AsyncSession, candidate_ids: list[uuid.UUID]) -> list[TesterInvite]:
    if not candidate_ids:
        return []
    return list(
        (
            await db.execute(
                select(TesterInvite)
                .where(TesterInvite.candidate_id.in_(candidate_ids))
                .order_by(TesterInvite.created_at)
            )
        ).scalars()
    )


def invite_link(token: str) -> str:
    return store_link(f"/thu-hang/{token}")


DEFAULT_INVITE = (
    "Chào {ten}, mình đang thử {mon} trước khi quyết định có bán không. Bạn dùng thử cùng mình vài ngày rồi kể "
    "thật lòng giúp mình nhé? Mình gửi mẫu tận nơi, không mất phí."
)


async def invite_testers(
    db: AsyncSession, candidate_id: uuid.UUID, customer_ids: list[uuid.UUID], message: str | None, user: User
) -> list[TesterInvite]:
    """Chị mời khách quen thử mẫu: mỗi khách một link riêng dùng một lần. Đây là việc chị quyết (h8)."""
    cand = await db.get(Candidate, candidate_id)
    if cand is None:
        raise NotFound("Không tìm thấy món đang thử.")
    if cand.stage != CandidateStage.TRIAL:
        raise BadRequest("Chỉ mời thử món đang ở cột «Đang thử».")
    if not customer_ids:
        raise BadRequest("Chị chọn ít nhất một khách.")
    out = []
    for cid in dict.fromkeys(customer_ids):
        c = await get_customer(db, cid)
        if await db.scalar(
            select(TesterInvite.id).where(TesterInvite.candidate_id == cand.id, TesterInvite.customer_id == c.id)
        ):
            continue
        name = (c.name or "bạn").split()[-1]
        text = (message or DEFAULT_INVITE).replace("{ten}", name).replace("{mon}", cand.title_vi)
        inv = TesterInvite(candidate_id=cand.id, customer_id=c.id, token=random_token(18), message=text)
        db.add(inv)
        await db.flush()
        if await is_opted_out(db, c.id):
            out.append(inv)  # để nháp: khách từ chối nhận tin, chị tự gửi link nếu khách đồng ý
            continue
        try:
            await notify(db, c, f"{text}\n{invite_link(inv.token)}", link=invite_link(inv.token), kind="tester_invite")
            inv.status = TesterInviteStatus.INVITED
            inv.invited_at = now_utc()
        except (IntegrationError, BadRequest) as e:
            log.info("Chưa gửi được lời mời thử cho %s: %s", c.id, e)
        out.append(inv)
    await control.audit(db, "crm.testers_invited", user=user, entity_type="candidates", entity_id=cand.id,
                        data={"customers": [str(i.customer_id) for i in out]})  # fmt: skip
    await db.flush()
    return out


async def mark_invite(db: AsyncSession, invite_id: uuid.UUID, status: TesterInviteStatus, user: User) -> TesterInvite:
    inv = await db.get(TesterInvite, invite_id)
    if inv is None:
        raise NotFound("Không tìm thấy lời mời.")
    allowed = {
        TesterInviteStatus.INVITED: {TesterInviteStatus.DRAFT},
        TesterInviteStatus.SAMPLE_SENT: {TesterInviteStatus.INVITED, TesterInviteStatus.ACCEPTED},
        TesterInviteStatus.CLOSED: set(TesterInviteStatus) - {TesterInviteStatus.CLOSED},
    }
    if status not in allowed or inv.status not in allowed[status]:
        raise Conflict("Không chuyển lời mời sang bước này được.", code="invalid_transition")
    inv.status = status
    if status == TesterInviteStatus.SAMPLE_SENT:
        inv.sample_sent_at = now_utc()
    if status == TesterInviteStatus.INVITED:
        inv.invited_at = now_utc()
    await control.audit(db, "crm.tester_invite_status", user=user, entity_type="tester_invites", entity_id=inv.id,
                        data={"status": str(status)})  # fmt: skip
    await db.flush()
    return inv


async def invite_by_token(db: AsyncSession, token: str) -> TesterInvite:
    inv = (await db.execute(select(TesterInvite).where(TesterInvite.token == token))).scalar_one_or_none()
    if inv is None or inv.status in (TesterInviteStatus.DRAFT, TesterInviteStatus.CLOSED):
        raise NotFound("Đường link này không còn dùng được.")
    return inv


async def respond_invite(
    db: AsyncSession, token: str, action: str, *, feedback: str | None, rating: int | None
) -> TesterInvite:
    """Khách trả lời qua link (công khai): nhận / không nhận, rồi gửi cảm nhận đúng một lần."""
    inv = await invite_by_token(db, token)
    now = now_utc()
    if action in ("accept", "decline"):
        if inv.status != TesterInviteStatus.INVITED:
            raise Conflict("Bạn đã trả lời lời mời này rồi.", code="already_answered")
        inv.status = TesterInviteStatus.ACCEPTED if action == "accept" else TesterInviteStatus.DECLINED
        inv.responded_at = now
    elif action == "feedback":
        if inv.status == TesterInviteStatus.FEEDBACK_RECEIVED:
            raise Conflict("Cảm nhận đã được gửi rồi, cảm ơn bạn!", code="feedback_done")
        if inv.status == TesterInviteStatus.DECLINED:
            raise Conflict("Bạn đã từ chối lời mời này.", code="declined")
        if not (feedback or "").strip():
            raise BadRequest("Bạn viết vài dòng cảm nhận giúp mình nhé.")
        inv.feedback = feedback.strip()[:4000]
        inv.feedback_rating = rating
        inv.feedback_at = now
        inv.responded_at = inv.responded_at or now
        inv.status = TesterInviteStatus.FEEDBACK_RECEIVED
        c = await db.get(Customer, inv.customer_id)
        await events.emit(
            "tester.feedback_received",
            {"tester_invite_id": str(inv.id), "candidate_id": str(inv.candidate_id), "customer_id": str(inv.customer_id),
             "customer_name": c.name if c else None, "feedback": inv.feedback, "rating": rating},
            db=db,
        )  # fmt: skip
    else:
        raise BadRequest("Thao tác không hợp lệ.")
    await control.audit(db, "crm.tester_responded", actor=Actor.CUSTOMER, entity_type="tester_invites",
                        entity_id=inv.id, data={"action": action})  # fmt: skip
    await db.flush()
    return inv
