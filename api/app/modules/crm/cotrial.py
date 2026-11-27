"""«Mời thử cùng» (27/11): sổ người dùng thử + lời mời theo món đang thử + chọn người + cảm nhận + hoàn tiền.

- Sổ người dùng thử (`tester_profiles`): khách đăng ký một lần ở /dung-thu, đồng ý điều kiện (mua giá thường, gửi cảm
  nhận đúng hạn, gửi đủ thì được hoàn). Hồ sơ khách (bảng của orders) tạo/khớp qua sự kiện `customer.contact_submitted`,
  crm chỉ đọc lại theo số điện thoại / email.
- Lời mời (`cotrial_offers`) gắn một ứng viên đang mua mẫu / đang thử; link riêng /dung-thu/m/<token> không liệt kê ở
  đâu. Mỗi người đăng ký là một dòng `tester_invites` (offer_id ≠ null) — dùng lại link cảm nhận /thu-hang/<token> và sự
  kiện `tester.feedback_received` (cảm nhận thành ghi chú thử author=tester ở Bàn chọn, không bao giờ ra website).
- Tiền: chị xác nhận tay «đã nhận tiền» trên dòng đăng ký, KHÔNG tạo đơn (món chưa là sản phẩm, đơn sẽ làm lệch doanh
  thu / sổ sách / hồ sơ bán). Hoàn tiền: cảm nhận đủ → `control.propose` (luôn hỏi chị); chị chuyển tay rồi duyệt.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core import events
from app.core.enums import Actor
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.money import format_vnd
from app.core.security import random_token
from app.core.storage import get_storage, new_key
from app.core.timeutil import now_utc, to_local
from app.integrations import IntegrationError
from app.modules.catalog.models import Category
from app.modules.control.models import User
from app.modules.crm.models import CotrialOffer, CotrialOfferStatus, TesterInvite, TesterInviteStatus, TesterProfile
from app.modules.crm.service import invite_link, notify, store_link
from app.modules.orders.models import Customer
from app.modules.orders.util import normalize_phone
from app.modules.selection.models import TrialNote
from app.modules.sourcing.models import Candidate, CandidateStage

log = logging.getLogger("app.crm")

ACTION_REFUND = "crm.cotrial_refund"
REMIND_BEFORE = timedelta(days=2)
MAX_OFFER_PHOTOS = 4
MAX_FEEDBACK_PHOTOS = 3
OFFER_STAGES = (CandidateStage.SAMPLE, CandidateStage.TRIAL)

S = TesterInviteStatus
# đã chiếm một suất (chị đã chọn); lỡ hạn vẫn tính vì hàng đã gửi
TAKEN = (S.SELECTED, S.PAID, S.SAMPLE_SENT, S.FEEDBACK_RECEIVED, S.REFUND_PROPOSED, S.REFUNDED, S.FEEDBACK_MISSED)
DONE = (S.FEEDBACK_RECEIVED, S.REFUND_PROPOSED, S.REFUNDED)
WOULD_BUY = {"yes": "Có, sẽ mua", "maybe": "Còn phân vân", "no": "Không mua"}


def offer_link(token: str) -> str:
    return store_link(f"/dung-thu/m/{token}")


def refund_amount(o: CotrialOffer) -> int:
    if o.refund_vnd is not None:
        return min(o.refund_vnd, o.price_vnd)
    return round(o.price_vnd * (o.refund_pct or 0) / 100)


def _contact(phone: str | None, email: str | None) -> tuple[str | None, str | None]:
    phone_n = normalize_phone(phone) if (phone or "").strip() else None
    email_n = (email or "").strip().lower() or None
    if email_n and ("@" not in email_n or len(email_n) > 254):
        raise BadRequest("Email chưa đúng, bạn kiểm tra lại giúp mình.", code="email_invalid")
    if not phone_n and not email_n:
        raise BadRequest("Bạn để lại số điện thoại (Zalo) hoặc email để mình báo nhé.", code="contact_required")
    return phone_n, email_n


async def _find_customer(db: AsyncSession, phone: str | None, email: str | None) -> Customer | None:
    """Đọc bảng khách của orders (chỉ đọc). Hồ sơ đã gộp → hồ sơ chính."""
    c = None
    if phone:
        c = (await db.execute(select(Customer).where(Customer.phone == phone))).scalar_one_or_none()
    if c is None and email:
        c = (
            await db.execute(
                select(Customer)
                .where(func.lower(Customer.email) == email, Customer.merged_into_id.is_(None))
                .order_by(Customer.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
    while c is not None and c.merged_into_id:
        c = await db.get(Customer, c.merged_into_id)
    return c


async def categories(db: AsyncSession) -> list[dict[str, str]]:
    rows = await db.execute(
        select(Category.slug, Category.name)
        .where(Category.is_active.is_(True), Category.parent_id.is_(None))
        .order_by(Category.position, Category.name)
    )
    return [{"slug": s, "name": n} for s, n in rows.all()]


async def _profile_of(db: AsyncSession, customer_id: uuid.UUID) -> TesterProfile | None:
    return (
        await db.execute(select(TesterProfile).where(TesterProfile.customer_id == customer_id))
    ).scalar_one_or_none()


async def signup(
    db: AsyncSession,
    *,
    name: str | None,
    phone: str | None,
    email: str | None,
    interests: list[str],
    agree: bool,
) -> tuple[Customer, TesterProfile]:
    """Đăng ký sổ người dùng thử (công khai). Đã có thì cập nhật nhóm quan tâm; không trả dữ liệu cũ ra ngoài."""
    if not agree:
        raise BadRequest("Bạn đọc và đồng ý điều kiện dùng thử giúp mình nhé.", code="agree_required")
    name = (name or "").strip()[:120] or None
    if not name:
        raise BadRequest("Bạn cho mình xin tên gọi nhé.", code="name_required")
    phone_n, email_n = _contact(phone, email)
    known = {c["slug"] for c in await categories(db)}
    picked = [i for i in dict.fromkeys(interests) if i in known][:10]
    await events.emit("customer.contact_submitted", {"name": name, "phone": phone_n, "email": email_n}, db=db)
    c = await _find_customer(db, phone_n, email_n)
    if c is None:
        raise BadRequest("Chưa ghi được tên bạn, bạn thử lại sau ít phút nhé.", code="contact_failed")
    p = await _profile_of(db, c.id)
    if p is None:
        p = TesterProfile(customer_id=c.id, interests=picked, agreed_at=now_utc())
        db.add(p)
    else:
        p.interests = list(dict.fromkeys([*p.interests, *picked]))
        p.agreed_at = now_utc()
    await db.flush()
    await control.audit(db, "crm.tester_signed_up", actor=Actor.CUSTOMER, entity_type="tester_profiles",
                        entity_id=p.id)  # fmt: skip
    return c, p


# ---- lời mời theo món (desk) -------------------------------------------------------------------------------------


async def _copy_public(key: str, offer_id: uuid.UUID) -> dict[str, Any]:
    from app.modules.catalog import images as img_lib

    processed = img_lib.process_photo(await get_storage().get(key), enhance=False)  # xoay, cắt vuông, bỏ EXIF
    return {"files": await img_lib.store_renditions(f"public/cotrial/{offer_id}", processed)}


async def _picked_keys(db: AsyncSession, cand: Candidate, picks: list[dict[str, Any]]) -> list[str]:
    """Ảnh chị chọn: ảnh nhà cung cấp đã lưu bản sao (theo link gốc) hoặc ảnh chị chụp trong ghi chú thử của món này."""
    cache = {e.get("url"): e.get("key") for e in (cand.image_cache or []) if isinstance(e, dict) and e.get("key")}
    keys: list[str] = []
    for pk in picks[:MAX_OFFER_PHOTOS]:
        if pk.get("kind") == "supplier":
            key = cache.get(pk.get("ref"))
        else:
            note = await db.get(TrialNote, uuid.UUID(str(pk.get("ref"))))
            media = note.media if note and note.candidate_id == cand.id else []
            i = int(pk.get("index") or 0)
            key = media[i].get("storage_key") if 0 <= i < len(media) else None
        if not key:
            raise BadRequest("Có ảnh chị chọn chưa lưu về kho, chị chọn ảnh khác nhé.", code="image_unavailable")
        keys.append(key)
    return keys


async def create_offer(db: AsyncSession, candidate_id: uuid.UUID, data: dict[str, Any], user: User) -> CotrialOffer:
    cand = await db.get(Candidate, candidate_id)
    if cand is None:
        raise NotFound("Không tìm thấy món này.")
    if cand.stage not in OFFER_STAGES:
        raise BadRequest("Chỉ mời thử cùng món đang mua mẫu hoặc đang thử.", code="not_in_trial")
    price = int(data["price_vnd"])
    if (data.get("refund_vnd") is None) == (data.get("refund_pct") is None):
        raise BadRequest("Chị ghi số tiền hoàn hoặc % hoàn (một trong hai).", code="refund_required")
    if data.get("refund_vnd") is not None and int(data["refund_vnd"]) > price:
        raise BadRequest("Tiền hoàn không lớn hơn giá được.", code="refund_too_high")
    o = CotrialOffer(
        candidate_id=cand.id,
        token=random_token(18),
        title=(data.get("title") or cand.title_vi).strip()[:200],
        description=(data.get("description") or "").strip() or None,
        price_vnd=price,
        refund_vnd=data.get("refund_vnd"),
        refund_pct=data.get("refund_pct"),
        ask_price_vnd=data.get("ask_price_vnd"),
        slots=int(data.get("slots") or 3),
        feedback_days=int(data.get("feedback_days") or 10),
        created_by_id=user.id,
    )
    db.add(o)
    await db.flush()
    o.photos = [await _copy_public(k, o.id) for k in await _picked_keys(db, cand, data.get("images") or [])]
    await control.audit(db, "crm.cotrial_offer_created", user=user, entity_type="cotrial_offers", entity_id=o.id,
                        summary=f"Mời thử cùng: {o.title}")  # fmt: skip
    await db.flush()
    return o


async def get_offer(db: AsyncSession, offer_id: uuid.UUID) -> CotrialOffer:
    o = await db.get(CotrialOffer, offer_id)
    if o is None:
        raise NotFound("Không tìm thấy lời mời.")
    return o


async def update_offer(db: AsyncSession, offer_id: uuid.UUID, data: dict[str, Any], user: User) -> CotrialOffer:
    o = await get_offer(db, offer_id)
    for k in ("title", "description", "slots", "feedback_days"):
        if data.get(k) is not None:
            setattr(o, k, data[k].strip() if isinstance(data[k], str) else data[k])
    if data.get("status") is not None:
        o.status = CotrialOfferStatus(data["status"])
    await control.audit(db, "crm.cotrial_offer_updated", user=user, entity_type="cotrial_offers", entity_id=o.id,
                        data={k: v for k, v in data.items() if v is not None})  # fmt: skip
    await db.flush()
    return o


async def offers(db: AsyncSession, candidate_id: uuid.UUID | None = None) -> list[CotrialOffer]:
    q = select(CotrialOffer).order_by(CotrialOffer.created_at.desc())
    if candidate_id:
        q = q.where(CotrialOffer.candidate_id == candidate_id)
    return list((await db.execute(q.limit(200))).scalars())


async def applications(db: AsyncSession, offer_ids: list[uuid.UUID]) -> list[TesterInvite]:
    if not offer_ids:
        return []
    return list(
        (
            await db.execute(
                select(TesterInvite).where(TesterInvite.offer_id.in_(offer_ids)).order_by(TesterInvite.created_at)
            )
        ).scalars()
    )


def taken(apps: list[TesterInvite]) -> int:
    return sum(a.status in TAKEN for a in apps)


async def history(db: AsyncSession, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Lịch sử để chị chọn người: số đơn, lần thử cùng đã gửi đủ cảm nhận / lỡ hạn / bỏ ngang (chọn rồi không trả)."""
    out = {cid: {"orders": 0, "trials": 0, "completed": 0, "missed": 0, "dropped": 0} for cid in customer_ids}
    if not customer_ids:
        return out
    for cid, n in (
        await db.execute(select(Customer.id, Customer.order_count).where(Customer.id.in_(customer_ids)))
    ).all():
        out[cid]["orders"] = n
    rows = await db.execute(
        select(TesterInvite.customer_id, TesterInvite.status, TesterInvite.selected_at, TesterInvite.paid_at).where(
            TesterInvite.customer_id.in_(customer_ids), TesterInvite.offer_id.is_not(None)
        )
    )
    for cid, st, selected_at, paid_at in rows.all():
        h = out[cid]
        if st in DONE:
            h["completed"] += 1
        elif st == S.FEEDBACK_MISSED:
            h["missed"] += 1
        elif selected_at and not paid_at and st in (S.DECLINED, S.CLOSED):
            h["dropped"] += 1
        if st in TAKEN or (selected_at and st in (S.DECLINED, S.CLOSED)):
            h["trials"] += 1
    return out


async def profiles_of(db: AsyncSession, customer_ids: list[uuid.UUID]) -> dict[uuid.UUID, TesterProfile]:
    if not customer_ids:
        return {}
    rows = await db.execute(select(TesterProfile).where(TesterProfile.customer_id.in_(customer_ids)))
    return {p.customer_id: p for p in rows.scalars()}


# ---- công khai: link riêng của lời mời ---------------------------------------------------------------------------


async def offer_by_token(db: AsyncSession, token: str) -> CotrialOffer:
    o = (await db.execute(select(CotrialOffer).where(CotrialOffer.token == token))).scalar_one_or_none()
    if o is None or o.status != CotrialOfferStatus.OPEN:
        raise NotFound("Lời mời này không còn mở.")  # cùng một câu cho link sai và link đã đóng
    return o


async def apply(
    db: AsyncSession,
    token: str,
    *,
    name: str | None,
    phone: str | None,
    email: str | None,
    interests: list[str],
    agree: bool,
    note: str | None,
) -> TesterInvite:
    """Người xem link đăng ký thử món này; chưa có trong sổ thì vào sổ luôn (cùng lúc)."""
    o = await offer_by_token(db, token)
    if taken(await applications(db, [o.id])) >= o.slots:
        raise Conflict("Món này đã đủ người thử rồi, lần sau mình mời bạn nhé.", code="full")
    if not agree:
        raise BadRequest("Bạn đọc và đồng ý điều kiện dùng thử giúp mình nhé.", code="agree_required")
    phone_n, email_n = _contact(phone, email)
    c = await _find_customer(db, phone_n, email_n)
    profile = await _profile_of(db, c.id) if c else None
    if profile is None:
        c, profile = await signup(db, name=name, phone=phone_n, email=email_n, interests=interests, agree=agree)
    else:
        profile.agreed_at = now_utc()
    if await db.scalar(
        select(TesterInvite.id).where(TesterInvite.candidate_id == o.candidate_id, TesterInvite.customer_id == c.id)
    ):
        raise Conflict("Bạn đã đăng ký thử món này rồi, mình sẽ báo khi chọn xong nhé.", code="already_applied")
    inv = TesterInvite(
        candidate_id=o.candidate_id, customer_id=c.id, offer_id=o.id, token=random_token(18), status=S.APPLIED,
        message=(note or "").strip()[:1000] or None, responded_at=now_utc(),
    )  # fmt: skip
    db.add(inv)
    await db.flush()
    await control.audit(db, "crm.cotrial_applied", actor=Actor.CUSTOMER, entity_type="tester_invites",
                        entity_id=inv.id)  # fmt: skip
    return inv


# ---- chọn người, tiền, gửi hàng (desk) ---------------------------------------------------------------------------


async def _app(db: AsyncSession, invite_id: uuid.UUID) -> tuple[TesterInvite, CotrialOffer]:
    inv = await db.get(TesterInvite, invite_id)
    if inv is None or inv.offer_id is None:
        raise NotFound("Không tìm thấy người đăng ký.")
    return inv, await get_offer(db, inv.offer_id)


def _bad_step() -> Conflict:
    return Conflict("Không chuyển sang bước này được.", code="invalid_transition")


async def _tell(db: AsyncSession, inv: TesterInvite, text: str, kind: str) -> bool:
    c = await db.get(Customer, inv.customer_id)
    if c is None:
        return False
    try:
        await notify(db, c, text, link=invite_link(inv.token), kind=kind)
        return True
    except (IntegrationError, BadRequest) as e:
        log.info("Chưa báo được người dùng thử %s: %s", inv.id, e)
        return False


async def change(
    db: AsyncSession, invite_id: uuid.UUID, action: str, user: User, *, override: bool = False
) -> TesterInvite:
    inv, o = await _app(db, invite_id)
    now = now_utc()
    if action == "select":
        if inv.status not in (S.APPLIED, S.DECLINED):
            raise _bad_step()
        if taken(await applications(db, [o.id])) >= o.slots:
            raise Conflict(f"Đã chọn đủ {o.slots} người. Chị bỏ chọn ai đó hoặc tăng số suất.", code="full")
        profile = await _profile_of(db, inv.customer_id)
        if profile and profile.excluded and not override:
            raise Conflict(
                f"Người này đang bị loại trừ: {profile.excluded_reason or 'lỡ hạn gửi cảm nhận'}. Chị vẫn chọn thì xác nhận.",
                code="excluded",
            )
        inv.status, inv.selected_at = S.SELECTED, now
        await _tell(
            db, inv,
            f"Chào bạn, mình chọn bạn dùng thử «{o.title}» cùng mình. Giá {format_vnd(o.price_vnd)}; nhận hàng rồi "
            f"gửi cảm nhận đủ trong {o.feedback_days} ngày thì mình hoàn {format_vnd(refund_amount(o))}. Mình nhắn "
            f"riêng cách chuyển khoản nhé. Xem lại và gửi cảm nhận ở: {invite_link(inv.token)}",
            "cotrial_selected",
        )  # fmt: skip
    elif action == "decline":
        if inv.status not in (S.APPLIED, S.SELECTED):
            raise _bad_step()
        inv.status = S.DECLINED
    elif action == "paid":
        if inv.status != S.SELECTED:
            raise _bad_step()
        inv.status, inv.paid_at, inv.paid_vnd = S.PAID, now, o.price_vnd
    elif action == "shipped":
        if inv.status != S.PAID:
            raise _bad_step()
        inv.status, inv.sample_sent_at = S.SAMPLE_SENT, now
        inv.feedback_due_at = now + timedelta(days=o.feedback_days)
    elif action == "propose_refund":  # chị trả lại đề xuất trước đó, giờ đề xuất lại
        if inv.status != S.FEEDBACK_RECEIVED:
            raise _bad_step()
        await propose_refund(db, inv, o)
    else:
        raise BadRequest("Thao tác không hợp lệ.")
    await control.audit(db, f"crm.cotrial_{action}", user=user, entity_type="tester_invites", entity_id=inv.id,
                        data={"override": override} if override else None)  # fmt: skip
    await db.flush()
    return inv


# ---- cảm nhận + hoàn tiền ----------------------------------------------------------------------------------------


async def submit_feedback(
    db: AsyncSession,
    token: str,
    *,
    rating: int,
    liked: str,
    disliked: str,
    would_buy: str,
    refund_account: str | None,
    photos: list[tuple[bytes, str]],
) -> TesterInvite:
    """Người dùng thử gửi cảm nhận một lần (công khai). Đủ câu trả lời → đề xuất hoàn tiền vào hàng chờ của chị."""
    inv = (await db.execute(select(TesterInvite).where(TesterInvite.token == token))).scalar_one_or_none()
    if inv is None or inv.offer_id is None:
        raise NotFound("Đường link này không còn dùng được.")
    o = await get_offer(db, inv.offer_id)
    if inv.status in DONE:
        raise Conflict("Cảm nhận đã được gửi rồi, cảm ơn bạn!", code="feedback_done")
    if inv.status == S.FEEDBACK_MISSED or (inv.feedback_due_at and now_utc() > inv.feedback_due_at):
        raise Conflict("Đã quá hạn gửi cảm nhận nên mình không hoàn tiền được, mong bạn thông cảm.", code="missed")
    if inv.status != S.SAMPLE_SENT:
        raise Conflict("Mình chưa gửi hàng cho bạn nên chưa gửi cảm nhận được.", code="not_shipped")
    liked, disliked = liked.strip(), disliked.strip()
    if not liked or not disliked or would_buy not in WOULD_BUY:
        raise BadRequest("Bạn trả lời đủ các câu giúp mình nhé (ảnh thì không bắt buộc).", code="incomplete")
    media = []
    for data, ctype in photos[:MAX_FEEDBACK_PHOTOS]:
        stored = await get_storage().put(new_key("private/cotrial-feedback", ctype.split("/")[-1]), data, ctype)
        media.append({"storage_key": stored.key, "content_type": ctype, "size": stored.size})
    ask = o.ask_price_vnd or o.price_vnd
    inv.feedback_answers = {
        "liked": liked[:2000], "disliked": disliked[:2000], "would_buy": would_buy, "ask_price_vnd": ask,
        "refund_account": (refund_account or "").strip()[:300] or None,
    }  # fmt: skip
    inv.feedback = f"Thích: {liked}\nChưa ưng: {disliked}\nGiá {format_vnd(ask)}: {WOULD_BUY[would_buy]}"[:4000]
    inv.feedback_rating = rating
    inv.feedback_media = media
    inv.feedback_at = now_utc()
    inv.status = S.FEEDBACK_RECEIVED
    c = await db.get(Customer, inv.customer_id)
    await events.emit(
        "tester.feedback_received",
        {"tester_invite_id": str(inv.id), "candidate_id": str(inv.candidate_id), "customer_id": str(inv.customer_id),
         "customer_name": c.name if c else None, "feedback": inv.feedback, "rating": rating},
        db=db,
    )  # fmt: skip
    await propose_refund(db, inv, o, customer=c)
    await control.audit(db, "crm.cotrial_feedback", actor=Actor.CUSTOMER, entity_type="tester_invites",
                        entity_id=inv.id)  # fmt: skip
    await db.flush()
    return inv


async def propose_refund(
    db: AsyncSession, inv: TesterInvite, o: CotrialOffer, *, customer: Customer | None = None
) -> None:
    c = customer or await db.get(Customer, inv.customer_id)
    amount = refund_amount(o)
    who = (c.name if c else None) or "người dùng thử"
    out = await control.propose(
        ACTION_REFUND,
        f"Hoàn tiền dùng thử: {who} · {o.title}",
        {"tester_invite_id": str(inv.id), "refund_vnd": amount},
        {
            "customer": who, "phone": c.phone if c else None, "email": c.email if c else None,
            "refund_vnd": amount, "paid_vnd": inv.paid_vnd, "refund_account": inv.feedback_answers.get("refund_account"),
            "rating": inv.feedback_rating, "feedback": inv.feedback,
        },
        db=db,
        summary=f"Cảm nhận đã đủ. Chị chuyển hoàn {format_vnd(amount)} rồi bấm duyệt để ghi «đã hoàn».",
        ref_type="tester_invites", ref_id=inv.id, dedupe_key=f"cotrial-refund:{inv.id}", ai_generated=False,
    )  # fmt: skip
    inv.refund_vnd = amount
    if out.status == "pending":
        inv.status = S.REFUND_PROPOSED
        inv.refund_approval_id = out.item_id


async def apply_refund(db: AsyncSession, invite_id: uuid.UUID, amount: int) -> TesterInvite:
    """Chị đã chuyển hoàn tay và duyệt (handler của ACTION_REFUND)."""
    inv = await db.get(TesterInvite, invite_id)
    if inv is None:
        raise NotFound("Không tìm thấy người dùng thử.")
    if inv.status == S.REFUNDED:
        return inv
    if inv.status not in (S.REFUND_PROPOSED, S.FEEDBACK_RECEIVED):
        raise Conflict("Người này chưa tới bước hoàn tiền.", code="invalid_transition")
    inv.status, inv.refund_vnd, inv.refunded_at = S.REFUNDED, amount, now_utc()
    await db.flush()
    return inv


async def refund_returned(db: AsyncSession, invite_id: uuid.UUID) -> None:
    inv = await db.get(TesterInvite, invite_id)
    if inv is not None and inv.status == S.REFUND_PROPOSED:
        inv.status = S.FEEDBACK_RECEIVED
        inv.refund_approval_id = None


# ---- hạn cảm nhận: nhắc trước hạn, quá hạn thì loại trừ ---------------------------------------------------------


async def mark_missed(db: AsyncSession, inv: TesterInvite, o: CotrialOffer) -> None:
    if inv.status != S.SAMPLE_SENT:
        return
    inv.status = S.FEEDBACK_MISSED
    profile = await _profile_of(db, inv.customer_id)
    if profile is not None:
        due = to_local(inv.feedback_due_at).strftime("%d/%m") if inv.feedback_due_at else ""
        profile.excluded = True
        profile.excluded_reason = f"Lỡ hạn gửi cảm nhận «{o.title}» ({due})"[:300]
    await control.audit(db, "crm.cotrial_feedback_missed", actor=Actor.SYSTEM, entity_type="tester_invites",
                        entity_id=inv.id)  # fmt: skip
    await db.flush()


async def run_deadlines(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    now = now or now_utc()
    rows = list(
        (
            await db.execute(
                select(TesterInvite).where(
                    TesterInvite.offer_id.is_not(None),
                    TesterInvite.status == S.SAMPLE_SENT,
                    TesterInvite.feedback_due_at.is_not(None),
                )
            )
        ).scalars()
    )
    stats = {"reminded": 0, "missed": 0}
    for inv in rows:
        o = await get_offer(db, inv.offer_id)  # type: ignore[arg-type]
        assert inv.feedback_due_at is not None
        if now > inv.feedback_due_at:
            await mark_missed(db, inv, o)
            stats["missed"] += 1
        elif inv.reminded_at is None and inv.feedback_due_at - now <= REMIND_BEFORE:
            due = to_local(inv.feedback_due_at).strftime("%d/%m")
            await _tell(
                db, inv,
                f"Bạn ơi, hạn gửi cảm nhận «{o.title}» là ngày {due}. Gửi đủ là mình hoàn "
                f"{format_vnd(refund_amount(o))} nhé: {invite_link(inv.token)}",
                "cotrial_reminder",
            )  # fmt: skip
            inv.reminded_at = now
            stats["reminded"] += 1
    await db.flush()
    return stats


async def set_excluded(db: AsyncSession, profile_id: uuid.UUID, excluded: bool, user: User) -> TesterProfile:
    p = await db.get(TesterProfile, profile_id)
    if p is None:
        raise NotFound("Không tìm thấy người dùng thử.")
    p.excluded = excluded
    if not excluded:
        p.excluded_reason = None
    await control.audit(db, "crm.tester_excluded" if excluded else "crm.tester_included", user=user,
                        entity_type="tester_profiles", entity_id=p.id)  # fmt: skip
    await db.flush()
    return p


async def registry(db: AsyncSession) -> list[tuple[TesterProfile, Customer]]:
    rows = await db.execute(
        select(TesterProfile, Customer)
        .join(Customer, Customer.id == TesterProfile.customer_id)
        .order_by(TesterProfile.created_at.desc())
        .limit(500)
    )
    return [(p, c) for p, c in rows.all()]
