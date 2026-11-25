"""Việc nền của orders (giờ trong lịch là giờ Việt Nam)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app import control
from app.core.config import settings
from app.core.enums import Channel
from app.core.jobs import cron
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.modules.orders import drops, marketplace, notify, payments, service, shipping
from app.modules.orders.models import Notification, NotificationStatus, Order, OrderStatus, Return
from app.modules.orders.returns import OPEN_STATUSES

log = logging.getLogger("app.orders.jobs")


@cron("orders.expire_unpaid", minute={0, 10, 20, 30, 40, 50})
async def expire_unpaid(ctx: dict[str, Any]) -> dict[str, int]:
    """g2: nhắc khách chưa chuyển khoản, quá hạn thì huỷ và trả suất."""
    async with ctx["db"]() as db:
        stats = await payments.expire_unpaid(db)
        await db.commit()
        return stats


@cron("orders.reconcile_payments", minute={7, 22, 37, 52})
async def reconcile_payments(ctx: dict[str, Any]) -> int:
    """g2: đối soát khoản chuyển tới (phòng khi webhook lỡ)."""
    async with ctx["db"]() as db:
        try:
            transfers = await get_driver("payments").list_transactions(now_utc() - timedelta(days=2))
        except Exception as e:
            log.warning("Đối soát thanh toán lỗi: %s", e)
            return 0
        got = await payments.ingest_transfers(db, settings.payments_driver, transfers)
        await db.commit()
        return len(got)


@cron("orders.poll_tracking", minute={5, 35})
async def poll_tracking(ctx: dict[str, Any]) -> int:
    """g4: hỏi trạng thái vận đơn đang đi (bổ sung cho webhook của hãng)."""
    async with ctx["db"]() as db:
        n = await shipping.poll_active(db)
        await db.commit()
        return n


@cron("orders.notify_arriving", minute={15})
async def notify_arriving(ctx: dict[str, Any]) -> int:
    """g5: báo «hàng đang về» khi lô của đợt rời kho nước ngoài."""
    async with ctx["db"]() as db:
        n = await drops.notify_arriving(db)
        await db.commit()
        return n


@cron("orders.retry_notifications", minute={25})
async def retry_notifications(ctx: dict[str, Any]) -> int:
    async with ctx["db"]() as db:
        rows = list(
            (
                await db.execute(
                    select(Notification).where(
                        Notification.status == NotificationStatus.FAILED,
                        Notification.attempts < notify.MAX_ATTEMPTS,
                        Notification.recipient != "",
                    )
                )
            ).scalars()
        )
        for n in rows:
            await notify.deliver(db, n)
        await db.commit()
        return len(rows)


@cron("orders.pull_marketplaces", minute={12, 42})
async def pull_marketplaces(ctx: dict[str, Any]) -> int:
    """g9: kéo đơn TikTok Shop, Shopee về danh sách chung."""
    total = 0
    async with ctx["db"]() as db:
        for mk in (Channel.TIKTOK_SHOP, Channel.SHOPEE):
            try:
                async with db.begin_nested():
                    total += (await marketplace.pull_orders(db, mk)).created_orders
            except Exception as e:
                log.warning("Kéo đơn %s lỗi: %s", mk.value, e)
        await db.commit()
    return total


@cron("orders.complete_delivered", hour={3}, minute={30})
async def complete_delivered(ctx: dict[str, Any]) -> int:
    """Đơn đã giao quá hạn đổi trả, không có yêu cầu đang mở → hoàn tất."""
    async with ctx["db"]() as db:
        days = int(await control.get_setting(db, "orders.return_window_days") or 7)
        cutoff = now_utc() - timedelta(days=days)
        rows = list(
            (
                await db.execute(
                    select(Order).where(Order.status == OrderStatus.DELIVERED, Order.delivered_at < cutoff)
                )
            ).scalars()
        )
        n = 0
        for o in rows:
            if await db.scalar(select(func.count()).where(Return.order_id == o.id, Return.status.in_(OPEN_STATUSES))):
                continue
            o.completed_at = now_utc()
            service.set_status(db, o, OrderStatus.COMPLETED, "Đơn hoàn tất", visible=False)
            n += 1
        await db.commit()
        return n
