"""Route của hộp thư: bàn làm việc (/api/desk/inbox), webhook (/api/hooks/social/<kênh>), giả lập tin đến (dev/test)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.config import settings
from app.core.db import DbSession
from app.core.deps import CurrentUser, OwnerUser
from app.core.enums import Channel
from app.core.errors import Forbidden, NotFound
from app.core.jobs import enqueue
from app.core.pagination import Page, Paginated
from app.integrations import IntegrationError, get_driver
from app.modules.catalog.models import Product
from app.modules.inbox import service
from app.modules.inbox.channels import HOOK_DRIVERS, messaging_driver
from app.modules.inbox.models import ChannelAccount, Direction, Message, ReplyDraft, Thread, ThreadStatus
from app.modules.inbox.schemas import (
    Capabilities,
    ChannelAccountOut,
    CustomerBrief,
    DraftView,
    InboxMeta,
    LastMessage,
    LinkCustomerIn,
    MessageOut,
    ProductBrief,
    RedraftIn,
    ReplyIn,
    SendDraftIn,
    SimulateIn,
    StatusIn,
    ThreadCounts,
    ThreadDetail,
    ThreadListItem,
)
from app.modules.orders.models import Customer

log = logging.getLogger("app.inbox")

router = APIRouter(prefix="/api/desk/inbox", tags=["inbox"])
hooks = APIRouter(prefix="/api/hooks/social", tags=["hooks"])
routers = [router, hooks]

REGULAR_MIN_KEY = "crm.regular_min_orders"


def _simulate_enabled() -> bool:
    return settings.app_env in ("dev", "test")


def _last(m: Message | None) -> LastMessage | None:
    if m is None:
        return None
    return LastMessage(
        direction=m.direction, sender=m.sender, body=m.body, ai_generated=m.ai_generated, sent_at=m.sent_at
    )


async def _draft_view(db: AsyncSession, d: ReplyDraft | None) -> DraftView | None:
    if d is None:
        return None
    return DraftView(
        id=d.id,
        kind=d.kind,
        intent=d.intent,
        intent_label=service.INTENT_LABELS.get(d.intent) if d.intent else None,
        body=d.body,
        status=d.status,
        confidence=d.confidence,
        sources=d.sources,
        options=await service.draft_options(db, d),
        approval_item_id=d.approval_item_id,
        created_at=d.created_at,
    )


async def _list_items(db: AsyncSession, threads: list[Thread]) -> list[ThreadListItem]:
    ids = [t.id for t in threads]
    drafts = await service.active_drafts(db, ids)
    lasts = await service.last_messages(db, ids)
    inbound = await service.last_messages(db, ids, Direction.INBOUND)
    cids = {t.customer_id for t in threads if t.customer_id}
    names = (
        dict((await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(cids)))).all()) if cids else {}
    )
    out = []
    for t in threads:
        last = lasts.get(t.id)
        out.append(
            ThreadListItem(
                id=t.id,
                channel=t.channel,
                channel_label=service.CHANNEL_LABELS.get(t.channel, str(t.channel)),
                kind=t.kind,
                participant_name=t.participant_name,
                customer_id=t.customer_id,
                customer_name=names.get(t.customer_id) if t.customer_id else None,
                status=t.status,
                needs_owner=t.needs_owner,
                escalation_reason=t.escalation_reason,
                escalation_label=service.REASON_LABELS.get(t.escalation_reason) if t.escalation_reason else None,
                last_intent=t.last_intent,
                intent_label=service.INTENT_LABELS.get(t.last_intent) if t.last_intent else None,
                snippet=t.snippet,
                last_message_at=t.last_message_at,
                unread_count=t.unread_count,
                last_message=_last(last),
                last_inbound=_last(inbound.get(t.id)),
                draft=await _draft_view(db, drafts.get(t.id)),
            )
        )
    return out


async def _detail(db: AsyncSession, t: Thread) -> ThreadDetail:
    (item,) = await _list_items(db, [t])
    acc = await db.get(ChannelAccount, t.channel_account_id) if t.channel_account_id else None
    customer = None
    if t.customer_id and (c := await db.get(Customer, t.customer_id)):
        min_orders = int(await control.get_setting(db, REGULAR_MIN_KEY) or 2)
        customer = CustomerBrief(
            id=c.id, name=c.name, phone=c.phone, order_count=c.order_count, total_spent_vnd=c.total_spent_vnd,
            is_regular=c.is_regular or c.order_count >= min_orders,
        )  # fmt: skip
    product = None
    if t.product_id and (p := await db.get(Product, t.product_id)):
        product = ProductBrief(id=p.id, name=p.name, slug=p.slug, price_vnd=p.price_vnd)
    return ThreadDetail(
        **item.model_dump(),
        account_name=acc.name if acc else None,
        external_post_id=t.external_post_id,
        messages=[MessageOut.model_validate(m) for m in await service.messages_of(db, t.id)],
        customer=customer,
        product=product,
        capabilities=Capabilities(**await service.capabilities(db, t)),
    )


# ---- bàn làm việc ------------------------------------------------------------------------------------------------


@router.get("/meta", response_model=InboxMeta)
async def inbox_meta(_: CurrentUser, db: DbSession) -> InboxMeta:
    accounts = (await db.execute(select(ChannelAccount).order_by(ChannelAccount.channel))).scalars()
    return InboxMeta(
        simulate_enabled=_simulate_enabled(), accounts=[ChannelAccountOut.model_validate(a) for a in accounts]
    )


@router.get("/counts", response_model=ThreadCounts)
async def thread_counts(_: CurrentUser, db: DbSession) -> ThreadCounts:
    return ThreadCounts(**await service.counts(db))


@router.get("/threads", response_model=Paginated[ThreadListItem])
async def list_threads(
    _: CurrentUser,
    db: DbSession,
    page: Page,
    tab: Literal["waiting", "ai", "all"] = "waiting",
    q: str | None = Query(default=None, max_length=100),
    channel: Channel | None = None,
) -> Paginated[ThreadListItem]:
    res = await service.list_threads(db, page, tab=tab, q=q, channel=channel)
    return Paginated[ThreadListItem](
        items=await _list_items(db, res.items), total=res.total, page=res.page, size=res.size, pages=res.pages
    )


@router.post("/dev/simulate", response_model=ThreadDetail, status_code=status.HTTP_201_CREATED)
async def simulate(body: SimulateIn, _: CurrentUser, db: DbSession) -> ThreadDetail:
    """Giả lập khách bình luận / nhắn tin (chỉ bật ở môi trường dev, test) — chạy trọn luồng không cần tài khoản."""
    if not _simulate_enabled():
        raise NotFound()
    mock = get_driver("social", "mock")
    ev = mock.simulate_inbound(
        body.text, channel=Channel(body.channel), kind=body.kind, author_name=body.author_name,
        author_external_id=body.author_external_id, post_external_id=body.post_external_id,
    )  # fmt: skip
    await mock.fetch_inbound()  # lấy ra khỏi hàng đợi giả, xử lý ngay dưới đây
    msg = await service.ingest(db, ev, driver_name="mock")
    if msg is None:
        raise NotFound()
    await service.triage(db, msg.id)
    return await _detail(db, await service.get_thread(db, msg.thread_id))


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread(thread_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ThreadDetail:
    return await _detail(db, await service.get_thread(db, thread_id))


@router.post("/threads/{thread_id}/read", response_model=ThreadDetail)
async def read_thread(thread_id: uuid.UUID, _: CurrentUser, db: DbSession) -> ThreadDetail:
    t = await service.get_thread(db, thread_id)
    await service.mark_read(db, t)
    return await _detail(db, t)


@router.post("/threads/{thread_id}/reply", response_model=ThreadDetail)
async def reply(thread_id: uuid.UUID, body: ReplyIn, user: CurrentUser, db: DbSession) -> ThreadDetail:
    await service.owner_reply(db, thread_id, body.body, user, private=body.private)
    return await _detail(db, await service.get_thread(db, thread_id))


@router.post("/threads/{thread_id}/redraft", response_model=ThreadDetail)
async def redraft(thread_id: uuid.UUID, body: RedraftIn, _: CurrentUser, db: DbSession) -> ThreadDetail:
    await service.redraft(db, thread_id, body.note)
    return await _detail(db, await service.get_thread(db, thread_id))


@router.post("/threads/{thread_id}/customer", response_model=ThreadDetail)
async def link_customer(thread_id: uuid.UUID, body: LinkCustomerIn, user: CurrentUser, db: DbSession) -> ThreadDetail:
    return await _detail(db, await service.link_customer(db, thread_id, body.customer_id, user))


@router.post("/threads/{thread_id}/status", response_model=ThreadDetail)
async def set_status(thread_id: uuid.UUID, body: StatusIn, user: CurrentUser, db: DbSession) -> ThreadDetail:
    return await _detail(db, await service.set_status(db, thread_id, ThreadStatus(body.status), user))


@router.post("/drafts/{draft_id}/send", response_model=ThreadDetail)
async def send_draft(draft_id: uuid.UUID, body: SendDraftIn, user: OwnerUser, db: DbSession) -> ThreadDetail:
    """Gửi bản nháp AI (có thể đã sửa). Bản nháp đang chờ duyệt thì đi qua hàng chờ (chỉ chị được duyệt)."""
    d = await service.send_draft_now(db, draft_id, body.body, user, private=body.private)
    return await _detail(db, await service.get_thread(db, d.thread_id))


@router.post("/drafts/{draft_id}/dismiss", response_model=ThreadDetail)
async def dismiss_draft(draft_id: uuid.UUID, user: OwnerUser, db: DbSession) -> ThreadDetail:
    d = await service.dismiss_draft(db, draft_id, user)
    return await _detail(db, await service.get_thread(db, d.thread_id))


# ---- webhook -----------------------------------------------------------------------------------------------------


def _hook_driver(channel: str) -> tuple[str, Any]:
    name = HOOK_DRIVERS.get(channel)
    if name is None or (name == "mock" and not _simulate_enabled()):
        raise NotFound("Không có webhook cho kênh này.")
    return name, messaging_driver(name)


@hooks.get("/{channel}", include_in_schema=False)
async def verify_webhook(channel: str, request: Request) -> PlainTextResponse:
    """Meta gọi GET để xác nhận đăng ký webhook (hub.challenge)."""
    _, driver = _hook_driver(channel)
    fn = getattr(driver, "verify_subscription", None)
    challenge = fn(dict(request.query_params)) if fn else None
    if challenge is None:
        raise Forbidden("Mã xác nhận webhook không đúng.", code="invalid_verify_token")
    return PlainTextResponse(challenge)


@hooks.post("/{channel}")
async def receive_webhook(channel: str, request: Request, db: DbSession) -> dict[str, int]:
    name, driver = _hook_driver(channel)
    raw = await request.body()
    try:
        evs = await driver.parse_webhook(dict(request.headers), raw)
    except IntegrationError as e:
        if e.code == "invalid_signature":
            raise Forbidden(e.message, code="invalid_signature") from e
        raise
    new_ids: list[uuid.UUID] = []
    for ev in evs:
        msg = await service.ingest(db, ev, driver_name=name)
        if msg is not None:
            new_ids.append(msg.id)
    await db.commit()  # AI xử lý ở việc nền: tin phải nằm trong CSDL trước
    for mid in new_ids:
        try:
            await enqueue("inbox.triage", message_id=str(mid))
        except Exception:
            log.exception("Không xếp được việc xử lý tin %s", mid)
    return {"received": len(evs), "new": len(new_ids)}
