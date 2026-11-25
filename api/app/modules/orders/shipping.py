"""Vận đơn (g4): báo phí ở mọi hãng đã bật, chọn hãng theo phí + thời gian, tạo vận đơn (từng đơn / hàng loạt,
qua `control.propose` — mặc định AI tự làm), nhận trạng thái (webhook + hỏi định kỳ) → `shipment_events`,
phát `order.shipped` / `order.delivered`."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core import events
from app.core.config import settings
from app.core.enums import Carrier, ShippingStatus
from app.core.errors import AppError, Conflict
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.integrations.shipping import Address, ShippingRequest, TrackingEvent
from app.modules.orders import notify, refs, service
from app.modules.orders.models import Order, OrderEvent, OrderStatus, Shipment, ShipmentEvent
from app.modules.orders.notify import CARRIER_NAMES, vnd
from app.modules.orders.schemas import LabelOut, ShipmentResult, ShippingOption

log = logging.getLogger("app.orders.shipping")

SHIP_ACTION = "orders.create_shipment"
PROBLEM_ACTION = "orders.delivery_problem"

SHIPPING_LABELS: dict[ShippingStatus, str] = {
    ShippingStatus.PENDING: "Chưa tạo vận đơn",
    ShippingStatus.CREATED: "Đã tạo vận đơn, chờ hãng lấy hàng",
    ShippingStatus.PICKED_UP: "Hãng đã lấy hàng",
    ShippingStatus.IN_TRANSIT: "Đang trung chuyển",
    ShippingStatus.OUT_FOR_DELIVERY: "Đang giao tới bạn",
    ShippingStatus.DELIVERED: "Đã giao thành công",
    ShippingStatus.FAILED_DELIVERY: "Giao chưa thành công",
    ShippingStatus.RETURNING: "Đang hoàn hàng về",
    ShippingStatus.RETURNED: "Đã hoàn hàng về",
    ShippingStatus.CANCELLED: "Đã huỷ vận đơn",
}
FINAL = (ShippingStatus.DELIVERED, ShippingStatus.RETURNED, ShippingStatus.CANCELLED)


def driver_for(carrier: Carrier) -> Any:
    return get_driver("shipping", carrier.value)


async def carrier_drivers(db: AsyncSession) -> list[str]:
    names = await control.get_setting(db, "orders.shipping_carriers")
    if isinstance(names, list) and names:
        return [str(n) for n in names]
    return [settings.shipping_driver]


def build_request(
    addr: dict[str, Any],
    *,
    code: str,
    weight: int,
    cod: int = 0,
    value: int = 0,
    items: list[dict] | None = None,
    note: str | None = None,
) -> ShippingRequest:
    return ShippingRequest(
        order_code=code,
        to=Address(
            name=addr.get("name") or "Khách",
            phone=addr.get("phone") or "0000000000",
            address_line=addr.get("address_line") or "",
            ward=addr.get("ward"),
            district=addr.get("district"),
            province=addr.get("province") or settings.shipping_from_province,
            codes={k: str(v) for k, v in (addr.get("codes") or {}).items()},
        ),
        weight_grams=max(100, weight),
        cod_amount_vnd=cod,
        declared_value_vnd=value,
        items=items or [],
        note=note,
    )


async def quote_all(db: AsyncSession, req: ShippingRequest) -> list[ShippingOption]:
    out: list[ShippingOption] = []
    for name in await carrier_drivers(db):
        try:
            quotes = await get_driver("shipping", name).quote(req)
        except AppError as e:
            log.warning("Báo phí %s lỗi: %s", name, e.message)
            continue
        except Exception:
            log.exception("Báo phí %s lỗi", name)
            continue
        out += [
            ShippingOption(
                carrier=q.carrier,
                driver=name,
                service=q.service,
                service_name=q.service_name,
                fee_vnd=q.fee_vnd,
                eta_days_min=q.eta_days_min,
                eta_days_max=q.eta_days_max,
            )
            for q in quotes
        ]
    return out


async def pick_best(db: AsyncSession, options: list[ShippingOption]) -> tuple[ShippingOption | None, str]:
    """Điểm = phí + (số ngày giao chậm nhất × giá trị một ngày chị đặt). Thấp nhất thắng."""
    if not options:
        return None, "Không hãng nào báo phí được."
    day_value = int(await control.get_setting(db, "orders.shipping_day_value_vnd") or 5000)
    ranked = sorted(options, key=lambda o: (o.fee_vnd + o.eta_days_max * day_value, o.fee_vnd))
    best = ranked[0]
    reason = (
        f"Chọn {CARRIER_NAMES.get(best.carrier.value, best.carrier.value)} · {best.service_name}: "
        f"{vnd(best.fee_vnd)}, {best.eta_days_min}–{best.eta_days_max} ngày"
    )
    if len(ranked) > 1:
        alt = ranked[1]
        reason += (
            f" (so với {CARRIER_NAMES.get(alt.carrier.value, alt.carrier.value)} · {alt.service_name} "
            f"{vnd(alt.fee_vnd)}, {alt.eta_days_min}–{alt.eta_days_max} ngày; mỗi ngày chậm tính {vnd(day_value)})."
        )
    return best, reason


async def checkout_fee(db: AsyncSession, addr: dict[str, Any], weight: int, value: int) -> ShippingOption | None:
    req = build_request(addr, code="BAOGIA", weight=weight, value=value)
    best, _ = await pick_best(db, await quote_all(db, req))
    return best


async def weight_of(db: AsyncSession, order: Order) -> int:
    products = await refs.products_by_id(db, [i.product_id for i in order.items])
    default = int(await control.get_setting(db, "orders.default_weight_grams") or 500)
    return sum(
        ((products[i.product_id].weight_grams if i.product_id in products else None) or default) * i.quantity
        for i in order.items
    )


async def request_for(db: AsyncSession, order: Order) -> ShippingRequest:
    return build_request(
        service.order_address(order), code=order.code, weight=await weight_of(db, order), cod=order.cod_amount_vnd,
        value=order.subtotal_vnd, items=[{"name": i.name, "quantity": i.quantity} for i in order.items],
        note=order.customer_note,
    )  # fmt: skip


async def quote_for_order(db: AsyncSession, order: Order) -> tuple[list[ShippingOption], ShippingOption | None, str]:
    options = await quote_all(db, await request_for(db, order))
    best, reason = await pick_best(db, options)
    return options, best, reason


async def active_shipment(db: AsyncSession, order_id: Any) -> Shipment | None:
    return (
        await db.execute(select(Shipment).where(Shipment.order_id == order_id, Shipment.status.not_in(FINAL)).limit(1))
    ).scalar_one_or_none()


async def ship_orders(
    db: AsyncSession, order_ids: list[Any], *, driver: str | None = None, service_key: str | None = None
) -> list[ShipmentResult]:
    """Tạo vận đơn cho nhiều đơn: mỗi đơn một đề xuất qua control (mức mặc định: AI tự làm)."""
    results: list[ShipmentResult] = []
    for oid in order_ids:
        order = await service.get_order(db, oid, lock=True)
        if order.status != OrderStatus.READY_TO_SHIP:
            results.append(
                ShipmentResult(
                    order_id=order.id,
                    code=order.code,
                    status="skipped",
                    message=f"Đơn đang «{service.STATUS_LABELS[order.status]}», chưa giao được.",
                )
            )
            continue
        if await active_shipment(db, order.id):
            results.append(
                ShipmentResult(order_id=order.id, code=order.code, status="skipped", message="Đơn đã có vận đơn.")
            )
            continue
        options, best, reason = await quote_for_order(db, order)
        if driver:
            chosen = [o for o in options if o.driver == driver and (not service_key or o.service == service_key)]
            same_driver = [o for o in options if o.driver == driver]
            if not chosen and service_key and same_driver:  # dịch vụ không có trong bảng giá: vẫn theo ý chị
                chosen = [same_driver[0].model_copy(update={"service": service_key, "service_name": service_key})]
            best = chosen[0] if chosen else None
            reason = "Chị chọn hãng này." if best else reason
        if best is None:
            results.append(
                ShipmentResult(
                    order_id=order.id,
                    code=order.code,
                    status="failed",
                    message="Không hãng nào nhận đơn này (kiểm địa chỉ).",
                )
            )
            continue
        out = await control.propose(
            SHIP_ACTION,
            f"Tạo vận đơn {order.code} · {CARRIER_NAMES.get(best.carrier.value, best.carrier.value)}",
            {"order_id": str(order.id), "driver": best.driver, "service": best.service, "reason": reason,
             "quotes": [o.model_dump(mode="json") for o in options]},
            {"order_code": order.code, "recipient": order.recipient_name, "province": order.province,
             "fee_vnd": best.fee_vnd, "cod_amount_vnd": order.cod_amount_vnd, "service_name": best.service_name,
             "eta": f"{best.eta_days_min}–{best.eta_days_max} ngày"},
            db=db, summary=reason, rationale=reason, ref_type="orders", ref_id=order.id,
            dedupe_key=f"ship:{order.id}", ai_generated=False,
        )  # fmt: skip
        res = out.result or {}
        results.append(
            ShipmentResult(
                order_id=order.id,
                code=order.code,
                status=out.status,
                shipment_id=res.get("shipment_id"),
                tracking_code=res.get("tracking_code"),
                carrier=best.carrier,
                fee_vnd=best.fee_vnd,
                message=out.error or (reason if out.status == "pending" else None),
            )
        )
    return results


async def create_shipment(
    db: AsyncSession, order: Order, driver_name: str, service_key: str, *, reason: str | None, quotes: list[Any]
) -> Shipment:
    """Handler thật của orders.create_shipment: gọi hãng, lưu vận đơn."""
    if order.status != OrderStatus.READY_TO_SHIP:
        raise Conflict(f"Đơn {order.code} không còn ở bước chờ giao.")
    if await active_shipment(db, order.id):
        raise Conflict(f"Đơn {order.code} đã có vận đơn.")
    req = await request_for(db, order)
    created = await get_driver("shipping", driver_name).create(req, service_key)
    sh = Shipment(
        order_id=order.id, carrier=created.carrier, service=created.service, tracking_code=created.tracking_code,
        status=ShippingStatus.CREATED, fee_vnd=created.fee_vnd, cod_amount_vnd=order.cod_amount_vnd,
        weight_grams=req.weight_grams, label_url=created.label_url, quotes=quotes, selection_reason=reason,
        expected_delivery_at=created.expected_delivery_at, raw={"driver": driver_name, **(created.raw or {})},
    )  # fmt: skip
    db.add(sh)
    await db.flush()
    service.add_event(
        db, order, "shipment_created", "Đã đóng gói, chờ hãng vận chuyển lấy hàng",
        detail=f"{CARRIER_NAMES.get(sh.carrier.value, sh.carrier.value)} · mã vận đơn {sh.tracking_code}",
        data={"shipment_id": str(sh.id)},
    )  # fmt: skip
    await db.flush()
    await _push_marketplace(db, order)
    return sh


async def _push_marketplace(db: AsyncSession, order: Order) -> None:
    """g9: đơn từ sàn có vận đơn / đã giao → báo ngược lên sàn (lỗi không làm hỏng luồng đơn; cron đẩy lại)."""
    from app.modules.orders import marketplace

    if order.channel not in marketplace.MARKETPLACES:
        return
    try:
        async with db.begin_nested():
            await marketplace.push_status(db, order)
    except Exception:
        log.exception("Đẩy trạng thái đơn %s lên sàn lỗi", order.code)


async def apply_tracking(db: AsyncSession, sh: Shipment, evs: list[TrackingEvent]) -> int:
    """Ghi mốc mới (không trùng) rồi đổi trạng thái vận đơn + đơn. Trả số mốc mới."""
    seen = set(
        (
            await db.execute(
                select(ShipmentEvent.status, ShipmentEvent.occurred_at).where(ShipmentEvent.shipment_id == sh.id)
            )
        ).all()
    )
    new = 0
    for e in sorted(evs, key=lambda x: x.occurred_at):
        if (e.status, e.occurred_at) in seen:
            continue
        db.add(
            ShipmentEvent(
                shipment_id=sh.id,
                status=e.status,
                description=e.description,
                location=e.location,
                occurred_at=e.occurred_at,
            )
        )
        seen.add((e.status, e.occurred_at))
        new += 1
    sh.last_synced_at = now_utc()
    if evs:
        latest = max(evs, key=lambda x: x.occurred_at)
        await _set_shipment_status(db, sh, latest.status, latest.occurred_at, [e.status for e in evs])
    await db.flush()
    return new


async def _set_shipment_status(
    db: AsyncSession, sh: Shipment, status: ShippingStatus, at: Any, seen: list[ShippingStatus]
) -> None:
    sh.status = status
    if status in (
        ShippingStatus.PICKED_UP,
        ShippingStatus.IN_TRANSIT,
        ShippingStatus.OUT_FOR_DELIVERY,
        ShippingStatus.DELIVERED,
    ):
        sh.picked_up_at = sh.picked_up_at or at
    if status == ShippingStatus.DELIVERED:
        sh.delivered_at = sh.delivered_at or at
    if not sh.order_id:
        return
    order = await service.get_order(db, sh.order_id, lock=True)
    carrier = CARRIER_NAMES.get(sh.carrier.value, sh.carrier.value)
    extra = {"hang": carrier, "ma_van_don": sh.tracking_code or ""}
    moved = status in (
        ShippingStatus.PICKED_UP,
        ShippingStatus.IN_TRANSIT,
        ShippingStatus.OUT_FOR_DELIVERY,
        ShippingStatus.DELIVERED,
    )
    if moved and order.status == OrderStatus.READY_TO_SHIP:
        order.shipped_at = sh.picked_up_at or now_utc()
        service.set_status(
            db, order, OrderStatus.SHIPPING, f"Đã giao cho {carrier}", detail=f"Mã vận đơn {sh.tracking_code}"
        )
        await db.flush()
        await events.emit("order.shipped", {"order_id": str(order.id), "shipment_id": str(sh.id)}, db=db)
        await notify.notify_order(db, order, "shipped", extra)
    if ShippingStatus.OUT_FOR_DELIVERY in (status, *seen) and status != ShippingStatus.DELIVERED:
        await notify.notify_order(db, order, "out_for_delivery", extra)
    if status == ShippingStatus.DELIVERED and order.status in (OrderStatus.SHIPPING, OrderStatus.READY_TO_SHIP):
        order.delivered_at = sh.delivered_at or now_utc()
        service.set_status(db, order, OrderStatus.DELIVERED, "Đã giao tới bạn")
        await db.flush()
        from app.modules.orders import payments as pay_svc

        await pay_svc.record_cod(db, order)
        await events.emit("order.delivered", {"order_id": str(order.id)}, db=db)
        await notify.notify_order(db, order, "delivered", extra)
        await _push_marketplace(db, order)
    if status in (ShippingStatus.FAILED_DELIVERY, ShippingStatus.RETURNING, ShippingStatus.RETURNED):
        title = SHIPPING_LABELS[status]
        if status == ShippingStatus.RETURNED and order.status in (OrderStatus.SHIPPING, OrderStatus.READY_TO_SHIP):
            service.set_status(db, order, OrderStatus.RETURNED, "Hàng đã hoàn về kho", visible=True)
        else:
            exists = await db.scalar(
                select(func.count()).where(
                    OrderEvent.order_id == order.id, OrderEvent.kind == f"shipment_{status.value}"
                )
            )
            if not exists:
                service.add_event(db, order, f"shipment_{status.value}", title, detail=f"Mã vận đơn {sh.tracking_code}")
        await control.propose(
            PROBLEM_ACTION, f"Giao hàng trục trặc: {order.code} · {title}",
            {"order_id": str(order.id), "shipment_id": str(sh.id), "status": status.value},
            {"order_code": order.code, "recipient": order.recipient_name, "phone": order.recipient_phone,
             "tracking_code": sh.tracking_code, "carrier": carrier, "status": title},
            db=db, summary=f"{carrier} báo «{title}». Chị gọi khách hoặc hẹn giao lại.",
            ref_type="orders", ref_id=order.id, dedupe_key=f"delivery:{sh.id}", priority=5, ai_generated=False,
        )  # fmt: skip
    if status == ShippingStatus.CANCELLED:
        service.add_event(db, order, "shipment_cancelled", "Đã huỷ vận đơn", visible=False)


async def sync_shipment(db: AsyncSession, sh: Shipment) -> int:
    if not sh.tracking_code or sh.status in FINAL:
        return 0
    info = await driver_for(sh.carrier).track(sh.tracking_code)
    return await apply_tracking(db, sh, info.events)


async def cancel_shipment(db: AsyncSession, sh: Shipment) -> Shipment:
    if sh.status != ShippingStatus.CREATED:
        raise Conflict("Hãng đã lấy hàng, không huỷ được vận đơn.", code="cannot_cancel")
    if sh.tracking_code:
        await driver_for(sh.carrier).cancel(sh.tracking_code)
    sh.status = ShippingStatus.CANCELLED
    db.add(
        ShipmentEvent(
            shipment_id=sh.id, status=ShippingStatus.CANCELLED, description="Đã huỷ vận đơn", occurred_at=now_utc()
        )
    )
    if sh.order_id:
        order = await service.get_order(db, sh.order_id)
        service.add_event(db, order, "shipment_cancelled", "Đã huỷ vận đơn", visible=False)
    await db.flush()
    return sh


async def handle_webhook(db: AsyncSession, carrier: str, evs: list[TrackingEvent]) -> int:
    by_code: dict[str, list[TrackingEvent]] = {}
    for e in evs:
        by_code.setdefault(e.tracking_code, []).append(e)
    n = 0
    for code, items in by_code.items():
        sh = (
            await db.execute(
                select(Shipment).where(Shipment.carrier == Carrier(carrier), Shipment.tracking_code == code)
            )
        ).scalar_one_or_none()
        if sh is None:
            log.info("Webhook %s: không thấy vận đơn %s", carrier, code)
            continue
        n += await apply_tracking(db, sh, items)
    return n


async def poll_active(db: AsyncSession) -> int:
    stale = now_utc() - timedelta(minutes=20)
    rows = list(
        (
            await db.execute(
                select(Shipment).where(
                    Shipment.status.not_in(FINAL), Shipment.tracking_code.is_not(None),
                    (Shipment.last_synced_at.is_(None)) | (Shipment.last_synced_at < stale),
                )
            )
        ).scalars()
    )  # fmt: skip
    n = 0
    for sh in rows:
        try:
            async with db.begin_nested():
                n += await sync_shipment(db, sh)
        except Exception:
            log.exception("Hỏi trạng thái vận đơn %s lỗi", sh.tracking_code)
    return n


async def labels(db: AsyncSession, order_ids: list[Any]) -> list[LabelOut]:
    out: list[LabelOut] = []
    for oid in order_ids:
        order = await service.get_order(db, oid)
        sh = (
            await db.execute(
                select(Shipment)
                .where(Shipment.order_id == order.id, Shipment.status != ShippingStatus.CANCELLED)
                .order_by(Shipment.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if sh is None:
            continue
        addr = ", ".join(x for x in (order.address_line, order.ward, order.district, order.province) if x)
        out.append(
            LabelOut(
                order_id=order.id,
                code=order.code,
                recipient_name=order.recipient_name,
                recipient_phone=order.recipient_phone,
                address=addr,
                carrier=sh.carrier,
                service=sh.service,
                tracking_code=sh.tracking_code,
                cod_amount_vnd=sh.cod_amount_vnd,
                weight_grams=sh.weight_grams,
                items_summary=", ".join(f"{i.name} x{i.quantity}" for i in order.items),
                note=order.customer_note,
                label_url=sh.label_url,
            )
        )
    return out
