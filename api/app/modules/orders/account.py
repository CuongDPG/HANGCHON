"""Đăng nhập của khách trên website («Của tôi» → Đơn của tôi) bằng mã một lần, `/api/store/account/**`.

Khách nhập số điện thoại hoặc email → máy chủ gửi mã 6 chữ số qua `notify` (loại tin `login_code`) → khách nhập mã →
cookie httpOnly `hc_customer` (khoá ký và claim riêng, không dùng được cho bàn làm việc), sống `CUSTOMER_SESSION_DAYS`.

- Không lộ ai đã mua: câu trả lời khi xin mã luôn như nhau. Chỉ **gửi** tin cho liên hệ đã có trong sổ khách / đơn
  (không tốn tin, không làm phiền người lạ), nhưng liên hệ nào cũng có một dòng mã để thời gian xử lý như nhau.
- Mã chỉ lưu bản băm HMAC, hết hạn sau 10 phút, sai `MAX_ATTEMPTS` lần thì bỏ; xin mã mới thì mã cũ hết hiệu lực.
- Giới hạn tần suất (`core.ratelimit`): xin mã theo IP và theo liên hệ; nhập mã theo IP và theo liên hệ (chỉ đếm lần sai).
- Đơn của khách: đăng nhập bằng số điện thoại → đơn có hồ sơ khách mang số đó **hoặc** người nhận là số đó (như tra
  cứu bằng SĐT + mã đơn). Đăng nhập bằng email → chỉ đơn của hồ sơ khách **không có số điện thoại** mang email đó:
  email trong sổ khách do khách tự điền ở form công khai (chưa xác minh), gắn vào hồ sơ có SĐT thì người khác điền
  email của mình vào là xem được đơn của chủ số đó.
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

import jwt
from fastapi import APIRouter, BackgroundTasks, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import settings
from app.core.db import DbSession
from app.core.enums import Channel
from app.core.errors import BadRequest, Unauthorized
from app.core.pagination import Page, Paginated, paginate
from app.core.security import hmac_sha256
from app.core.timeutil import now_utc
from app.integrations import notify as notify_api
from app.integrations.notify import OutboundNotification
from app.modules.orders import service
from app.modules.orders.models import Customer, CustomerLoginCode, Order, OrderStatus
from app.modules.orders.util import normalize_phone, order_access_token

log = logging.getLogger("app.orders.account")

router = APIRouter(prefix="/api/store/account", tags=["orders · store account"])

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
JWT_ALG = "HS256"
AUDIENCE = "hangchon-store"
LOGIN_KIND = "login_code"  # loại tin cho `notify` (ZNS: khoá trong ZALO_ZNS_TEMPLATES)

SENT_MESSAGE = (
    "Nếu số điện thoại hoặc email này đã đặt hàng ở Hàng Chọn, mình vừa gửi mã 6 chữ số tới đó. Mã dùng trong 10 phút."
)
WRONG_CODE = "Mã chưa đúng hoặc đã hết hạn. Bạn kiểm tra lại, hoặc xin mã mới nhé."
TOO_MANY = "Bạn thử nhiều lần quá, đợi một lúc rồi thử lại nhé."

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
Kind = Literal["phone", "email"]


# ---- schema --------------------------------------------------------------------------------------------------------


class CodeIn(BaseModel):
    contact: str = Field(min_length=3, max_length=254, description="Số điện thoại hoặc email")


class CodeOut(BaseModel):
    message: str
    expires_in: int
    dev_code: str | None = Field(default=None, description="Chỉ có ở dev/test (chưa nối kênh gửi tin thật)")


class VerifyIn(CodeIn):
    code: str = Field(min_length=4, max_length=10)


class MeOut(BaseModel):
    signed_in: bool
    kind: Kind | None = None
    contact: str | None = Field(default=None, description="Liên hệ đã che bớt, vd 090•••0101")


class MyOrder(BaseModel):
    code: str
    token: str
    status: OrderStatus
    status_label: str
    placed_at: datetime
    total_vnd: int
    items_summary: str
    item_count: int


# ---- liên hệ, mã, phiên --------------------------------------------------------------------------------------------


def parse_contact(raw: str) -> tuple[Kind, str]:
    text = (raw or "").strip()
    if "@" in text:
        email = text.lower()
        if len(email) > 254 or not EMAIL_RE.match(email):
            raise BadRequest("Email chưa đúng, bạn kiểm tra lại giúp mình.", code="email_invalid")
        return "email", email
    phone = normalize_phone(text)
    assert phone is not None
    return "phone", phone


def mask(kind: str, contact: str) -> str:
    if kind == "email":
        local, _, domain = contact.partition("@")
        return f"{local[:2]}•••@{domain}"
    return f"{contact[:3]}•••{contact[-4:]}"


def _secret() -> str:
    return settings.customer_session_secret or hmac_sha256(settings.jwt_secret, b"customer-session")


def _hash(contact: str, code: str) -> str:
    return hmac_sha256(_secret(), f"login:{contact}:{code}".encode())


def create_session_token(kind: str, contact: str) -> str:
    now = now_utc()
    payload = {
        "typ": "customer",
        "aud": AUDIENCE,
        "kind": kind,
        "sub": contact,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.customer_session_days)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALG)


def read_session(request: Request) -> tuple[Kind, str] | None:
    token = request.cookies.get(settings.customer_cookie_name)
    if not token:
        return None
    try:
        claims = jwt.decode(token, _secret(), algorithms=[JWT_ALG], audience=AUDIENCE)
    except jwt.PyJWTError:
        return None
    kind, sub = claims.get("kind"), claims.get("sub")
    if claims.get("typ") != "customer" or kind not in ("phone", "email") or not isinstance(sub, str) or not sub:
        return None
    return kind, sub


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.customer_cookie_name,
        token,
        max_age=settings.customer_session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )


async def _customer_ids(db: AsyncSession, kind: str, contact: str) -> list[uuid.UUID]:
    """Hồ sơ khách khớp liên hệ (kèm hồ sơ đã gộp vào chúng)."""
    if kind == "phone":
        cond = Customer.phone == contact
    else:
        cond = (func.lower(Customer.email) == contact) & Customer.phone.is_(None)
    ids = list((await db.execute(select(Customer.id).where(cond))).scalars())
    if ids:
        ids += list((await db.execute(select(Customer.id).where(Customer.merged_into_id.in_(ids)))).scalars())
    return ids


def _orders_filter(kind: str, contact: str, ids: list[uuid.UUID]) -> Any:
    conds = [Order.customer_id.in_(ids)] if ids else []
    if kind == "phone":
        conds.append(Order.recipient_phone == contact)
    return or_(*conds) if conds else None


async def _known(db: AsyncSession, kind: str, contact: str) -> bool:
    ids = await _customer_ids(db, kind, contact)
    if ids:
        return True
    cond = _orders_filter(kind, contact, ids)
    if cond is None:
        return False
    return bool(await db.scalar(select(Order.id).where(cond, Order.status != OrderStatus.DRAFT).limit(1)))


async def _deliver(kind: str, contact: str, code: str) -> None:
    text = f"Mã đăng nhập Hàng Chọn của bạn: {code}. Mã dùng trong 10 phút. Đừng đưa mã này cho ai."
    msg = OutboundNotification(
        channel=Channel.EMAIL if kind == "email" else Channel.ZALO_OA,
        to=contact,
        text=text,
        subject="Mã đăng nhập Hàng Chọn" if kind == "email" else None,
        kind=LOGIN_KIND,
        data={"ma_dang_nhap": code, "phone": contact if kind == "phone" else ""},
    )
    res = await notify_api.send(msg)
    if res.status == "failed":
        log.warning("Chưa gửi được mã đăng nhập (%s): %s", kind, res.error)


# ---- route ---------------------------------------------------------------------------------------------------------


@router.post("/code", response_model=CodeOut)
async def request_code(body: CodeIn, request: Request, db: DbSession, tasks: BackgroundTasks) -> CodeOut:
    """Xin mã đăng nhập. Câu trả lời như nhau dù liên hệ đã mua hay chưa."""
    kind, contact = parse_contact(body.contact)
    ip = ratelimit.client_ip(request)
    await ratelimit.limit(f"account:code:ip:{ip}", 10, 3600, TOO_MANY)
    await ratelimit.limit(f"account:code:{contact}", 3, 900, TOO_MANY)
    await ratelimit.limit(f"account:code:day:{contact}", 10, 86400, TOO_MANY)
    now = now_utc()
    await db.execute(
        update(CustomerLoginCode)
        .where(CustomerLoginCode.contact == contact, CustomerLoginCode.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        CustomerLoginCode(contact_kind=kind, contact=contact, code_hash=_hash(contact, code), expires_at=now + CODE_TTL)
    )
    if await _known(db, kind, contact):
        tasks.add_task(_deliver, kind, contact, code)  # gửi sau khi trả lời: thời gian trả lời không lộ gì
    return CodeOut(
        message=SENT_MESSAGE,
        expires_in=int(CODE_TTL.total_seconds()),
        dev_code=code if settings.allows_simulation else None,
    )


@router.post("/verify", response_model=MeOut)
async def verify_code(body: VerifyIn, request: Request, response: Response, db: DbSession) -> MeOut:
    kind, contact = parse_contact(body.contact)
    ip = ratelimit.client_ip(request)
    await ratelimit.limit(f"account:verify:ip:{ip}", 30, 900, TOO_MANY)
    fail_key = f"account:verify:{contact}"
    if not await ratelimit.hit(fail_key, 10, 3600, record=False):
        raise ratelimit.RateLimited(TOO_MANY)
    now = now_utc()
    row = (
        await db.execute(
            select(CustomerLoginCode)
            .where(
                CustomerLoginCode.contact == contact,
                CustomerLoginCode.consumed_at.is_(None),
                CustomerLoginCode.expires_at > now,
            )
            .order_by(CustomerLoginCode.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    given = re.sub(r"\D", "", body.code)
    if row is None or not secrets.compare_digest(row.code_hash, _hash(contact, given)):
        if row is not None:
            row.attempts += 1
            if row.attempts >= MAX_ATTEMPTS:
                row.consumed_at = now
            await db.commit()  # lỗi bên dưới làm phiên rollback: giữ số lần sai
        await ratelimit.hit(fail_key, 10, 3600)
        raise BadRequest(WRONG_CODE, code="code_invalid")
    row.consumed_at = now
    _set_cookie(response, create_session_token(kind, contact))
    return MeOut(signed_in=True, kind=kind, contact=mask(kind, contact))


@router.get("/me", response_model=MeOut)
async def me(request: Request) -> MeOut:
    """Chưa đăng nhập vẫn trả 200 (`signed_in=false`) để trình duyệt không báo lỗi 401 ở mọi lần mở trang."""
    s = read_session(request)
    if s is None:
        return MeOut(signed_in=False)
    return MeOut(signed_in=True, kind=s[0], contact=mask(*s))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response.delete_cookie(settings.customer_cookie_name, path="/", domain=settings.cookie_domain)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/orders", response_model=Paginated[MyOrder])
async def my_orders(request: Request, db: DbSession, page: Page) -> Paginated[MyOrder]:
    """Đơn của khách đang đăng nhập (mới nhất trước), kèm mã xem đơn để mở trang theo dõi `/don/[code]`."""
    s = read_session(request)
    if s is None:
        raise Unauthorized("Bạn đăng nhập để xem đơn của mình nhé.", code="customer_signed_out")
    kind, contact = s
    cond = _orders_filter(kind, contact, await _customer_ids(db, kind, contact))
    if cond is None:
        return Paginated[MyOrder](items=[], total=0, page=page.page, size=page.size, pages=0)
    stmt = select(Order).where(cond, Order.status != OrderStatus.DRAFT).order_by(Order.placed_at.desc())
    return await paginate(db, stmt, page, _my_order)


def _my_order(o: Order) -> MyOrder:
    names = [f"{i.name} × {i.quantity}" if i.quantity > 1 else i.name for i in o.items]
    return MyOrder(
        code=o.code, token=order_access_token(o.id), status=o.status, status_label=service.STATUS_LABELS[o.status],
        placed_at=o.placed_at, total_vnd=o.total_vnd,
        items_summary=", ".join(names[:3]) + (f" và {len(names) - 3} món khác" if len(names) > 3 else ""),
        item_count=sum(i.quantity for i in o.items),
    )  # fmt: skip
