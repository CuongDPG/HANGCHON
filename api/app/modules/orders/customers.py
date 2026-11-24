"""Sổ khách có hồ sơ ngay từ tin nhắn đầu (h4): người lạ nhắn tin/bình luận → `customers` + `customer_identities`.

orders là chủ bảng khách; hộp thư chỉ đọc. Sau khi tạo/nhận ra khách, phát `customer.identified` để inbox gắn hội thoại
và crm tóm tắt sổ khách. Chạy lặp lại không sinh trùng (khoá theo kênh + định danh)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.inbox import rules
from app.modules.inbox.models import Direction, Message, Thread
from app.modules.orders.models import Customer, CustomerIdentity


async def ensure_from_message(db: AsyncSession, thread_id: uuid.UUID, message_id: uuid.UUID) -> uuid.UUID | None:
    thread = await db.get(Thread, thread_id)
    msg = await db.get(Message, message_id)
    if thread is None or msg is None or msg.direction != Direction.INBOUND or not thread.participant_external_id:
        return None
    ext = thread.participant_external_id
    cid = await db.scalar(
        select(CustomerIdentity.customer_id).where(
            CustomerIdentity.channel == thread.channel, CustomerIdentity.external_id == ext
        )
    )
    created = False
    if cid is None:
        cid = thread.customer_id
        phone = rules.extract_phone(msg.body or "")
        if cid is None and phone:
            cid = await db.scalar(select(Customer.id).where(Customer.phone == phone))
        if cid is None:
            c = Customer(name=thread.participant_name or msg.author_name, first_channel=thread.channel, phone=phone)
            db.add(c)
            await db.flush()
            cid, created = c.id, True
        await db.execute(
            pg_insert(CustomerIdentity)
            .values(
                id=uuid.uuid4(),
                customer_id=cid,
                channel=thread.channel,
                external_id=ext,
                display_name=thread.participant_name,
            )
            .on_conflict_do_nothing(constraint="uq_customer_identities_channel_external")
        )
    # khách đã gộp hồ sơ → hồ sơ chính
    c = await db.get(Customer, cid)
    while c is not None and c.merged_into_id:
        c = await db.get(Customer, c.merged_into_id)
    if c is None:
        return None
    if thread.customer_id != c.id:
        await events.emit(
            "customer.identified",
            {"customer_id": str(c.id), "thread_id": str(thread.id), "channel": thread.channel.value,
             "external_id": ext, "created": created},
            db=db,
        )  # fmt: skip
    return c.id
