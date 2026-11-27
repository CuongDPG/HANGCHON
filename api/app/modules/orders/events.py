"""orders nghe sự kiện của module khác (ARCHITECTURE mục 10). Mọi người nghe chạy lặp lại không sinh trùng."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.orders import customers, drafts, drops


@events.on("drop.closed")
async def _drop_closed(db: AsyncSession, payload: dict[str, Any]) -> None:
    """g3: hết đợt → chốt danh sách đơn của đợt (bên supply tự đọc order_items để cộng số lượng)."""
    await drops.on_drop_closed(db, uuid.UUID(str(payload["drop_id"])))


@events.on("inbound.arrived")
async def _inbound_arrived(db: AsyncSession, payload: dict[str, Any]) -> None:
    """g3/g8: lô hàng về → đơn của đợt chuyển sang chờ giao (khi mọi lô của đợt đã về)."""
    await drops.on_inbound_arrived(db, uuid.UUID(str(payload["inbound_shipment_id"])))


@events.on("message.received")
async def _message_received(db: AsyncSession, payload: dict[str, Any]) -> None:
    """h4: người lạ nhắn → có hồ sơ khách ngay; g6: AI nhận ra ý định mua → đơn nháp chờ chị chốt."""
    await customers.ensure_from_message(db, uuid.UUID(str(payload["thread_id"])), uuid.UUID(str(payload["message_id"])))
    await drafts.on_message(db, uuid.UUID(str(payload["thread_id"])), uuid.UUID(str(payload["message_id"])))


@events.on("customer.contact_submitted")
async def _contact_submitted(db: AsyncSession, payload: dict[str, Any]) -> None:
    """h4: khách tự để lại liên hệ (sổ người dùng thử «Mời thử cùng») → khớp hoặc tạo hồ sơ khách."""
    await customers.ensure_from_contact(db, payload)
