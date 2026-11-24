"""Route của crm: sổ khách, khách quen, nhắc mua lại, giới thiệu bạn, khách thử hàng (/api/desk/crm) và link thử hàng
công khai cho khách (/api/store/crm/thu-hang/<token>)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.errors import NotFound
from app.core.pagination import Page, Paginated, paginate
from app.modules.catalog.models import Category, Drop, Product
from app.modules.crm import service
from app.modules.crm.models import (
    Broadcast,
    CustomerNote,
    GroupDigest,
    NoteKind,
    Referral,
    ReferralUse,
    ReminderStatus,
    ReorderReminder,
    TesterInvite,
    TesterInviteStatus,
)
from app.modules.crm.schemas import (
    BroadcastIn,
    BroadcastView,
    CrmSettingsIn,
    CustomerListItem,
    CustomerNoteOut,
    CustomerProfile,
    DigestIn,
    GroupDigestOut,
    IdentityView,
    InviteIn,
    InviteStatusIn,
    InviteView,
    ManualUseIn,
    NoteIn,
    NotePatch,
    OptOutIn,
    OrderBrief,
    OrderLine,
    PublicInvite,
    QuestionView,
    ReferralOut,
    ReferralStats,
    ReferralUseOut,
    ReferralUseView,
    ReferralView,
    RegularsOut,
    ReminderView,
    ReorderRuleIn,
    ReorderRuleView,
    RespondIn,
    RewardIn,
    RunDueOut,
    SendIn,
    TagIn,
    ThreadBrief,
    TrialCandidateView,
    TrialNoteView,
)
from app.modules.inbox.context import ORDER_STATUS_LABELS
from app.modules.inbox.models import Direction, Message, Thread
from app.modules.inbox.service import CHANNEL_LABELS
from app.modules.orders.models import Customer, CustomerIdentity, Order
from app.modules.sourcing.models import Candidate

router = APIRouter(prefix="/api/desk/crm", tags=["crm"])
store = APIRouter(prefix="/api/store/crm", tags=["crm-store"])
routers = [router, store]


# ---- dựng dữ liệu trả về -----------------------------------------------------------------------------------------


async def _items(db: AsyncSession, customers: list[Customer]) -> list[CustomerListItem]:
    ids = [c.id for c in customers]
    tags = await service.tags_of(db, ids)
    summaries = await service.ai_summaries(db, ids)
    chans = await service.channels_of(db, ids)
    min_orders = await service.regular_min_orders(db)
    return [
        CustomerListItem(
            id=c.id,
            name=c.name,
            phone=c.phone,
            email=c.email,
            channels=chans.get(c.id, []),
            order_count=c.order_count,
            total_spent_vnd=c.total_spent_vnd,
            last_order_at=c.last_order_at,
            is_regular=c.is_regular or c.order_count >= min_orders or service.REGULAR_TAG in tags[c.id],
            opted_out=service.OPT_OUT_TAG in tags[c.id],
            tags=tags[c.id],
            summary=(summaries[c.id].body if c.id in summaries else None) or c.profile_summary,
            created_at=c.created_at,
        )
        for c in customers
    ]


async def _invite_views(db: AsyncSession, invites: list[TesterInvite]) -> list[InviteView]:
    cids = {i.customer_id for i in invites}
    names = (
        dict((await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(cids)))).all()) if cids else {}
    )
    cand_ids = {i.candidate_id for i in invites}
    titles = (
        dict((await db.execute(select(Candidate.id, Candidate.title_vi).where(Candidate.id.in_(cand_ids)))).all())
        if cand_ids
        else {}
    )
    return [
        InviteView(
            id=i.id,
            candidate_id=i.candidate_id,
            candidate_title=titles.get(i.candidate_id),
            customer_id=i.customer_id,
            customer_name=names.get(i.customer_id),
            status=i.status,
            message=i.message,
            invited_at=i.invited_at,
            responded_at=i.responded_at,
            feedback=i.feedback,
            feedback_rating=i.feedback_rating,
            feedback_at=i.feedback_at,
            link=service.invite_link(i.token),
        )
        for i in invites
    ]


async def _reminder_views(db: AsyncSession, rows: list[ReorderReminder]) -> list[ReminderView]:
    cids = {r.customer_id for r in rows}
    pids = {r.product_id for r in rows}
    cn = dict((await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(cids)))).all()) if cids else {}
    pn = dict((await db.execute(select(Product.id, Product.name).where(Product.id.in_(pids)))).all()) if pids else {}
    return [
        ReminderView(
            **ReminderView.model_validate(r).model_dump(exclude={"customer_name", "product_name"}),
            customer_name=cn.get(r.customer_id),
            product_name=pn.get(r.product_id),
        )
        for r in rows
    ]


async def _profile(db: AsyncSession, customer_id: uuid.UUID) -> CustomerProfile:
    c = await service.get_customer(db, customer_id)
    (item,) = await _items(db, [c])
    notes = list(
        (
            await db.execute(
                select(CustomerNote)
                .where(CustomerNote.customer_id == c.id)
                .order_by(CustomerNote.pinned.desc(), CustomerNote.created_at.desc())
            )
        ).scalars()
    )
    ai_note = next((n for n in notes if n.kind == NoteKind.AI_SUMMARY), None)
    orders = list(
        (
            await db.execute(select(Order).where(Order.customer_id == c.id).order_by(Order.placed_at.desc()).limit(20))
        ).scalars()
    )
    threads = list(
        (
            await db.execute(
                select(Thread).where(Thread.customer_id == c.id).order_by(Thread.last_message_at.desc().nulls_last())
            )
        ).scalars()
    )
    questions = (
        await db.execute(
            select(Message.body, Message.sent_at, Message.thread_id)
            .join(Thread, Thread.id == Message.thread_id)
            .where(Thread.customer_id == c.id, Message.direction == Direction.INBOUND)
            .order_by(Message.sent_at.desc())
            .limit(5)
        )
    ).all()
    ref = (await db.execute(select(Referral).where(Referral.referrer_customer_id == c.id))).scalar_one_or_none()
    reminders = list(
        (
            await db.execute(
                select(ReorderReminder).where(ReorderReminder.customer_id == c.id).order_by(ReorderReminder.due_on)
            )
        ).scalars()
    )
    invites = list((await db.execute(select(TesterInvite).where(TesterInvite.customer_id == c.id))).scalars())
    identities = list(
        (await db.execute(select(CustomerIdentity).where(CustomerIdentity.customer_id == c.id))).scalars()
    )
    return CustomerProfile(
        **item.model_dump(),
        default_address=c.default_address,
        first_channel=c.first_channel,
        identities=[IdentityView(channel=i.channel, external_id=i.external_id, display_name=i.display_name)
                    for i in identities],
        notes=[CustomerNoteOut.model_validate(n) for n in notes if n.kind != NoteKind.AI_SUMMARY],
        interests=[n.body for n in notes if n.kind == NoteKind.INTEREST],
        summary_updated_at=ai_note.updated_at if ai_note else None,
        orders=[
            OrderBrief(id=o.id, code=o.code, status=str(o.status), status_label=ORDER_STATUS_LABELS.get(o.status, str(o.status)),
                       placed_at=o.placed_at, total_vnd=o.total_vnd,
                       items=[OrderLine(name=i.name, quantity=i.quantity) for i in o.items])
            for o in orders
        ],
        threads=[
            ThreadBrief(id=t.id, channel=t.channel, channel_label=CHANNEL_LABELS.get(t.channel, str(t.channel)),
                        kind=str(t.kind), snippet=t.snippet, status=str(t.status), needs_owner=t.needs_owner,
                        last_message_at=t.last_message_at)
            for t in threads
        ],
        recent_questions=[QuestionView(body=b, sent_at=s, thread_id=tid) for b, s, tid in questions],
        referral=ReferralOut.model_validate(ref) if ref else None,
        reminders=await _reminder_views(db, reminders),
        invites=await _invite_views(db, invites),
    )  # fmt: skip


# ---- h4: sổ khách ------------------------------------------------------------------------------------------------


@router.get("/customers", response_model=Paginated[CustomerListItem])
async def list_customers(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    q: str | None = Query(default=None, max_length=100),
    segment: Literal["all", "regular", "optout", "new"] = "all",
    tag: str | None = None,
) -> Paginated[CustomerListItem]:
    res = await paginate(db, await service.customers_query(db, q=q, segment=segment, tag=tag), page)
    return Paginated[CustomerListItem](
        items=await _items(db, res.items), total=res.total, page=res.page, size=res.size, pages=res.pages
    )


@router.get("/customers/{customer_id}", response_model=CustomerProfile)
async def get_profile(customer_id: uuid.UUID, _: CurrentUser, db: DbSession) -> CustomerProfile:
    return await _profile(db, customer_id)


@router.post("/customers/{customer_id}/notes", response_model=CustomerNoteOut, status_code=status.HTTP_201_CREATED)
async def add_note(customer_id: uuid.UUID, body: NoteIn, user: CurrentUser, db: DbSession) -> CustomerNote:
    return await service.add_note(db, customer_id, body.body, NoteKind(body.kind), user, pinned=body.pinned)


@router.patch("/notes/{note_id}", response_model=CustomerNoteOut)
async def edit_note(note_id: uuid.UUID, body: NotePatch, _: CurrentUser, db: DbSession) -> CustomerNote:
    n = await db.get(CustomerNote, note_id)
    if n is None:
        raise NotFound("Không tìm thấy ghi chú.")
    if body.body is not None:
        n.body = body.body.strip()
    if body.pinned is not None:
        n.pinned = body.pinned
    await db.flush()
    return n


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: uuid.UUID, _: CurrentUser, db: DbSession) -> Response:
    n = await db.get(CustomerNote, note_id)
    if n is None:
        raise NotFound("Không tìm thấy ghi chú.")
    await db.delete(n)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/customers/{customer_id}/tags", response_model=CustomerProfile, status_code=status.HTTP_201_CREATED)
async def add_tag(customer_id: uuid.UUID, body: TagIn, _: CurrentUser, db: DbSession) -> CustomerProfile:
    await service.add_tag(db, customer_id, body.tag)
    return await _profile(db, customer_id)


@router.delete("/customers/{customer_id}/tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(customer_id: uuid.UUID, tag: str, _: CurrentUser, db: DbSession) -> Response:
    await service.remove_tag(db, customer_id, tag)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/customers/{customer_id}/opt-out", response_model=CustomerProfile)
async def opt_out(customer_id: uuid.UUID, body: OptOutIn, user: CurrentUser, db: DbSession) -> CustomerProfile:
    await service.get_customer(db, customer_id)
    await service.set_opt_out(db, customer_id, body.opt_out, user)
    return await _profile(db, customer_id)


@router.post("/customers/{customer_id}/refresh-summary", response_model=CustomerProfile)
async def refresh_summary(customer_id: uuid.UUID, _: CurrentUser, db: DbSession) -> CustomerProfile:
    await service.get_customer(db, customer_id)
    await service.refresh_profile(db, customer_id)
    return await _profile(db, customer_id)


@router.post("/customers/{customer_id}/referral", response_model=CustomerProfile)
async def make_referral(customer_id: uuid.UUID, _: CurrentUser, db: DbSession) -> CustomerProfile:
    await service.get_or_create_referral(db, customer_id)
    return await _profile(db, customer_id)


# ---- h5: khách quen, tin báo đợt, tóm tắt nhóm --------------------------------------------------------------------


@router.get("/regulars", response_model=RegularsOut)
async def list_regulars(_: CurrentUser, db: DbSession) -> RegularsOut:
    people = await service.regulars(db)
    reachable = [c for c in await service.audience(db) if await service.recipient(db, c)]
    return RegularsOut(
        min_orders=await service.regular_min_orders(db), total=len(people), reachable=len(reachable),
        items=await _items(db, people),
    )  # fmt: skip


@router.patch("/settings", response_model=RegularsOut)
async def update_settings(body: CrmSettingsIn, user: OwnerUser, db: DbSession) -> RegularsOut:
    await control.set_setting(db, service.REGULAR_MIN_KEY, body.regular_min_orders, user)
    return await list_regulars(user, db)


async def _broadcast_views(db: AsyncSession, rows: list[Broadcast]) -> list[BroadcastView]:
    dids = {b.drop_id for b in rows if b.drop_id}
    titles = dict((await db.execute(select(Drop.id, Drop.title).where(Drop.id.in_(dids)))).all()) if dids else {}
    return [
        BroadcastView(
            **BroadcastView.model_validate(b).model_dump(exclude={"drop_title"}), drop_title=titles.get(b.drop_id)
        )
        for b in rows
    ]


@router.get("/broadcasts", response_model=list[BroadcastView])
async def list_broadcasts(_: CurrentUser, db: DbSession) -> list[BroadcastView]:
    rows = list((await db.execute(select(Broadcast).order_by(Broadcast.created_at.desc()).limit(30))).scalars())
    return await _broadcast_views(db, rows)


@router.post("/broadcasts", response_model=BroadcastView, status_code=status.HTTP_201_CREATED)
async def create_broadcast(body: BroadcastIn, _: CurrentUser, db: DbSession) -> BroadcastView:
    b = await service.create_broadcast(db, body.title, body.body)
    return (await _broadcast_views(db, [b]))[0]


@router.post("/broadcasts/drop/{drop_id}", response_model=BroadcastView, status_code=status.HTTP_201_CREATED)
async def draft_for_drop(drop_id: uuid.UUID, _: CurrentUser, db: DbSession) -> BroadcastView:
    b = await service.draft_drop_announcement(db, drop_id)
    if b is None:
        raise NotFound("Không tìm thấy đợt.")
    return (await _broadcast_views(db, [b]))[0]


@router.post("/broadcasts/{broadcast_id}/send", response_model=BroadcastView)
async def send_broadcast(broadcast_id: uuid.UUID, body: SendIn, user: OwnerUser, db: DbSession) -> BroadcastView:
    b = await service.send_broadcast_now(db, broadcast_id, body.body, user)
    return (await _broadcast_views(db, [b]))[0]


@router.post("/broadcasts/{broadcast_id}/cancel", response_model=BroadcastView)
async def cancel_broadcast(broadcast_id: uuid.UUID, user: OwnerUser, db: DbSession) -> BroadcastView:
    b = await service.cancel_broadcast(db, broadcast_id, user)
    return (await _broadcast_views(db, [b]))[0]


@router.get("/group-digests", response_model=list[GroupDigestOut])
async def list_digests(_: CurrentUser, db: DbSession) -> list[GroupDigest]:
    return list((await db.execute(select(GroupDigest).order_by(GroupDigest.created_at.desc()).limit(20))).scalars())


@router.post("/group-digests", response_model=GroupDigestOut, status_code=status.HTTP_201_CREATED)
async def create_digest(body: DigestIn, _: CurrentUser, db: DbSession) -> GroupDigest:
    return await service.create_digest(db, body.text, period_start=body.period_start, period_end=body.period_end)


# ---- h6: nhắc mua lại --------------------------------------------------------------------------------------------


@router.get("/reorder-rules", response_model=list[ReorderRuleView])
async def reorder_rules(_: CurrentUser, db: DbSession) -> list[ReorderRuleView]:
    cycles = await service.reorder_cycles(db)
    cats = {c.id: c for c in (await db.execute(select(Category))).scalars()}
    consumable_cats = [cid for cid, c in cats.items() if c.is_consumable]
    configured = [uuid.UUID(k) for k in cycles]
    rows = (
        await db.execute(
            select(Product)
            .where(
                Product.is_consumable.is_(True)
                | Product.category_id.in_(consumable_cats or [uuid.uuid4()])
                | Product.id.in_(configured or [uuid.uuid4()])
            )
            .order_by(Product.name)
        )
    ).scalars()
    out = []
    for p in rows:
        rule = cycles.get(str(p.id))
        cat = cats.get(p.category_id) if p.category_id else None
        out.append(
            ReorderRuleView(
                product_id=p.id,
                name=p.name,
                is_consumable=p.is_consumable,
                product_days=p.reorder_days if p.is_consumable else None,
                category_days=cat.default_reorder_days if cat and cat.is_consumable else None,
                configured_days=rule.get("days") if rule else None,
                active=rule.get("active", True) if rule else True,
                effective_days=await service.cycle_for(db, p, cycles),
            )
        )
    return out


@router.put("/reorder-rules/{product_id}", response_model=list[ReorderRuleView])
async def set_reorder_rule(
    product_id: uuid.UUID, body: ReorderRuleIn, user: OwnerUser, db: DbSession
) -> list[ReorderRuleView]:
    await service.set_cycle(db, product_id, body.cycle_days, body.active, user)
    return await reorder_rules(user, db)


@router.get("/reminders", response_model=list[ReminderView])
async def list_reminders(
    _: CurrentUser, db: DbSession, status_: ReminderStatus | None = Query(default=None, alias="status")
) -> list[ReminderView]:
    q = select(ReorderReminder).order_by(ReorderReminder.due_on)
    if status_:
        q = q.where(ReorderReminder.status == status_)
    return await _reminder_views(db, list((await db.execute(q.limit(200))).scalars()))


@router.post("/reminders/run-due", response_model=RunDueOut)
async def run_due(_: CurrentUser, db: DbSession) -> RunDueOut:
    return RunDueOut(**await service.run_due(db))


@router.post("/reminders/{reminder_id}/send", response_model=ReminderView)
async def send_reminder(reminder_id: uuid.UUID, body: SendIn, user: OwnerUser, db: DbSession) -> ReminderView:
    r = await service.send_reminder_now(db, reminder_id, body.body, user)
    return (await _reminder_views(db, [r]))[0]


@router.post("/reminders/{reminder_id}/skip", response_model=ReminderView)
async def skip_reminder(reminder_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ReminderView:
    r = await service.skip_reminder(db, reminder_id, user)
    return (await _reminder_views(db, [r]))[0]


# ---- h7: giới thiệu bạn ------------------------------------------------------------------------------------------


@router.get("/referrals/stats", response_model=ReferralStats)
async def referral_stats(_: CurrentUser, db: DbSession) -> ReferralStats:
    return ReferralStats(**await service.referral_stats(db))


@router.get("/referrals/uses", response_model=list[ReferralUseView])
async def referral_uses(_: CurrentUser, db: DbSession) -> list[ReferralUseView]:
    rows = (
        await db.execute(
            select(ReferralUse, Referral)
            .join(Referral, Referral.id == ReferralUse.referral_id)
            .order_by(ReferralUse.created_at.desc())
            .limit(200)
        )
    ).all()
    cids = {u.referred_customer_id for u, _ in rows} | {r.referrer_customer_id for _, r in rows}
    oids = {u.order_id for u, _ in rows if u.order_id}
    names = (
        dict((await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(cids)))).all()) if cids else {}
    )
    codes = dict((await db.execute(select(Order.id, Order.code).where(Order.id.in_(oids)))).all()) if oids else {}
    return [
        ReferralUseView(
            **ReferralUseOut.model_validate(u).model_dump(),
            code=r.code,
            referrer_name=names.get(r.referrer_customer_id),
            referred_name=names.get(u.referred_customer_id),
            order_code=codes.get(u.order_id) if u.order_id else None,
        )
        for u, r in rows
    ]


@router.get("/referrals", response_model=list[ReferralView])
async def list_referrals(_: CurrentUser, db: DbSession) -> list[ReferralView]:
    rows = list(
        (await db.execute(select(Referral).order_by(Referral.uses_count.desc(), Referral.created_at))).scalars()
    )
    cids = {r.referrer_customer_id for r in rows}
    names = (
        dict((await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(cids)))).all()) if cids else {}
    )
    return [
        ReferralView(**ReferralOut.model_validate(r).model_dump(), referrer_name=names.get(r.referrer_customer_id))
        for r in rows
    ]


@router.post("/referrals/{referral_id}/uses", response_model=ReferralView, status_code=status.HTTP_201_CREATED)
async def add_referral_use(referral_id: uuid.UUID, body: ManualUseIn, user: OwnerUser, db: DbSession) -> ReferralView:
    await service.manual_referral(db, referral_id, body.customer_id, body.order_id, user)
    r = await db.get(Referral, referral_id)
    return ReferralView(**ReferralOut.model_validate(r).model_dump())


@router.post("/referral-uses/{use_id}/reward", response_model=ReferralStats)
async def reward(use_id: uuid.UUID, body: RewardIn, user: OwnerUser, db: DbSession) -> ReferralStats:
    await service.reward_referral(db, use_id, body.note, user)
    return ReferralStats(**await service.referral_stats(db))


@router.post("/referral-uses/{use_id}/void", response_model=ReferralStats)
async def void(use_id: uuid.UUID, user: OwnerUser, db: DbSession) -> ReferralStats:
    await service.void_referral(db, use_id, user)
    return ReferralStats(**await service.referral_stats(db))


# ---- h8: khách thử hàng ------------------------------------------------------------------------------------------


@router.get("/testers/candidates", response_model=list[TrialCandidateView])
async def trial_candidates(_: CurrentUser, db: DbSession) -> list[TrialCandidateView]:
    cands = await service.trial_candidates(db)
    invites = await _invite_views(db, await service.invites_of(db, [c.id for c in cands]))
    out = []
    for c in cands:
        notes = await service.trial_notes(db, c.id)
        out.append(
            TrialCandidateView(
                id=c.id,
                title=c.title_vi,
                image_url=c.main_image_url or (c.images[0] if c.images else None),
                stage_changed_at=c.stage_changed_at,
                notes=[
                    TrialNoteView(
                        id=n.id,
                        kind=str(n.kind),
                        author=str(n.author),
                        text=n.text,
                        recorded_at=n.recorded_at,
                        trial_day=n.trial_day,
                    )
                    for n in notes
                ],
                invites=[i for i in invites if i.candidate_id == c.id],
            )
        )
    return out


@router.post("/tester-invites", response_model=list[InviteView], status_code=status.HTTP_201_CREATED)
async def invite(body: InviteIn, user: OwnerUser, db: DbSession) -> list[InviteView]:
    return await _invite_views(
        db, await service.invite_testers(db, body.candidate_id, body.customer_ids, body.message, user)
    )


@router.post("/tester-invites/{invite_id}/status", response_model=InviteView)
async def invite_status(invite_id: uuid.UUID, body: InviteStatusIn, user: CurrentUser, db: DbSession) -> InviteView:
    inv = await service.mark_invite(db, invite_id, TesterInviteStatus(body.status), user)
    return (await _invite_views(db, [inv]))[0]


# ---- công khai: link thử hàng ------------------------------------------------------------------------------------


async def _public(db: AsyncSession, inv: TesterInvite) -> PublicInvite:
    cand = await db.get(Candidate, inv.candidate_id)
    cust = await db.get(Customer, inv.customer_id)
    s = inv.status
    return PublicInvite(
        first_name=((cust.name if cust else None) or "bạn").split()[-1],
        product_title=cand.title_vi if cand else "món thử",
        image_url=(cand.main_image_url or (cand.images[0] if cand.images else None)) if cand else None,
        message=inv.message,
        status=s,
        can_answer=s == TesterInviteStatus.INVITED,
        can_feedback=s in (TesterInviteStatus.INVITED, TesterInviteStatus.ACCEPTED, TesterInviteStatus.SAMPLE_SENT),
        feedback=inv.feedback,
        feedback_rating=inv.feedback_rating,
    )


@store.get("/thu-hang/{token}", response_model=PublicInvite)
async def public_invite(token: str, db: DbSession) -> PublicInvite:
    return await _public(db, await service.invite_by_token(db, token))


@store.post("/thu-hang/{token}", response_model=PublicInvite)
async def respond(token: str, body: RespondIn, db: DbSession) -> PublicInvite:
    inv = await service.respond_invite(db, token, body.action, feedback=body.feedback, rating=body.rating)
    return await _public(db, inv)
