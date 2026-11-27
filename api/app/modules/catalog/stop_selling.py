"""«Ngừng bán trên mọi kênh» và «Mở bán lại» một món.

Chị bấm «Ngừng bán» → màn liệt kê mọi nơi món đang có (website, lịch đăng chưa đăng, bài đã đăng, sàn, đợt đang mở) →
một lần xác nhận → hành động `catalog.stop_selling` đi qua `control.propose` rồi chị duyệt ngay (một mục trong hàng chờ
và một dòng nhật ký, hoàn tác = «Mở bán lại"):

- website: catalog đặt `products.status = stopped` (mọi nơi đọc «đang bán» chỉ lấy `published`, nên đồng bộ sàn, đăng
  bài tự động, đợt mới, trang đợt đều bỏ món này);
- bài đăng: content nghe `product.sale_stop_requested` (huỷ lịch, ẩn / xoá hẳn / ghi «đã gỡ tay» bài đã đăng);
- sàn: orders nghe cùng sự kiện (ngừng bán qua API, sàn chưa có lệnh thì đặt tồn về 0);
- đợt đang mở: không tự đóng (đóng đợt đã có đơn là việc chị quyết), chỉ báo kèm link.

Bên nghe ghi kết quả vào bảng của mình (`scheduled_posts.removal`, `marketplace_listings.data["stop"]`); catalog đọc
lại để báo từng bước. Dữ liệu hoàn tác (`undo_data`) ghi đúng thứ đã làm: trạng thái website trước đó, bài đã ẩn,
món sàn đã ngừng — «Mở bán lại» chỉ khôi phục đúng những thứ đó."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core import events
from app.core.errors import BadRequest, Conflict
from app.core.timeutil import VN_TZ, now_utc, to_local
from app.integrations.marketplaces import driver_for as marketplace_driver
from app.integrations.social import driver_for as social_driver
from app.modules.catalog.models import Drop, DropItem, DropStatus, Product, ProductStatus
from app.modules.catalog.tracking import CHANNEL_LABELS, DROP_STATUS_LABELS
from app.modules.content.models import PostStatus, ScheduledPost
from app.modules.control.models import AIActivity, ApprovalStatus, User
from app.modules.orders.models import ListingStatus, MarketplaceListing

ACTION = "catalog.stop_selling"
STOPPABLE = (ProductStatus.PUBLISHED, ProductStatus.PAUSED)
SCHEDULED = (PostStatus.PLANNED, PostStatus.APPROVED, PostStatus.FAILED)
LIVE = (PostStatus.PUBLISHED, PostStatus.DRAFT_PUSHED)
OPEN_DROPS = (DropStatus.PENDING_REVIEW, DropStatus.SCHEDULED, DropStatus.OPEN)
LISTED = (ListingStatus.ACTIVE, ListingStatus.INACTIVE, ListingStatus.ERROR, ListingStatus.PENDING)


def _label(ch: Any) -> str:
    return CHANNEL_LABELS.get(ch, getattr(ch, "value", str(ch)))


def _overdue(posts: list[ScheduledPost]) -> list[ScheduledPost]:
    """Bài chị giữ lại khi ngừng bán, đã quá giờ hẹn: mở bán lại không tự đăng, hỏi chị trước."""
    now = now_utc()
    return [x for x in posts if x.status == PostStatus.APPROVED and x.scheduled_at <= now]


def _post_row(x: ScheduledPost) -> dict[str, Any]:
    d = social_driver(x.channel)
    modes = d.remove_modes(x.channel)
    return {
        "id": x.id, "channel": x.channel.value, "label": _label(x.channel), "status": x.status.value,
        "url": x.external_url, "scheduled_at": x.scheduled_at, "published_at": x.published_at,
        "can_hide": "hide" in modes, "can_delete": "delete" in modes, "simulated": d.name == "mock",
    }  # fmt: skip


async def _rows(db: AsyncSession, p: Product) -> dict[str, Any]:
    posts = list(
        (
            await db.execute(
                select(ScheduledPost)
                .where(ScheduledPost.product_id == p.id, ScheduledPost.status.in_(SCHEDULED + LIVE))
                .order_by(ScheduledPost.scheduled_at)
            )
        ).scalars()
    )
    listings = list(
        (
            await db.execute(
                select(MarketplaceListing).where(
                    MarketplaceListing.product_id == p.id, MarketplaceListing.external_id.is_not(None),
                    MarketplaceListing.status.in_(LISTED),
                )
            )
        ).scalars()
    )  # fmt: skip
    drops = (
        await db.execute(
            select(Drop, DropItem)
            .join(DropItem, DropItem.drop_id == Drop.id)
            .where(DropItem.product_id == p.id, Drop.status.in_(OPEN_DROPS))
            .order_by(Drop.created_at.desc())
        )
    ).all()
    return {
        "scheduled": [x for x in posts if x.status in SCHEDULED],
        "live": [x for x in posts if x.status in LIVE],
        "listings": listings,
        "drops": drops,
    }


def _listing_row(li: MarketplaceListing) -> dict[str, Any]:
    d = marketplace_driver(li.marketplace)
    return {
        "id": li.id, "marketplace": li.marketplace.value, "label": _label(li.marketplace), "status": li.status.value,
        "external_id": li.external_id, "auto": bool(getattr(d, "supports_deactivate", False)),
        "simulated": d.name == "mock",
    }  # fmt: skip


def _drop_row(d: Drop, it: DropItem) -> dict[str, Any]:
    return {
        "id": d.id, "code": d.code, "title": d.title, "status": d.status.value,
        "status_label": DROP_STATUS_LABELS.get(d.status, d.status.value), "slots_reserved": it.slots_reserved or 0,
    }  # fmt: skip


async def latest(db: AsyncSession, product_id: uuid.UUID) -> AIActivity | None:
    return (
        await db.execute(
            select(AIActivity)
            .where(AIActivity.action == ACTION, AIActivity.ref_id == product_id)
            .order_by(AIActivity.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def plan(db: AsyncSession, p: Product) -> dict[str, Any]:
    r = await _rows(db, p)
    act = await latest(db, p.id)
    last = None
    if act is not None:
        u = act.undo_data or {}
        last = {
            "activity_id": act.id, "at": act.created_at, "steps": (act.result or {}).get("steps", []),
            "undone_at": act.undone_at, "undoable": act.undoable and act.undone_at is None,
            "hidden_posts": len(u.get("hidden_post_ids") or []), "gone_posts": len(u.get("gone_post_ids") or []),
            "listings": len(u.get("listing_ids") or []), "cancelled_posts": len(u.get("cancelled_post_ids") or []),
        }  # fmt: skip
    return {
        "product_id": p.id,
        "status": p.status,
        "can_stop": p.status in STOPPABLE,
        "website_published": p.status == ProductStatus.PUBLISHED,
        "scheduled_posts": [_post_row(x) for x in r["scheduled"]],
        "posts": [_post_row(x) for x in r["live"]],
        "listings": [_listing_row(li) for li in r["listings"]],
        "drops": [_drop_row(d, it) for d, it in r["drops"]],
        "overdue_posts": [_post_row(x) for x in _overdue(r["scheduled"])] if p.status == ProductStatus.STOPPED else [],
        "last_stop": last,
    }


# ---- ngừng bán ---------------------------------------------------------------------------------------------------


async def stop(db: AsyncSession, p: Product, user: User, choice: dict[str, Any]) -> AIActivity:
    """Chị xác nhận ngừng bán: propose → chị duyệt ngay (owner) → handler chạy từng bước. Trả dòng nhật ký."""
    if p.status not in STOPPABLE:
        raise BadRequest("Món này không ở trạng thái đang bán." if p.status != ProductStatus.STOPPED
                         else "Món này đã ngừng bán rồi.", code="not_stoppable")  # fmt: skip
    r = await _rows(db, p)
    sched = {x.id for x in r["scheduled"]}
    live = {x.id for x in r["live"]}
    lids = {li.id for li in r["listings"]}
    cancel = [str(i) for i in dict.fromkeys(choice.get("cancel_post_ids") or []) if i in sched]
    remove = [
        {"id": str(c["id"]), "manual_done": bool(c.get("manual_done"))}
        for c in {c["id"]: c for c in choice.get("remove_posts") or []}.values()
        if c["id"] in live
    ]
    listing_ids = [str(i) for i in dict.fromkeys(choice.get("listing_ids") or []) if i in lids]
    delete = bool(choice.get("delete_posts"))
    payload = {
        "stop_id": str(uuid.uuid4()), "product_id": str(p.id), "user_id": str(user.id), "delete_posts": delete,
        "cancel_post_ids": cancel, "remove_posts": remove, "listing_ids": listing_ids,
    }  # fmt: skip
    preview = {
        "product": p.name, "website": p.status.value, "scheduled_posts": len(cancel), "posts": len(remove),
        "listings": len(listing_ids), "delete_posts": delete, "drops": [d.title for d, _ in r["drops"]],
        "kept": len(sched) + len(live) + len(lids) - len(cancel) - len(remove) - len(listing_ids),
    }  # fmt: skip
    out = await control.propose(
        ACTION, f"Ngừng bán «{p.name}» trên mọi kênh", payload, preview, db=db,
        summary=f"Website, {len(cancel)} lịch đăng, {len(remove)} bài đã đăng, {len(listing_ids)} sàn"
        + (" — xoá hẳn bài" if delete else ""),
        ref_type="products", ref_id=p.id, dedupe_key=f"stop:{p.id}", ai_generated=False,
    )  # fmt: skip
    if out.status == "blocked":
        raise BadRequest("Việc «Ngừng bán trên mọi kênh» đang tắt ở Mức tự chủ.", code="action_off")
    if out.status == "failed":
        raise BadRequest(out.error or "Chưa ngừng bán được.")
    if out.status == "pending" and out.item_id:
        item = await control.approve(db, out.item_id, user, note="Chị tự ngừng bán từ bàn làm việc")
        if item.status == ApprovalStatus.FAILED:
            raise BadRequest(item.error or "Chưa ngừng bán được.")
    act = await latest(db, p.id)
    assert act is not None
    return act


async def apply_stop(ctx: control.ActionContext) -> control.HandlerResult:
    pl = ctx.payload
    db = ctx.db
    p = await db.get(Product, uuid.UUID(pl["product_id"]))
    if p is None:
        raise Conflict("Sản phẩm không còn.")
    if p.status not in STOPPABLE:
        raise Conflict("Món này không còn ở trạng thái đang bán.", code="not_stoppable")
    r = await _rows(db, p)  # chụp trước khi gỡ: thứ chị bỏ tích là «giữ lại»
    # bài còn chờ duyệt luôn huỷ (kể cả bài vừa vào hàng chờ sau khi chị mở màn ngừng bán)
    waiting = [str(x.id) for x in r["scheduled"] if x.status == PostStatus.PLANNED]
    pl = {**pl, "cancel_post_ids": list(dict.fromkeys([*pl["cancel_post_ids"], *waiting]))}
    prev = p.status
    p.status = ProductStatus.STOPPED
    await db.flush()
    user = ctx.user or (await db.get(User, uuid.UUID(pl["user_id"])) if pl.get("user_id") else None)
    await control.audit(db, "catalog.product_stopped", user=user, entity_type="products", entity_id=p.id,
                        summary=f"Ngừng bán trên mọi kênh: {p.name}", data={"stop_id": pl["stop_id"]})  # fmt: skip
    await events.emit("product.sale_stop_requested", pl, db=db)
    steps, undo = await _stop_steps(db, pl, prev, r)
    counts = {s: sum(1 for x in steps if x["status"] == s) for s in ("done", "needs_manual", "failed")}
    summary = f"{counts['done']} bước xong" + (f", {counts['needs_manual']} cần chị gỡ tay" if counts["needs_manual"]
                                             else "") + (f", {counts['failed']} lỗi" if counts["failed"] else "")  # fmt: skip
    return control.HandlerResult(
        result={"stop_id": pl["stop_id"], "steps": steps, "counts": counts},
        undo={"stop_id": pl["stop_id"], "product_id": str(p.id), "prev_status": prev.value, **undo},
        summary=summary, ref_type="products", ref_id=p.id,
    )  # fmt: skip


def _step(kind: str, label: str, status: str, detail: str, **kw: Any) -> dict[str, Any]:
    return {"kind": kind, "label": label, "status": status, "detail": detail, "id": None, "channel": None,
            "url": None, **kw}  # fmt: skip


MISSING = "Bước này chưa chạy được (lỗi hệ thống), chị thử lại sau."


async def _stop_steps(
    db: AsyncSession, pl: dict[str, Any], prev: ProductStatus, r: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stop_id = pl["stop_id"]
    steps = [
        _step("website", "Website", "done", "Đã gỡ khỏi kệ website." if prev == ProductStatus.PUBLISHED
              else "Trang đã tạm ẩn từ trước, giữ ẩn."),
    ]  # fmt: skip
    undo: dict[str, Any] = {"hidden_post_ids": [], "gone_post_ids": [], "cancelled_post_ids": [], "listing_ids": []}
    cancel = set(pl["cancel_post_ids"])
    chosen = {c["id"]: c for c in pl["remove_posts"]}
    ids = [uuid.UUID(i) for i in [*cancel, *chosen]]
    posts = {
        str(x.id): x
        for x in (await db.execute(select(ScheduledPost).where(ScheduledPost.id.in_(ids)))).scalars()
    } if ids else {}  # fmt: skip
    for x in r["scheduled"]:
        sid = str(x.id)
        rm = (posts[sid].removal or {}) if sid in posts else {}
        waiting = (
            rm.get("prev_status") if rm.get("stop_id") == stop_id else x.status.value
        ) == PostStatus.PLANNED.value
        base = {"id": sid, "channel": x.channel.value,
                "label": f"{'Bài chờ duyệt' if waiting else 'Lịch đăng'} {_label(x.channel)}"}  # fmt: skip
        if sid not in cancel:
            steps.append(_step("scheduled_post", status="skipped", detail="Chị giữ lại (bài không đăng khi món đang "
                               "ngừng bán).", **base))  # fmt: skip
            continue
        if rm.get("stop_id") != stop_id:
            steps.append(_step("scheduled_post", status="failed", detail=MISSING, **base))
        elif rm.get("outcome") == "cancelled":
            undo["cancelled_post_ids"].append(sid)
            steps.append(_step("scheduled_post", status="done", detail="Đã huỷ bài chờ duyệt." if waiting
                               else "Đã huỷ lịch đăng.", **base))  # fmt: skip
        else:
            steps.append(_step("scheduled_post", status="failed", detail=rm.get("error") or MISSING, **base))
    for x in r["live"]:
        sid = str(x.id)
        base = {"id": sid, "channel": x.channel.value, "label": f"Bài {_label(x.channel)}", "url": x.external_url}
        if sid not in chosen:
            steps.append(_step("post", status="skipped", detail="Chị giữ lại bài này.", **base))
            continue
        rm = (posts[sid].removal or {}) if sid in posts else {}
        out = rm.get("outcome") if rm.get("stop_id") == stop_id else None
        if out == "hidden":
            undo["hidden_post_ids"].append(sid)
            steps.append(_step("post", status="done", detail="Đã ẩn bài; mở bán lại sẽ hiện lại.", **base))
        elif out in ("deleted", "manual"):
            undo["gone_post_ids"].append(sid)
            steps.append(_step("post", status="done", detail="Đã xoá hẳn bài (không khôi phục được)." if out ==
                               "deleted" else "Chị đã gỡ tay.", **base))  # fmt: skip
        elif out == "needs_manual":
            modes = social_driver(x.channel).remove_modes(x.channel)
            if x.status == PostStatus.DRAFT_PUSHED:
                why = "Bản nháp nằm trong app TikTok của chị — chị xoá nháp trong app."
            elif "delete" in modes and not pl.get("delete_posts"):
                why = f"{_label(x.channel)} không ẩn được bài, chỉ xoá hẳn; chị chưa chọn «Xoá hẳn» nên cần gỡ tay."
            else:
                why = f"{_label(x.channel)} chưa gỡ bài tự động được — chị gỡ tay theo link."
            steps.append(_step("post", status="needs_manual", detail=why, **base))
        else:
            steps.append(_step("post", status="failed", detail=rm.get("error") or MISSING, **base))
    lids = set(pl["listing_ids"])
    fresh = {
        str(li.id): li
        for li in (
            await db.execute(select(MarketplaceListing).where(MarketplaceListing.id.in_([uuid.UUID(i) for i in lids])))
        ).scalars()
    } if lids else {}  # fmt: skip
    for li in r["listings"]:
        sid = str(li.id)
        base = {"id": sid, "channel": li.marketplace.value, "label": _label(li.marketplace)}
        if sid not in lids:
            steps.append(_step("listing", status="skipped", detail="Chị giữ lại trên sàn (đồng bộ tồn dừng khi "
                               "món ngừng bán).", **base))  # fmt: skip
            continue
        rec = ((fresh[sid].data or {}).get("stop") or {}) if sid in fresh else {}
        out = rec.get("outcome") if rec.get("stop_id") == stop_id else None
        if out in ("deactivated", "stock_zero"):
            undo["listing_ids"].append(sid)
            steps.append(_step("listing", status="done", detail="Đã ngừng bán trên sàn." if out == "deactivated" else
                               "Sàn chưa có lệnh ngừng bán qua API nên đã đặt tồn về 0.", **base))  # fmt: skip
        else:
            steps.append(_step("listing", status="failed", detail=rec.get("error") or MISSING, **base))
    for d, it in r["drops"]:
        reserved = it.slots_reserved or 0
        steps.append(_step(
            "drop", f"Đợt {d.code}: {d.title}", "needs_manual",
            "Món đã ẩn khỏi trang đợt, khách không đặt thêm được"
            + (f"; {reserved} suất đã đặt vẫn giữ" if reserved else "")
            + ". Đóng đợt hay không là chị quyết.", id=str(d.id),
        ))  # fmt: skip
    return steps, undo


# ---- mở bán lại (hoàn tác) ---------------------------------------------------------------------------------------


async def undo_stop(ctx: control.UndoContext) -> None:
    u = ctx.undo
    db = ctx.db
    p = await db.get(Product, uuid.UUID(u["product_id"]))
    if p is None:
        raise Conflict("Sản phẩm không còn.")
    if p.status == ProductStatus.STOPPED:
        p.status = ProductStatus(u.get("prev_status") or ProductStatus.PUBLISHED.value)
        await db.flush()
    await events.emit(
        "product.sale_resume_requested",
        {"stop_id": u["stop_id"], "product_id": u["product_id"], "user_id": str(ctx.user.id) if ctx.user else None,
         "post_ids": u.get("hidden_post_ids") or [], "listing_ids": u.get("listing_ids") or [],
         "overdue": u.get("overdue") or []},
        db=db,
    )  # fmt: skip
    await control.audit(
        db, "catalog.product_resumed", user=ctx.user, entity_type="products", entity_id=p.id,
        summary=f"Mở bán lại: {p.name}", data={"stop_id": u["stop_id"], "steps": await resume_steps(db, u)},
    )  # fmt: skip


async def resume_steps(db: AsyncSession, u: dict[str, Any]) -> list[dict[str, Any]]:
    p = await db.get(Product, uuid.UUID(u["product_id"]))
    stopped = p is None or p.status == ProductStatus.STOPPED
    steps = [
        _step("website", "Website", "failed" if stopped else "done",
              "Món vẫn đang ngừng bán." if stopped else "Đã lên lại kệ website." if p.status == ProductStatus.PUBLISHED
              else "Trang về lại trạng thái tạm ẩn như trước khi ngừng bán."),
    ]  # fmt: skip
    hidden = [uuid.UUID(i) for i in u.get("hidden_post_ids") or []]
    gone = [uuid.UUID(i) for i in u.get("gone_post_ids") or []]
    rows = {
        x.id: x for x in (await db.execute(select(ScheduledPost).where(ScheduledPost.id.in_(hidden + gone)))).scalars()
    } if hidden or gone else {}  # fmt: skip
    for pid in hidden:
        x = rows.get(pid)
        if x is None:
            continue
        rm = x.removal or {}
        base = {"id": str(x.id), "channel": x.channel.value, "label": f"Bài {_label(x.channel)}", "url": x.external_url}
        if x.status == PostStatus.PUBLISHED and rm.get("restored_at"):
            steps.append(_step("post", status="done", detail="Đã hiện lại bài.", **base))
        else:
            steps.append(_step("post", status="failed", detail=rm.get("restore_error") or "Chưa hiện lại được bài.",
                               **base))  # fmt: skip
    for pid in gone:
        x = rows.get(pid)
        if x is None:
            continue
        steps.append(_step(
            "post", f"Bài {_label(x.channel)}", "info",
            "Bài đã gỡ khi ngừng bán, không hiện lại được — chị lên lịch bài mới ở xưởng nội dung.",
            id=str(x.id), channel=x.channel.value, url=f"/desk/noi-dung/san-pham/{u['product_id']}?kenh={x.channel.value}",
        ))  # fmt: skip
    prod_id = uuid.UUID(u["product_id"])
    for x in (await db.execute(select(ScheduledPost).where(ScheduledPost.product_id == prod_id))).scalars():
        rec = (x.removal or {}).get("resume") or {}
        if rec.get("stop_id") != u["stop_id"]:
            continue
        base = {"id": str(x.id), "channel": x.channel.value, "label": f"Bài quá giờ {_label(x.channel)}"}
        choice = rec.get("choice")
        if choice == "now" and x.status == PostStatus.APPROVED:
            steps.append(_step("scheduled_post", status="done", detail="Đăng ngay theo chị chọn (trong vài phút).",
                               **base))  # fmt: skip
        elif choice == "reschedule" and x.status == PostStatus.APPROVED:
            when = to_local(x.scheduled_at).strftime("%H:%M %d/%m")
            steps.append(_step("scheduled_post", status="done", detail=f"Đã hẹn lại lúc {when}.", **base))
        elif choice == "drop" and x.status == PostStatus.CANCELLED:
            steps.append(_step("scheduled_post", status="done", detail="Đã bỏ bài theo chị chọn.", **base))
        elif choice is None and x.status == PostStatus.CANCELLED:
            steps.append(_step("scheduled_post", status="info", detail="Bài đã quá giờ hẹn, chị chưa chọn cách xử lý "
                               "nên không đăng — chị đặt lịch lại ở xưởng nội dung.",
                               url=f"/desk/noi-dung/san-pham/{u['product_id']}", **base))  # fmt: skip
        else:
            steps.append(_step("scheduled_post", status="failed", detail="Bài đã đổi trạng thái, chưa xử lý được.",
                               **base))  # fmt: skip
    n = len(u.get("cancelled_post_ids") or [])
    if n:
        steps.append(_step("scheduled_post", "Lịch đăng", "info",
                           f"{n} lịch đăng đã huỷ không tự đặt lại — chị đặt lịch mới ở xưởng nội dung.",
                           url=f"/desk/noi-dung/san-pham/{u['product_id']}"))  # fmt: skip
    lids = [uuid.UUID(i) for i in u.get("listing_ids") or []]
    for li in (
        (await db.execute(select(MarketplaceListing).where(MarketplaceListing.id.in_(lids)))).scalars() if lids else []
    ):
        rec = (li.data or {}).get("stop") or {}
        base = {"id": str(li.id), "channel": li.marketplace.value, "label": _label(li.marketplace)}
        if rec.get("restored_at") and rec.get("stop_id") == u["stop_id"]:
            steps.append(_step("listing", status="done", detail=f"Đã mở bán lại, tồn {li.synced_stock or 0}.", **base))
        else:
            steps.append(_step("listing", status="failed", detail=rec.get("restore_error") or "Chưa mở bán lại được.",
                               **base))  # fmt: skip
    return steps


def _overdue_choices(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in raw:
        at = c.get("scheduled_at")
        if c["action"] == "reschedule":
            if at is None:
                raise BadRequest("Chị chọn giờ hẹn lại cho bài quá giờ nhé.", code="reschedule_time")
            at = at if at.tzinfo else at.replace(tzinfo=VN_TZ)
            if at <= now_utc():
                raise BadRequest("Giờ hẹn lại phải sau bây giờ.", code="reschedule_time")
        out.append({"id": str(c["id"]), "action": c["action"],
                    "scheduled_at": at.isoformat() if c["action"] == "reschedule" else None})  # fmt: skip
    return out


async def resume(
    db: AsyncSession, p: Product, user: User, overdue: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Chị bấm «Mở bán lại» = hoàn tác lần ngừng bán gần nhất (cùng đường với nút Hoàn tác ở Nhật ký AI).

    `overdue`: lựa chọn của chị cho bài đã quá giờ hẹn (`now` / `reschedule` + `scheduled_at` / `drop`); ghi vào
    dữ liệu hoàn tác để content đọc. Bài quá giờ chị chưa chọn (vd hoàn tác từ Nhật ký AI) không tự đăng."""
    if p.status != ProductStatus.STOPPED:
        raise BadRequest("Món này không ở trạng thái ngừng bán.", code="not_stopped")
    choices = _overdue_choices(overdue or [])
    act = await latest(db, p.id)
    if act is None or act.undone_at is not None or not act.undoable:
        # không còn dòng nhật ký để hoàn tác (hiếm): đưa về «tạm ẩn» để chị đăng lại trang ở xưởng nội dung
        p.status = ProductStatus.PAUSED
        await control.audit(db, "catalog.product_resumed", user=user, entity_type="products", entity_id=p.id,
                            summary=f"Mở bán lại (không có lần ngừng bán để hoàn tác): {p.name}")  # fmt: skip
        await db.flush()
        return [_step("website", "Website", "needs_manual", "Không thấy lần ngừng bán để hoàn tác: trang về «tạm ẩn», "
                      "chị đăng lại ở xưởng nội dung; bài và sàn chị kiểm tay.")]  # fmt: skip
    act.undo_data = {**(act.undo_data or {}), "overdue": choices}
    await db.flush()
    await control.undo(db, act.id, user)
    return await resume_steps(db, act.undo_data or {})
