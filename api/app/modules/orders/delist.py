"""Ngừng bán / mở bán lại một món trên TikTok Shop, Shopee khi chị ngừng bán món đó trên mọi kênh.

catalog phát `product.sale_stop_requested` / `product.sale_resume_requested` (payload: `stop_id`, `product_id`,
`listing_ids`). Sàn có lệnh ngừng bán qua API (`supports_deactivate`) thì dùng; không có thì đặt tồn về 0 (và nói rõ).
Kết quả ghi vào `marketplace_listings.data["stop"]` để catalog đọc lại. Lặp lại cùng `stop_id` thì bỏ qua."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.errors import AppError
from app.core.timeutil import now_utc
from app.modules.catalog.models import Product
from app.modules.control.models import User
from app.modules.orders.marketplace import MK_NAMES, available_stock, driver_for
from app.modules.orders.models import ListingStatus, MarketplaceListing

log = logging.getLogger("app.orders.delist")


def _uuid(v: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(v))
    except (TypeError, ValueError):
        return None


def _msg(e: Exception) -> str:
    return (e.message if isinstance(e, AppError) else str(e))[:500]


async def _ctx(db: AsyncSession, payload: dict[str, Any]) -> tuple[str, uuid.UUID | None, User | None]:
    uid = _uuid(payload.get("user_id"))
    return str(payload["stop_id"]), _uuid(payload.get("product_id")), (await db.get(User, uid) if uid else None)


async def on_stop(db: AsyncSession, payload: dict[str, Any]) -> None:
    stop_id, product_id, user = await _ctx(db, payload)
    for raw in payload.get("listing_ids") or []:
        lid = _uuid(raw)
        li = await db.get(MarketplaceListing, lid) if lid else None
        if li is None or li.product_id != product_id or ((li.data or {}).get("stop") or {}).get("stop_id") == stop_id:
            continue
        name = MK_NAMES.get(li.marketplace, li.marketplace.value)
        rec: dict[str, Any] = {"stop_id": stop_id, "prev_status": li.status.value, "at": now_utc().isoformat()}
        if not li.external_id:
            rec.update(outcome="failed", error="Món chưa có mã trên sàn (chưa đồng bộ xong).")
        else:
            driver = driver_for(li.marketplace)
            try:
                if getattr(driver, "supports_deactivate", False):
                    await driver.deactivate_product(li.marketplace, li.external_id)
                    rec["outcome"] = "deactivated"
                else:
                    await driver.update_stock(li.marketplace, li.external_id, 0)
                    rec["outcome"] = "stock_zero"
                    li.synced_stock = 0
                li.status = ListingStatus.INACTIVE
                li.error = None
            except Exception as e:
                log.warning("Ngừng bán trên %s lỗi: %s", name, _msg(e))
                rec.update(outcome="failed", error=_msg(e))
        li.data = {**(li.data or {}), "stop": rec}
        ok = rec["outcome"] != "failed"
        await control.audit(
            db, "orders.listing_deactivated" if ok else "orders.listing_deactivate_failed", user=user,
            entity_type="marketplace_listings", entity_id=li.id,
            summary=f"Ngừng bán trên {name}" + ("" if ok else f" lỗi: {rec['error'][:200]}"),
            data={"stop_id": stop_id, "outcome": rec["outcome"]},
        )  # fmt: skip
    await db.flush()


async def on_resume(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Mở bán lại các món đã ngừng trong lần `stop_id`, rồi đẩy lại tồn đang có (lượt đồng bộ sau giữ tiếp)."""
    stop_id, product_id, user = await _ctx(db, payload)
    product = await db.get(Product, product_id) if product_id else None
    for raw in payload.get("listing_ids") or []:
        lid = _uuid(raw)
        li = await db.get(MarketplaceListing, lid) if lid else None
        rec = dict((li.data or {}).get("stop") or {}) if li is not None else {}
        if (
            li is None or product is None or li.product_id != product_id or rec.get("stop_id") != stop_id
            or rec.get("outcome") not in ("deactivated", "stock_zero") or rec.get("restored_at")
        ):  # fmt: skip
            continue
        name = MK_NAMES.get(li.marketplace, li.marketplace.value)
        driver = driver_for(li.marketplace)
        stock = await available_stock(db, product)
        try:
            if rec["outcome"] == "deactivated":
                await driver.activate_product(li.marketplace, li.external_id)
                try:  # tồn: lượt đồng bộ sau cũng đẩy lại, lỗi ở đây không chặn việc mở bán
                    await driver.update_stock(li.marketplace, li.external_id, stock)
                except Exception as e:
                    log.warning("Đẩy tồn lên %s sau khi mở bán lại lỗi: %s", name, _msg(e))
                    stock = li.synced_stock or 0
            else:
                await driver.update_stock(li.marketplace, li.external_id, stock)
        except Exception as e:
            rec["restore_error"] = _msg(e)
            li.data = {**(li.data or {}), "stop": rec}
            await control.audit(db, "orders.listing_activate_failed", user=user, entity_type="marketplace_listings",
                                entity_id=li.id, summary=f"Mở bán lại trên {name} lỗi: {rec['restore_error'][:200]}")  # fmt: skip
            continue
        li.synced_stock = stock
        li.last_synced_at = now_utc()
        li.status = ListingStatus.ACTIVE if stock > 0 else ListingStatus.INACTIVE
        rec.update(restored_at=now_utc().isoformat(), restore_error=None)
        li.data = {**(li.data or {}), "stop": rec}
        await control.audit(db, "orders.listing_activated", user=user, entity_type="marketplace_listings",
                            entity_id=li.id, summary=f"Mở bán lại trên {name} (tồn {stock})")  # fmt: skip
    await db.flush()
