"""Đợt mở bán (e3): nháp → (mở qua control.propose) → đã hẹn giờ / đang mở → đóng (hết hạn, hết suất, chị đóng)
→ hàng về. Mở/đóng phát `drop.opened` / `drop.closed`. «Nhắc mình» báo khách một lần khi đợt mở."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core import events
from app.core.enums import Channel
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.integrations.notify import OutboundNotification
from app.modules.catalog.models import Drop, DropItem, DropReminder, DropStatus, Product, ProductStatus
from app.modules.catalog.textutil import hash_key, normalize_contact, unique_slug
from app.modules.control.models import User, UserRole

log = logging.getLogger("app.catalog")

OPENABLE = (DropStatus.DRAFT, DropStatus.PENDING_REVIEW)
ARRIVED = (DropStatus.FULFILLING, DropStatus.COMPLETED)
PUBLIC = (DropStatus.SCHEDULED, DropStatus.OPEN, DropStatus.CLOSED, DropStatus.SOURCING, DropStatus.ARRIVING,
          *ARRIVED)  # fmt: skip


async def get_drop(db: AsyncSession, drop_id: uuid.UUID) -> Drop:
    d = await db.get(Drop, drop_id)
    if d is None:
        raise NotFound("Không tìm thấy đợt bán.")
    return d


async def get_by_slug(db: AsyncSession, slug: str) -> Drop:
    d = (await db.execute(select(Drop).where(Drop.slug == slug, Drop.status.in_(PUBLIC)))).scalar_one_or_none()
    if d is None:
        raise NotFound("Không tìm thấy đợt này.")
    return d


async def _next_code(db: AsyncSession) -> str:
    codes = (await db.execute(select(Drop.code))).scalars()
    nums = [int(m.group(1)) for c in codes if (m := re.fullmatch(r"D(\d+)", c))]
    return f"D{(max(nums) if nums else 0) + 1}"


def label(drop: Drop) -> str:
    """«Đợt 12» — số đợt cho khách."""
    m = re.fullmatch(r"D(\d+)", drop.code)
    return f"Đợt {m.group(1)}" if m else drop.title


async def create_drop(db: AsyncSession, data: dict[str, Any], user: User) -> Drop:
    code = await _next_code(db)
    d = Drop(
        code=code,
        slug=await unique_slug(db, Drop, f"dot-{code[1:]}-{data['title']}"),
        title=data["title"],
        description=data.get("description"),
        opens_at=data.get("opens_at"),
        closes_at=data.get("closes_at"),
        expected_arrival_date=data.get("expected_arrival_date"),
        deposit_pct=data.get("deposit_pct"),
        status=DropStatus.DRAFT,
    )
    db.add(d)
    await db.flush()
    if data.get("items") is not None:
        await set_items(db, d, data["items"])
    await control.audit(db, "catalog.drop_created", user=user, entity_type="drops", entity_id=d.id,
                        summary=f"Tạo {label(d)}: {d.title}")  # fmt: skip
    return d


async def update_drop(db: AsyncSession, drop: Drop, data: dict[str, Any], user: User) -> Drop:
    if drop.status in (*ARRIVED, DropStatus.CANCELLED):
        raise Conflict("Đợt đã xong, không sửa được nữa.")
    for k in ("title", "description", "opens_at", "closes_at", "expected_arrival_date", "deposit_pct"):
        if k in data:
            setattr(drop, k, data[k])
    if "items" in data and data["items"] is not None:
        await set_items(db, drop, data["items"])
    await control.audit(db, "catalog.drop_edited", user=user, entity_type="drops", entity_id=drop.id,
                        summary=f"Sửa {label(drop)}", data={"fields": sorted(data)})  # fmt: skip
    await db.flush()
    return drop


async def set_items(db: AsyncSession, drop: Drop, items: list[dict[str, Any]]) -> None:
    await db.refresh(drop, ["items"])
    existing = {(i.product_id, i.variant_id): i for i in drop.items}
    keep: set[uuid.UUID] = set()
    for pos, raw in enumerate(items):
        pid = uuid.UUID(str(raw["product_id"]))
        product = await db.get(Product, pid)
        if product is None:
            raise BadRequest("Có món không còn trong danh sách sản phẩm.")
        key = (pid, raw.get("variant_id"))
        it = existing.get(key)
        slots = raw.get("slots_total")
        if it is None:
            it = DropItem(drop_id=drop.id, product_id=pid, variant_id=raw.get("variant_id"), slots_reserved=0)
            db.add(it)
        if slots is not None and slots < it.slots_reserved:
            raise BadRequest(f"«{product.name}» đã có {it.slots_reserved} suất được đặt, không giảm dưới số đó.")
        it.price_vnd = int(raw.get("price_vnd") or product.price_vnd)
        it.slots_total = slots
        it.max_per_order = raw.get("max_per_order")
        it.min_total_to_order = raw.get("min_total_to_order")
        it.position = pos
        await db.flush()
        keep.add(it.id)
    for it in drop.items:
        if it.id not in keep:
            if it.slots_reserved:
                raise BadRequest("Không bỏ được món đã có khách đặt khỏi đợt.")
            await db.delete(it)
    await db.flush()
    await db.refresh(drop, ["items"])


async def _validate_openable(db: AsyncSession, drop: Drop) -> None:
    if drop.status not in OPENABLE:
        raise Conflict("Đợt này đã mở hoặc đã xong.", code="drop_not_draft")
    if not drop.items:
        raise BadRequest("Đợt chưa có món nào.", code="drop_empty")
    if drop.closes_at is None or drop.closes_at <= now_utc():
        raise BadRequest("Hạn chót đặt phải ở tương lai.", code="drop_deadline")
    if drop.opens_at and drop.opens_at >= drop.closes_at:
        raise BadRequest("Giờ mở phải trước hạn chót.", code="drop_window")
    pids = [i.product_id for i in drop.items]
    unpublished = (
        await db.execute(select(Product.name).where(Product.id.in_(pids), Product.status != ProductStatus.PUBLISHED))
    ).scalars()
    names = list(unpublished)
    if names:
        raise BadRequest(
            f"Món chưa đăng trên kệ: {', '.join(names)}. Chị đăng trước rồi mới mở đợt.", code="drop_unpublished"
        )


async def request_open(db: AsyncSession, drop: Drop, user: User) -> tuple[Drop, control.ProposeOutcome]:
    """Mở đợt qua control.propose. Chị (owner) bấm thì duyệt luôn — đó là quyết định của chị; người phụ bấm thì chờ chị."""
    await _validate_openable(db, drop)
    when = drop.opens_at
    out = await control.propose(
        "catalog.open_drop",
        f"Mở {label(drop)}: {drop.title}",
        {"drop_id": str(drop.id)},
        {
            "title": drop.title,
            "opens_at": when.isoformat() if when else None,
            "closes_at": drop.closes_at.isoformat() if drop.closes_at else None,
            "expected_arrival_date": drop.expected_arrival_date.isoformat() if drop.expected_arrival_date else None,
            "items": len(drop.items),
            "slots": sum(i.slots_total or 0 for i in drop.items),
        },
        db=db,
        summary=f"{len(drop.items)} món, hạn chót {drop.closes_at:%d/%m}." if drop.closes_at else None,
        ref_type="drops",
        ref_id=drop.id,
        dedupe_key=f"drop:{drop.id}",
        ai_generated=False,
    )
    if out.status == "pending":
        drop.approval_item_id = out.item_id
        drop.status = DropStatus.PENDING_REVIEW
        await db.flush()
        if user.role == UserRole.OWNER and out.item_id:
            item = await control.approve(db, out.item_id, user, note="Chị tự mở đợt từ bàn làm việc")
            if item.error:
                raise BadRequest(item.error)
    await db.refresh(drop)
    return drop, out


async def apply_open(db: AsyncSession, drop: Drop) -> Drop:
    """Handler sau khi duyệt: chưa tới giờ mở → hẹn giờ; tới rồi → mở ngay."""
    await _validate_openable(db, drop)
    now = now_utc()
    if drop.opens_at and drop.opens_at > now:
        drop.status = DropStatus.SCHEDULED
        await db.flush()
        return drop
    return await _open_now(db, drop)


async def _open_now(db: AsyncSession, drop: Drop) -> Drop:
    drop.status = DropStatus.OPEN
    drop.opens_at = drop.opens_at or now_utc()
    drop.announced_at = now_utc()
    await db.flush()
    await events.emit("drop.opened", {"drop_id": str(drop.id)}, db=db)
    pending = (
        await db.execute(
            select(func.count()).where(DropReminder.drop_id == drop.id, DropReminder.notified_at.is_(None))
        )
    ).scalar_one()
    if pending:
        await control.propose(
            "catalog.send_drop_reminders",
            f"Báo {pending} khách đã bấm «Nhắc mình»: {label(drop)} đã mở",
            {"drop_id": str(drop.id)},
            {"count": pending, "text": reminder_text(drop)},
            db=db,
            ref_type="drops",
            ref_id=drop.id,
            dedupe_key=f"drop-remind:{drop.id}",
            ai_generated=False,
        )
    return drop


def reminder_text(drop: Drop) -> str:
    from app.core.config import settings

    deadline = f", hạn chót {drop.closes_at:%d/%m}" if drop.closes_at else ""
    return (
        f"Hàng Chọn: {label(drop)} «{drop.title}» đã mở{deadline}. "
        f"Xem các món: {settings.web_base_url.rstrip('/')}/dot/{drop.slug}"
    )


async def send_reminders(db: AsyncSession, drop: Drop) -> int:
    rows = list(
        (
            await db.execute(
                select(DropReminder).where(DropReminder.drop_id == drop.id, DropReminder.notified_at.is_(None))
            )
        ).scalars()
    )
    driver = get_driver("notify")
    sent = 0
    for r in rows:
        res = await driver.send(OutboundNotification(channel=Channel.ZALO_OA, to=r.contact, text=reminder_text(drop)))
        if res.status != "failed":
            r.notified_at = now_utc()
            sent += 1
    await db.flush()
    return sent


async def close_drop(db: AsyncSession, drop: Drop, *, reason: str, user: User | None = None) -> Drop:
    if drop.status not in (DropStatus.OPEN, DropStatus.SCHEDULED):
        raise Conflict("Đợt này không ở trạng thái đang mở.")
    drop.status = DropStatus.CLOSED
    if drop.closes_at is None or drop.closes_at > now_utc():
        drop.closes_at = now_utc()
    await db.flush()
    await control.audit(db, "catalog.drop_closed", user=user, entity_type="drops", entity_id=drop.id,
                        summary=f"Đóng {label(drop)} ({reason})")  # fmt: skip
    await events.emit("drop.closed", {"drop_id": str(drop.id)}, db=db)
    return drop


async def mark_arrived(db: AsyncSession, drop: Drop, arrived_on: date, user: User) -> Drop:
    if drop.status not in (DropStatus.CLOSED, DropStatus.SOURCING, DropStatus.ARRIVING):
        raise Conflict("Chỉ đánh dấu hàng về cho đợt đã đóng.")
    drop.status = DropStatus.FULFILLING
    drop.actual_arrival_date = arrived_on
    await control.audit(db, "catalog.drop_arrived", user=user, entity_type="drops", entity_id=drop.id,
                        summary=f"{label(drop)}: hàng đã về {arrived_on:%d/%m}")  # fmt: skip
    await db.flush()
    return drop


async def cancel_drop(db: AsyncSession, drop: Drop, user: User) -> Drop:
    if drop.status not in (*OPENABLE, DropStatus.SCHEDULED):
        raise Conflict("Đợt đã mở thì đóng đợt, không huỷ.")
    drop.status = DropStatus.CANCELLED
    await control.cancel_pending(db, action="catalog.open_drop", dedupe_key=f"drop:{drop.id}")
    await control.audit(db, "catalog.drop_cancelled", user=user, entity_type="drops", entity_id=drop.id,
                        summary=f"Huỷ {label(drop)}")  # fmt: skip
    await db.flush()
    return drop


def sold_out(drop: Drop) -> bool:
    limited = [i for i in drop.items if i.slots_total is not None]
    return (
        bool(drop.items) and len(limited) == len(drop.items) and all(i.slots_reserved >= i.slots_total for i in limited)
    )


async def tick(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Cron: mở đợt đã tới giờ, đóng đợt hết hạn hoặc hết suất. Chạy lại không sinh trùng (theo trạng thái)."""
    now = now or now_utc()
    opened = closed = 0
    due = (await db.execute(select(Drop).where(Drop.status == DropStatus.SCHEDULED, Drop.opens_at <= now))).scalars()
    for d in list(due):
        # hết giờ trước khi kịp mở vẫn mở rồi đóng ngay bên dưới, để bên nghe nhận đủ hai sự kiện
        await _open_now(db, d)
        opened += 1
    open_drops = (await db.execute(select(Drop).where(Drop.status == DropStatus.OPEN))).scalars()
    for d in list(open_drops):
        if (d.closes_at and d.closes_at <= now) or sold_out(d):
            await close_drop(db, d, reason="hết hạn" if d.closes_at and d.closes_at <= now else "hết suất")
            closed += 1
    return {"opened": opened, "closed": closed}


async def add_reminder(db: AsyncSession, drop: Drop, contact: str) -> bool:
    if drop.status not in (DropStatus.SCHEDULED, DropStatus.DRAFT, DropStatus.PENDING_REVIEW):
        raise Conflict("Đợt này đã mở rồi, bạn vào đặt luôn nhé.", code="drop_already_open")
    norm = normalize_contact(contact)
    if len(norm) < 6:
        raise BadRequest("Bạn để lại số điện thoại hoặc Zalo giúp mình.")
    stmt = (
        pg_insert(DropReminder)
        .values(
            id=uuid.uuid4(), drop_id=drop.id, contact=norm, contact_key=hash_key("drop-remind", norm), channel="zalo"
        )
        .on_conflict_do_nothing(constraint="uq_drop_reminders_contact")
        .returning(DropReminder.id)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def recount_slots(db: AsyncSession, drop_item_ids: list[uuid.UUID]) -> None:
    """Số suất đã đặt = tổng số lượng các dòng đơn đã trả tiền (đặt cọc) và chưa huỷ. Tính lại → chạy lặp không sai."""
    from app.modules.orders.models import Order, OrderItem, OrderStatus, PaymentState

    if not drop_item_ids:
        return
    rows = (
        await db.execute(
            select(OrderItem.drop_item_id, func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.drop_item_id.in_(drop_item_ids),
                Order.payment_state.in_((PaymentState.PAID, PaymentState.PARTIALLY_PAID)),
                Order.status.not_in((OrderStatus.CANCELLED, OrderStatus.RETURNED)),
            )
            .group_by(OrderItem.drop_item_id)
        )
    ).all()
    counted = {r[0]: int(r[1]) for r in rows}
    for iid in drop_item_ids:
        it = await db.get(DropItem, iid)
        if it is not None:
            it.slots_reserved = counted.get(iid, 0)
    await db.flush()
