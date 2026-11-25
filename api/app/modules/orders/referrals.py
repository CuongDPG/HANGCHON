"""Quà giới thiệu bạn tự áp vào đơn (h7) — phía orders, chỉ ĐỌC bảng của crm (`referrals`, `referral_uses`).

Thiết kế «mã giới thiệu, quà cho cả hai»:
  · bạn được giới thiệu: đơn ĐẦU TIÊN có mã → giảm `referrals.reward_referred_vnd` ngay trên đơn;
  · người giới thiệu: khi đơn đầu của bạn đã trả tiền VÀ đã giao, crm tặng phần giảm `reward_referrer_vnd`
    (việc `crm.reward_referral`, AI tự làm, hoàn tác được) → orders tự trừ vào đơn kế tiếp của người giới thiệu.
Chống lạm dụng: chỉ khách mới (số điện thoại chưa có đơn còn sống), không tự giới thiệu mình, mỗi khách chỉ được
giới thiệu một lần, mỗi đơn dùng tối đa một phần quà của người giới thiệu. Không thêm cột: phần
giảm ghi ở đơn (`orders.raw["referral_gifts"]`, kể cả `credit_use_id` = phần quà đã dùng); quà do AI tặng = dòng Nhật
ký AI `crm.reward_referral` chưa hoàn tác. Đơn đã dùng phần quà mà bị huỷ thì phần quà được dùng lại."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import local_today
from app.modules.control.models import AIActivity
from app.modules.crm.models import Referral, ReferralUse, ReferralUseStatus
from app.modules.orders.models import Customer, Order, OrderStatus
from app.modules.orders.notify import vnd

DEAD = (OrderStatus.CANCELLED, OrderStatus.DRAFT)


@dataclass
class Gifts:
    friend_vnd: int = 0
    referral_id: uuid.UUID | None = None
    credit_vnd: int = 0
    credit_use_id: uuid.UUID | None = None
    note: str | None = None

    @property
    def total(self) -> int:
        return self.friend_vnd + self.credit_vnd

    def raw(self) -> dict[str, Any]:
        return {
            "friend_vnd": self.friend_vnd,
            "referral_id": str(self.referral_id) if self.referral_id else None,
            "credit_vnd": self.credit_vnd,
            "credit_use_id": str(self.credit_use_id) if self.credit_use_id else None,
        }


async def active_referral(db: AsyncSession, code: str | None) -> Referral | None:
    code = (code or "").strip().upper()
    if not code:
        return None
    ref = (await db.execute(select(Referral).where(func.upper(Referral.code) == code))).scalar_one_or_none()
    if ref is None or not ref.is_active or (ref.expires_on and ref.expires_on < local_today()):
        return None
    return ref


async def _customer_by_phone(db: AsyncSession, phone: str | None) -> Customer | None:
    if not phone:
        return None
    c = (await db.execute(select(Customer).where(Customer.phone == phone))).scalar_one_or_none()
    seen: set[uuid.UUID] = set()
    while c is not None and c.merged_into_id and c.id not in seen:
        seen.add(c.id)
        c = await db.get(Customer, c.merged_into_id)
    return c


async def quote_hint(db: AsyncSession, code: str | None) -> tuple[int, str | None]:
    """Bảng giá trước khi biết số điện thoại: chỉ báo quà dự kiến của mã (áp thật khi đặt, nếu là khách mới)."""
    if not (code or "").strip():
        return 0, None
    ref = await active_referral(db, code)
    if ref is None:
        return 0, "Mã giới thiệu này không còn dùng được."
    if ref.reward_referred_vnd <= 0:
        return 0, None
    return ref.reward_referred_vnd, (
        f"Quà giới thiệu: giảm {vnd(ref.reward_referred_vnd)} cho đơn đầu tiên của bạn. "
        "Mình áp khi bạn đặt nếu đây là lần đầu bạn mua."
    )


async def gifts_for(db: AsyncSession, order: Order, phone: str | None, max_vnd: int) -> Gifts:
    """Phần giảm tự áp cho một đơn sắp chốt. Không ghi gì vào bảng crm."""
    g = Gifts()
    if max_vnd <= 0:
        return g
    customer = await _customer_by_phone(db, phone)
    prior = 0
    if customer is not None:
        prior = int(
            await db.scalar(
                select(func.count()).where(
                    Order.customer_id == customer.id, Order.id != order.id, Order.status.not_in(DEAD)
                )
            )
            or 0
        )
    # bạn được giới thiệu: đơn đầu, không phải mã của chính mình, chưa từng được giới thiệu (lượt cũ chỉ còn hiệu lực
    # khi đơn của lượt đó đã huỷ)
    ref = await active_referral(db, order.referral_code)
    if ref is not None and ref.reward_referred_vnd > 0:
        if customer is not None and customer.id == ref.referrer_customer_id:
            g.note = "Mã giới thiệu dành cho bạn bè của bạn, không áp cho chính bạn."
        elif prior:
            g.note = "Quà giới thiệu chỉ áp cho đơn đầu tiên."
        elif customer is not None and await _already_referred(db, customer.id):
            g.note = "Bạn đã nhận quà giới thiệu rồi."
        else:
            g.friend_vnd = min(ref.reward_referred_vnd, max_vnd)
            g.referral_id = ref.id
    # người giới thiệu: phần quà đã được tặng mà chưa dùng (khoá dòng để hai đơn cùng lúc không dùng chung một phần)
    if customer is not None and max_vnd - g.friend_vnd > 0:
        used = (
            select(Order.raw["referral_gifts"]["credit_use_id"].astext)
            .where(Order.status.not_in(DEAD), Order.id != order.id)
            .where(Order.raw["referral_gifts"]["credit_use_id"].astext.is_not(None))
        )
        row = (
            await db.execute(
                select(ReferralUse, Referral.reward_referrer_vnd)
                .join(Referral, Referral.id == ReferralUse.referral_id)
                .join(  # quà do AI tặng (dòng Nhật ký AI chưa hoàn tác); chị tặng tay thì không tự trừ
                    AIActivity,
                    and_(
                        AIActivity.action == "crm.reward_referral",
                        AIActivity.ref_id == ReferralUse.id,
                        AIActivity.undone_at.is_(None),
                    ),
                )
                .where(
                    Referral.referrer_customer_id == customer.id,
                    ReferralUse.status == ReferralUseStatus.REWARDED,
                    Referral.reward_referrer_vnd > 0,
                    cast(ReferralUse.id, String).not_in(used),  # đơn đã dùng mà bị huỷ thì quà còn
                )
                .order_by(ReferralUse.rewarded_at.asc().nulls_last())
                .limit(1)
                .with_for_update(of=ReferralUse, skip_locked=True)
            )
        ).first()
        use, amount = row if row else (None, 0)
        if use is not None:
            g.credit_vnd = min(amount, max_vnd - g.friend_vnd)
            g.credit_use_id = use.id
    return g


async def _already_referred(db: AsyncSession, customer_id: uuid.UUID) -> bool:
    row = (
        await db.execute(
            select(ReferralUse.status, Order.status)
            .outerjoin(Order, Order.id == ReferralUse.order_id)
            .where(ReferralUse.referred_customer_id == customer_id)
        )
    ).first()
    if row is None:
        return False
    use_status, order_status = row
    return not (use_status == ReferralUseStatus.PENDING and (order_status is None or order_status in DEAD))
