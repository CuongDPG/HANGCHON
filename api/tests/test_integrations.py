from __future__ import annotations

import json

import pytest

from app.core.enums import Channel, ShippingStatus, SourcePlatform
from app.integrations import KINDS, IntegrationError, IntegrationNotConfigured, get_driver
from app.integrations.einvoice import InvoiceLine, InvoiceRequest
from app.integrations.marketplaces import MarketplaceProduct
from app.integrations.notify import OutboundNotification
from app.integrations.payments import transfer_content_for
from app.integrations.shipping import Address, ShippingRequest
from app.integrations.social import SocialPost
from app.integrations.sources import SourceQuery


def test_every_kind_has_default_driver() -> None:
    for kind in KINDS:
        assert get_driver(kind) is get_driver(kind)  # dùng chung một thể hiện
    with pytest.raises(IntegrationNotConfigured):
        get_driver("payments", "khong_co")


async def test_sources_mock_is_deterministic() -> None:
    src = get_driver("sources")
    q = SourceQuery(keywords=["保温杯"], platforms=[SourcePlatform.ALIBABA_1688, SourcePlatform.RAKUTEN], limit=6)
    a, b = await src.search(q), await src.search(q)
    assert [i.external_id for i in a] == [i.external_id for i in b] and len(a) == 6
    assert {i.currency for i in a} == {"CNY", "JPY"}
    p = await src.fetch_product("https://detail.1688.com/offer/123.html")
    assert p.platform == SourcePlatform.ALIBABA_1688 and p.images and p.reviews and p.specs
    assert await src.search_by_image(b"\xff\xd8abc")
    assert len(await src.trends(limit=4)) == 4
    prices = await src.market_prices("bình giữ nhiệt")
    assert all(x.price_vnd >= 10_000 for x in prices)


async def test_payments_mock_transfer_and_webhook() -> None:
    pay = get_driver("payments")
    req = await pay.create_request("HC2611250001", 250_000)
    assert req.transfer_content == transfer_content_for("HC2611250001") == "HC HC2611250001"
    t = pay.simulate_transfer(250_000, req.transfer_content)
    assert [x.external_id for x in await pay.list_transactions()] == [t.external_id]
    body = json.dumps({"transfers": [t.model_dump(mode="json")]}).encode()
    parsed = await pay.parse_webhook({"X-Mock-Signature": pay.sign(body)}, body)
    assert parsed[0].amount_vnd == 250_000
    with pytest.raises(IntegrationError):
        await pay.parse_webhook({"X-Mock-Signature": "sha256=sai"}, body)


async def test_shipping_mock_status_chain() -> None:
    ship = get_driver("shipping")
    req = ShippingRequest(
        order_code="HC1", to=Address(name="A", phone="0900000000", address_line="1 Phố", province="Hà Nội")
    )
    quotes = await ship.quote(req)
    assert {q.service for q in quotes} == {"standard", "express"}
    created = await ship.create(req, "standard")
    assert created.tracking_code.startswith("MKS")
    assert (await ship.track(created.tracking_code)).status == ShippingStatus.CREATED
    ship.advance(2)
    assert (await ship.track(created.tracking_code)).status == ShippingStatus.IN_TRANSIT
    ship.advance(10)
    info = await ship.track(created.tracking_code)
    assert info.status == ShippingStatus.DELIVERED and len(info.events) == 5
    fail = await ship.create(req, "fail")
    ship.advance(20)
    assert (await ship.track(fail.tracking_code)).status == ShippingStatus.RETURNED
    with pytest.raises(IntegrationError):
        await ship.cancel(created.tracking_code)  # đã lấy hàng


async def test_shipping_cancel_before_pickup() -> None:
    ship = get_driver("shipping")
    req = ShippingRequest(order_code="HC2", to=Address(name="B", phone="0900000001", address_line="x", province="Huế"))
    c = await ship.create(req, "express")
    await ship.cancel(c.tracking_code)
    ship.advance(5)
    assert (await ship.track(c.tracking_code)).status == ShippingStatus.CANCELLED


async def test_social_mock_publish_inbound_reply() -> None:
    social = get_driver("social")
    fb = await social.publish(SocialPost(channel=Channel.FACEBOOK, text="Bình giữ nhiệt", ai_label=True))
    tt = await social.publish(SocialPost(channel=Channel.TIKTOK, text="Kịch bản"))
    assert fb.status == "published" and fb.url and tt.status == "draft_pushed"
    ev = social.simulate_inbound("Còn hàng không chị?", author_name="Khách A")
    events = await social.fetch_inbound()
    assert events == [ev] and await social.fetch_inbound() == []
    sent = await social.send_message(Channel.FACEBOOK, ev.thread_external_id, "Còn ạ")
    assert sent.external_id and social.sent[-1]["text"] == "Còn ạ"
    m = await social.post_metrics(Channel.FACEBOOK, fb.external_id)
    assert m.reach > 0 and m == await social.post_metrics(Channel.FACEBOOK, fb.external_id)


async def test_notify_marketplaces_einvoice_mocks() -> None:
    notify = get_driver("notify")
    ok = await notify.send(OutboundNotification(channel=Channel.ZALO_OA, to="zalo_1", text="Đã nhận đơn"))
    bad = await notify.send(OutboundNotification(channel=Channel.SMS, to="fail-0900", text="x"))
    assert ok.status == "sent" and bad.status == "failed" and len(notify.outbox) == 1

    mk = get_driver("marketplaces")
    ext = await mk.upsert_product(
        Channel.SHOPEE, MarketplaceProduct(sku="BGN-01", name="Bình", description="d", price_vnd=1, stock=5)
    )
    await mk.update_stock(Channel.SHOPEE, ext, 3)
    o = mk.simulate_order(Channel.SHOPEE, "BGN-01", 2)
    assert (await mk.fetch_orders(Channel.SHOPEE))[0].external_id == o.external_id
    await mk.update_order_status(Channel.SHOPEE, o.external_id, "shipped")

    inv = get_driver("einvoice")
    req = InvoiceRequest(
        reference="HC1", buyer_name="Khách", lines=[InvoiceLine(name="Bình", quantity=2, unit_price_vnd=100_000)],
        total_vnd=200_000,
    )  # fmt: skip
    a = await inv.issue(req)
    assert (await inv.issue(req)).number == a.number  # không phát hành trùng
    with pytest.raises(IntegrationError):
        await inv.issue(req.model_copy(update={"reference": "HC2", "total_vnd": 1}))
