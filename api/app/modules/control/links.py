"""Đường dẫn tới màn hình của đối tượng một việc chờ / một việc AI đã làm (từ «Chờ duyệt» bấm tới đúng chỗ).

control chỉ ĐỌC bảng của module khác (qua SQL thô theo tên bảng) để biết sản phẩm/ứng viên/đơn gốc."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DIRECT = {
    "candidates": "/desk/san-hang/ung-vien/{id}",
    "assessments": None,  # tra ứng viên bên dưới
    "sourcing_briefs": "/desk/san-hang/de/{id}",
    "comparisons": "/desk/san-hang/so-sanh/{id}",
    "demand_signals": "/desk/san-hang?tab=nhu-cau",
    "products": "/desk/san-pham/{id}",
    "drops": "/desk/san-pham/dot/{id}",
    "reviews": "/desk/san-pham/danh-gia",
    "find_requests": "/desk/san-pham/nho-tim",
    "orders": "/desk/don-hang/{id}",
    "inventory_items": "/desk/don-hang/van-hanh",
    "payments": "/desk/don-hang/van-hanh",
    "purchase_orders": "/desk/nguon-cung/don/{id}",
    "supplier_messages": "/desk/nguon-cung",
    "threads": "/desk/khach/hoi-thoai/{id}",
    "customers": "/desk/khach/so-khach/{id}",
    "broadcasts": "/desk/khach/khach-quen",
    "reorder_reminders": "/desk/khach/nhac-mua-lai",
    "referral_uses": "/desk/khach/gioi-thieu",
    "livestream_scripts": "/desk/noi-dung/livestream/{id}",
    "voice_profiles": "/desk/noi-dung/giong",
    "media_assets": "/desk/noi-dung/video",
    "content_insights": "/desk/noi-dung/so-lieu",
    "scheduled_posts": "/desk/noi-dung/lich",
    "trial_notes": "/desk/ban-chon",
    "taste_profiles": "/desk/ban-chon/gu",
    "weekly_reports": "/desk/bao-cao",
    "invoices": "/desk/so-sach",
}

# bảng → (cột trỏ về đối tượng có màn hình riêng, mẫu đường dẫn)
VIA: dict[str, list[tuple[str, str]]] = {
    "assessments": [("candidate_id", "/desk/san-hang/ung-vien/{v}")],
    "selection_decisions": [("candidate_id", "/desk/ban-chon/{v}")],
    "price_proposals": [("candidate_id", "/desk/nguon-cung/gia-von/{v}"), ("product_id", "/desk/san-pham/{v}")],
    "returns": [("order_id", "/desk/don-hang/{v}")],
    "content_drafts": [("product_id", "/desk/noi-dung/san-pham/{v}"), ("drop_id", "/desk/noi-dung/dot/{v}")],
    "product_images": [("product_id", "/desk/san-pham/{v}")],
    "purchase_order_lines": [("purchase_order_id", "/desk/nguon-cung/don/{v}")],
}


async def object_href(
    db: AsyncSession, ref_type: str | None, ref_id: uuid.UUID | None, payload: dict[str, Any]
) -> str | None:
    if ref_type in VIA and ref_id is not None:
        cols = ", ".join(c for c, _ in VIA[ref_type])
        row = (await db.execute(text(f"SELECT {cols} FROM {ref_type} WHERE id = :id"), {"id": ref_id})).first()
        if row is not None:
            for (_, tpl), v in zip(VIA[ref_type], row, strict=True):
                if v:
                    return tpl.format(v=v)
    tpl = DIRECT.get(ref_type or "")
    if tpl and ref_id is not None:
        return tpl.format(id=ref_id)
    for key, t in (("thread_id", "/desk/khach/hoi-thoai/{}"), ("order_id", "/desk/don-hang/{}"),
                   ("candidate_id", "/desk/san-hang/ung-vien/{}"), ("product_id", "/desk/san-pham/{}")):  # fmt: skip
        if payload.get(key):
            return t.format(payload[key])
    return None


async def attach(db: AsyncSession, items: list[Any]) -> None:
    """Gắn `href` cho từng việc (đối tượng ORM hoặc schema đầu ra)."""
    for it in items:
        try:
            it.href = await object_href(db, it.ref_type, it.ref_id, it.payload or {})
        except Exception:  # bảng chưa có / dữ liệu lạ: không làm hỏng danh sách
            it.href = None
