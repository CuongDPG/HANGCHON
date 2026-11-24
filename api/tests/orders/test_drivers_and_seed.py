"""Driver thật (GHN, GHTK, Shopee, TikTok Shop) kiểm bằng HTTP giả lập theo tài liệu — chưa thử với tài khoản thật.
Dữ liệu mẫu seed_demo chạy lặp không sinh trùng."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.enums import Channel, ShippingStatus
from app.integrations import get_driver
from app.integrations.base import IntegrationNotConfigured
from app.integrations.shipping import Address, ShippingRequest
from app.modules.orders.models import Order

REQ = ShippingRequest(
    order_code="HC-48213",
    to=Address(name="Lan", phone="0900000101", address_line="12 Ngõ Mẫu", ward="Phường Ví Dụ", district="Quận Mẫu", province="Hà Nội"),
    weight_grams=800, cod_amount_vnd=407_000, declared_value_vnd=385_000, items=[{"name": "Bình", "quantity": 1}],
)  # fmt: skip


@respx.mock
async def test_ghn_quote_create_track(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ghn_token", "tok")
    monkeypatch.setattr(settings, "ghn_shop_id", "123")
    base = "https://online-gateway.ghn.vn/shiip/public-api"
    ok = lambda data: httpx.Response(200, json={"code": 200, "message": "Success", "data": data})  # noqa: E731
    respx.get(f"{base}/master-data/province").mock(
        return_value=ok([{"ProvinceID": 201, "ProvinceName": "Hà Nội", "NameExtension": ["Ha Noi"]}])
    )
    respx.post(f"{base}/master-data/district").mock(return_value=ok([{"DistrictID": 1442, "DistrictName": "Quận Mẫu"}]))
    respx.get(url__startswith=f"{base}/master-data/ward").mock(
        return_value=ok([{"WardCode": "20308", "WardName": "Phường Ví Dụ"}])
    )
    fee = respx.post(f"{base}/v2/shipping-order/fee").mock(return_value=ok({"total": 22000}))
    create = respx.post(f"{base}/v2/shipping-order/create").mock(
        return_value=ok({"order_code": "GHN123", "total_fee": 22000, "expected_delivery_time": "2026-11-28T17:00:00Z"})
    )
    respx.post(f"{base}/v2/a5/gen-token").mock(return_value=ok({"token": "abc"}))
    respx.post(f"{base}/v2/shipping-order/detail").mock(
        return_value=ok(
            {
                "status": "delivering",
                "log": [
                    {"status": "picked", "updated_date": "2026-11-26T08:00:00Z"},
                    {"status": "delivering", "updated_date": "2026-11-27T08:00:00Z"},
                ],
            }
        )
    )
    ghn = get_driver("shipping", "ghn")
    quotes = await ghn.quote(REQ)
    assert [q.fee_vnd for q in quotes] == [22000] and quotes[0].carrier == "ghn"
    sent = json.loads(fee.calls[0].request.content)
    assert sent["to_district_id"] == 1442 and sent["to_ward_code"] == "20308" and sent["cod_value"] == 407_000
    created = await ghn.create(REQ, "standard")
    assert created.tracking_code == "GHN123" and "printA5?token=abc" in (created.label_url or "")
    assert json.loads(create.calls[0].request.content)["client_order_code"] == "HC-48213"
    info = await ghn.track("GHN123")
    assert info.status == ShippingStatus.OUT_FOR_DELIVERY and [e.status for e in info.events] == [
        "picked_up",
        "out_for_delivery",
    ]
    assert len(await ghn.parse_webhook({}, json.dumps({"OrderCode": "GHN123", "Status": "lost"}).encode())) == 2


@respx.mock
async def test_ghtk_quote_and_track(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ghtk_token", "tok")
    for k, v in {
        "GHTK_PICK_NAME": "Hàng Chọn",
        "GHTK_PICK_TEL": "0900000000",
        "GHTK_PICK_ADDRESS": "1 Kho Mẫu",
    }.items():
        monkeypatch.setenv(k, v)
    base = "https://services.giaohangtietkiem.vn"
    respx.get(f"{base}/services/shipment/fee").mock(
        return_value=httpx.Response(
            200, json={"success": True, "fee": {"fee": 30000, "insurance_fee": 0, "delivery": True}}
        )
    )
    respx.get(f"{base}/services/shipment/v2/S1.A1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "order": {"status": 5, "status_text": "Đã giao hàng", "modified": "2026-11-27 10:00:00"},
            },
        )
    )
    ghtk = get_driver("shipping", "ghtk")
    quotes = await ghtk.quote(REQ)
    assert {q.service for q in quotes} == {"road", "fly"} and quotes[0].fee_vnd == 30000
    assert (await ghtk.track("S1.A1")).status == ShippingStatus.DELIVERED
    assert (await ghtk.parse_webhook({}, b"label_id=S1.A1&status_id=5"))[0].status == ShippingStatus.DELIVERED


async def test_drivers_need_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ghn_token", None)
    with pytest.raises(IntegrationNotConfigured):
        await get_driver("shipping", "ghn").quote(REQ)
    with pytest.raises(IntegrationNotConfigured):
        await get_driver("marketplaces", "shopee").fetch_orders(Channel.SHOPEE)
    with pytest.raises(IntegrationNotConfigured):
        await get_driver("marketplaces", "tiktok_shop").fetch_orders(Channel.TIKTOK_SHOP)


def test_marketplace_signatures() -> None:
    from app.integrations.marketplaces import shopee, tiktok_shop

    assert len(shopee.sign("key", "1", "/api/v2/order/get_order_list", 1700000000, "tok", "9")) == 64
    a = tiktok_shop.sign(
        "sec", "/order/202309/orders/search", {"app_key": "k", "timestamp": 1, "sign": "x", "access_token": "t"}, "{}"
    )
    b = tiktok_shop.sign("sec", "/order/202309/orders/search", {"timestamp": 1, "app_key": "k"}, "{}")
    assert a == b  # bỏ sign/access_token, không phụ thuộc thứ tự tham số


async def test_seed_demo_idempotent() -> None:
    from app.modules.orders.seed import seed_demo

    async with SessionLocal() as s:
        first = await seed_demo(s)
        await s.commit()
    async with SessionLocal() as s:
        second = await seed_demo(s)
        await s.commit()
        assert first["orders"] == 7 and second == {"products": 0, "drops": 0, "orders": 0}
        assert await s.scalar(select(func.count()).select_from(Order)) == 7
        statuses = set((await s.execute(select(Order.status))).scalars())
        assert {"pending_payment", "awaiting_stock", "ready_to_ship"} <= statuses
