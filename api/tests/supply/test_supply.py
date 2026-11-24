"""Nguồn cung và giá vốn (d1–d7)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select

from app.core import events
from app.core.db import SessionLocal
from app.core.enums import SourcePlatform
from app.core.timeutil import local_today, now_utc
from app.integrations import get_driver
from app.integrations.shipping import Address, ShippingRequest
from app.modules.assessment.models import MarketPrice
from app.modules.catalog.models import Drop, DropItem, Product
from app.modules.control.models import ApprovalItem, ApprovalStatus
from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.sourcing.models import CandidateStage
from app.modules.supply.models import PurchaseOrder
from tests.selection.helpers import capture, make_candidate

S = "/api/desk/supply"


async def _supplier(c: httpx.AsyncClient, name: str = "Xưởng Nghĩa Ô (ví dụ)", **kw) -> dict:
    r = await c.post(f"{S}/suppliers", json={"name": name, "kind": "factory", "country": "cn", "language": "zh", **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def _approve(c: httpx.AsyncClient, item_id: str, payload: dict | None = None) -> dict:
    r = await c.post(f"/api/desk/control/approvals/{item_id}/approve", json={"payload": payload} if payload else {})
    assert r.status_code == 200, r.text
    return r.json()


# ---- d2 ------------------------------------------------------------------------------------------------------------


async def test_landed_cost_breakdown_matches_wireframe(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate()
    body = {"candidate_id": str(c.id), "unit_price_amount": "31", "currency": "CNY", "weight_grams": 2100,
            "domestic_shipping_vnd": 10000, "packaging_vnd": 0}  # fmt: skip
    prev = (await owner_client.post(f"{S}/cost-sheets/preview", json=body)).json()
    lines = {ln["key"]: ln for ln in prev["breakdown"]}
    assert lines["unit_price"]["amount_vnd"] == 113150 and lines["unit_price"]["formula"] == "31 CNY × 3.650"
    assert lines["intl_shipping"]["amount_vnd"] == 29400 and "2,1 kg" in lines["intl_shipping"]["formula"]
    assert lines["agent_fee"]["amount_vnd"] == 3695  # 3% × (113.150 + 10.000)
    assert lines["vat"]["amount_vnd"] == 15255  # 10% × 152.550
    assert prev["landed_cost_vnd"] == 174930  # 171.500 như wireframe (≈172k) + hao hụt 2%

    sheet = (await owner_client.post(f"{S}/cost-sheets", json=body)).json()
    assert sheet["landed_cost_vnd"] == prev["landed_cost_vnd"] and sheet["version"] == 1
    manual = await make_candidate("Khăn tắm")
    m = (
        await owner_client.post(
            f"{S}/cost-sheets",
            json={**body, "candidate_id": str(manual.id), "auto_update": False, "fx_rate": "3500", "vat_pct": "0"},
        )
    ).json()
    assert Decimal(m["fx_rate"]) == 3500 and Decimal(m["vat_pct"]) == 0

    params = (await owner_client.get(f"{S}/settings")).json()
    params["fx_rates"]["CNY"] = "3800"
    r = await owner_client.patch(f"{S}/settings", json=params)
    assert r.status_code == 200 and r.json()["recalculated"] == 1  # bảng tham số riêng không bị tính lại
    cur = (await owner_client.get(f"{S}/cost-sheets/current", params={"candidate_id": str(c.id)})).json()
    assert cur["unit_price_vnd"] == 117800 and cur["version"] == 2
    again = (await owner_client.get(f"{S}/cost-sheets/current", params={"candidate_id": str(manual.id)})).json()
    assert again["landed_cost_vnd"] == m["landed_cost_vnd"]
    # nhập lại → bản mới, bản cũ thôi hiện hành
    v3 = (await owner_client.post(f"{S}/cost-sheets", json=body)).json()
    assert v3["version"] == 3
    assert (await owner_client.get(f"{S}/cost-sheets", params={"candidate_id": str(c.id)})).json()["total"] == 1


async def test_cost_settings_owner_only_and_validation(helper_client: httpx.AsyncClient, owner_client) -> None:
    params = (await helper_client.get(f"{S}/settings")).json()
    assert (await helper_client.patch(f"{S}/settings", json=params)).status_code == 403
    r = await owner_client.post(f"{S}/cost-sheets/preview", json={"unit_price_amount": "10", "currency": "KRW"})
    assert r.status_code == 400 and r.json()["code"] == "missing_fx"
    r = await owner_client.post(f"{S}/cost-sheets", json={"unit_price_amount": "10"})
    assert r.status_code == 400


# ---- d3 ------------------------------------------------------------------------------------------------------------


async def test_price_proposal_flow(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate()
    r = await owner_client.post(f"{S}/price-proposals", json={"candidate_id": str(c.id)})
    assert r.status_code == 400 and r.json()["code"] == "no_cost_sheet"
    await owner_client.post(
        f"{S}/cost-sheets", json={"candidate_id": str(c.id), "unit_price_amount": "31", "weight_grams": 2100}
    )
    async with SessionLocal() as s:
        for price in (289000, 315000, 350000):
            s.add(MarketPrice(candidate_id=c.id, platform=SourcePlatform.SHOPEE_VN, title="Giá phơi", url="https://e.x",
                              price_vnd=price, captured_at=now_utc()))  # fmt: skip
        await s.commit()
    p = (await owner_client.post(f"{S}/price-proposals", json={"candidate_id": str(c.id)})).json()
    assert p["status"] == "pending_review" and p["market_median_vnd"] == 315000 and p["market_samples"] == 3
    assert p["proposed_price_vnd"] % 1000 == 0 and p["proposed_price_vnd"] > p["landed_cost_vnd"]
    assert "289.000đ" in p["rationale"]

    with capture("price.approved") as seen:
        await _approve(owner_client, p["approval_item_id"], {"price_vnd": 279000})
    assert seen == [
        (
            "price.approved",
            {"candidate_id": str(c.id), "price_vnd": 279000, "price_proposal_id": p["id"], "product_id": None},
        )
    ]
    got = (await owner_client.get(f"{S}/price-proposals", params={"candidate_id": str(c.id)})).json()
    assert got[0]["status"] == "approved" and got[0]["approved_price_vnd"] == 279000

    p2 = (
        await owner_client.post(f"{S}/price-proposals", json={"candidate_id": str(c.id), "target_margin_pct": 50})
    ).json()
    r = await owner_client.post(
        f"/api/desk/control/approvals/{p2['approval_item_id']}/return", json={"note": "Cao quá"}
    )
    assert r.status_code == 200
    got = (await owner_client.get(f"{S}/price-proposals", params={"candidate_id": str(c.id)})).json()
    assert got[0]["status"] == "rejected" and "Cao quá" in got[0]["rationale"]


# ---- d1 + d5 + d7 + d4 ---------------------------------------------------------------------------------------------


async def test_sample_order_from_board_is_locked_then_full_lifecycle(owner_client: httpx.AsyncClient) -> None:
    sup = await _supplier(owner_client)
    c = await make_candidate(supplier_id=uuid.UUID(sup["id"]))
    r = await owner_client.post(f"/api/desk/selection/candidates/{c.id}/stage", json={"to": "sample"})
    assert r.status_code == 200
    pos = (await owner_client.get(f"{S}/purchase-orders", params={"candidate_id": str(c.id)})).json()["items"]
    assert len(pos) == 1
    po = pos[0]
    assert po["kind"] == "sample" and po["status"] == "pending_approval" and po["ai_generated"]
    assert "样品" in po["message_draft"] and po["supplier_name"] == sup["name"]
    # đặt hàng luôn hỏi chị: không đổi được mức tự chủ
    r = await owner_client.patch("/api/desk/control/autonomy/supply.place_order", json={"level": "auto"})
    assert r.status_code == 403
    # chuyển ra rồi vào lại cột Mua mẫu không sinh đơn trùng
    await owner_client.post(f"/api/desk/selection/candidates/{c.id}/stage", json={"to": "candidate"})
    await owner_client.post(f"/api/desk/selection/candidates/{c.id}/stage", json={"to": "sample"})
    assert (await owner_client.get(f"{S}/purchase-orders", params={"candidate_id": str(c.id)})).json()["total"] == 1

    r = await owner_client.post(f"{S}/purchase-orders/{po['id']}/status", json={"to": "sent"})
    assert r.status_code == 409
    await _approve(owner_client, po["approval_item_id"])
    po = (await owner_client.get(f"{S}/purchase-orders/{po['id']}")).json()
    assert po["status"] == "approved"
    r = await owner_client.patch(f"{S}/purchase-orders/{po['id']}", json={"message_draft": "x"})
    assert r.status_code == 409 and r.json()["code"] == "po_locked"

    await owner_client.patch(
        f"{S}/purchase-orders/{po['id']}", json={"expected_at": str(local_today() + timedelta(days=7))}
    )
    po = (await owner_client.post(f"{S}/purchase-orders/{po['id']}/status", json={"to": "sent"})).json()
    assert po["status"] == "sent" and len(po["inbound"]) == 1

    with capture("expense.recorded") as seen:
        po = (
            await owner_client.post(f"{S}/purchase-orders/{po['id']}/payments", json={"amount_vnd": po["total_vnd"]})
        ).json()
    assert po["status"] == "paid"
    ev = seen[0][1]
    assert ev["category"] == "samples" and ev["amount_vnd"] == po["total_vnd"] and ev["purchase_order_id"] == po["id"]
    assert ev["source_key"].startswith(f"po:{po['id']}:pay:")

    line = po["lines"][0]
    r = await owner_client.post(
        f"{S}/purchase-orders/{po['id']}/receive",
        json={"lines": [{"line_id": line["id"], "received_qty": 1, "defect_qty": 2}]},
    )
    assert r.status_code == 400
    po = (
        await owner_client.post(
            f"{S}/purchase-orders/{po['id']}/receive", json={"lines": [{"line_id": line["id"], "received_qty": 1}]}
        )
    ).json()
    assert po["status"] == "received"
    s = (await owner_client.get(f"{S}/suppliers/{sup['id']}")).json()
    assert s["order_count"] == 1 and Decimal(s["on_time_rate"]) == 1 and s["trust_score"] == 80
    assert s["trust_label"] == "Tin được"
    r = await owner_client.delete(f"{S}/suppliers/{sup['id']}")
    assert r.status_code == 409 and r.json()["code"] == "supplier_in_use"


async def test_payment_owner_only_and_not_before_approval(owner_client: httpx.AsyncClient, helper_client) -> None:
    c = await make_candidate()
    po = (
        await owner_client.post(f"{S}/purchase-orders/sample", json={"candidate_id": str(c.id), "quantity": 2})
    ).json()
    assert po["lines"][0]["quantity"] == 2
    r = await owner_client.post(f"{S}/purchase-orders/{po['id']}/payments", json={"amount_vnd": 1000})
    assert r.status_code == 409
    await _approve(owner_client, po["approval_item_id"])
    r = await helper_client.post(f"{S}/purchase-orders/{po['id']}/payments", json={"amount_vnd": 1000})
    assert r.status_code == 403
    r = await owner_client.post(f"/api/desk/control/approvals/{po['approval_item_id']}/approve", json={})
    assert r.status_code == 409


async def test_returned_order_goes_back_to_draft(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate()
    po = (await owner_client.post(f"{S}/purchase-orders/sample", json={"candidate_id": str(c.id)})).json()
    await owner_client.post(
        f"/api/desk/control/approvals/{po['approval_item_id']}/return", json={"note": "Đổi màu xanh"}
    )
    po = (await owner_client.get(f"{S}/purchase-orders/{po['id']}")).json()
    assert po["status"] == "draft" and "Đổi màu xanh" in po["notes"]
    po = (await owner_client.patch(f"{S}/purchase-orders/{po['id']}", json={"message_draft": "您好，要蓝色"})).json()
    po = (await owner_client.post(f"{S}/purchase-orders/{po['id']}/submit")).json()
    assert po["status"] == "pending_approval"
    item = await _approve(owner_client, po["approval_item_id"])
    assert item["status"] == "approved"


async def test_drop_closed_drafts_batch_orders_per_supplier(owner_client: httpx.AsyncClient) -> None:
    s1 = await _supplier(owner_client, "Xưởng A (ví dụ)")
    s2 = await _supplier(owner_client, "Shop B (ví dụ)", language="ja", country="JP")
    c1 = await make_candidate("Giá phơi", supplier_id=uuid.UUID(s1["id"]), stage=CandidateStage.SELECTED)
    c2 = await make_candidate("Hộp gia vị", supplier_id=uuid.UUID(s1["id"]), stage=CandidateStage.SELECTED)
    c3 = await make_candidate("Khăn Imabari", supplier_id=uuid.UUID(s2["id"]), stage=CandidateStage.SELECTED,
                              price_currency="JPY", price_amount=Decimal("1200"))  # fmt: skip
    async with SessionLocal() as s:
        drop = Drop(code="DOT-12", slug="dot-12", title="Đợt 12")
        s.add(drop)
        prods = [Product(candidate_id=c.id, slug=f"sp-{i}", name=c.title_vi) for i, c in enumerate((c1, c2, c3))]
        s.add_all(prods)
        await s.flush()
        items = [DropItem(drop_id=drop.id, product_id=p.id, price_vnd=200000) for p in prods]
        s.add_all(items)
        await s.flush()
        for n, (status, qty) in enumerate(
            [(OrderStatus.CONFIRMED, 2), (OrderStatus.AWAITING_STOCK, 3), (OrderStatus.CANCELLED, 50)]
        ):
            o = Order(code=f"HC-T{n}", status=status, recipient_name="Khách ví dụ", recipient_phone="0900000000",
                      placed_at=now_utc())  # fmt: skip
            s.add(o)
            await s.flush()
            for it in items:
                s.add(OrderItem(order_id=o.id, product_id=it.product_id, drop_item_id=it.id, name="x", quantity=qty))
        await s.commit()
        for _ in range(2):  # chạy lặp lại không sinh trùng
            await events.emit("drop.closed", {"drop_id": str(drop.id)}, db=s)
            await s.commit()
        pos = list((await s.execute(select(PurchaseOrder).where(PurchaseOrder.drop_id == drop.id))).scalars())
    assert len(pos) == 2
    by = {str(p.supplier_id): p for p in pos}
    a = by[s1["id"]]
    assert a.kind.value == "batch" and a.status.value == "pending_approval"
    assert sorted(ln.quantity for ln in a.lines) == [5, 5]
    assert "订购" in a.message_draft
    b = by[s2["id"]]
    assert b.currency == "JPY" and "注文" in b.message_draft
    async with SessionLocal() as s:
        locked = (await s.execute(select(ApprovalItem).where(ApprovalItem.action == "supply.place_order"))).scalars()
        assert {i.status for i in locked} == {ApprovalStatus.PENDING}


# ---- d6 ------------------------------------------------------------------------------------------------------------


async def test_supplier_inquiry_and_reply(owner_client: httpx.AsyncClient) -> None:
    sup = await _supplier(owner_client)
    c = await make_candidate()
    r = await owner_client.post(
        f"{S}/suppliers/{sup['id']}/messages/inquiry",
        json={"candidate_id": str(c.id), "topics": ["price", "moq", "lead_time"], "quantity": 200},
    )
    assert r.status_code == 201, r.text
    msg = r.json()
    assert msg["status"] == "pending_review" and "起订量" in msg["body_original"] and "200" in msg["body_vi"]
    r = await owner_client.post(f"{S}/messages/{msg['id']}/sent", json={})
    assert r.status_code == 409
    await _approve(owner_client, msg["approval_item_id"])
    sent = (await owner_client.post(f"{S}/messages/{msg['id']}/sent", json={"channel": "wechat"})).json()
    assert sent["status"] == "sent" and sent["channel"] == "wechat"

    r = await owner_client.post(
        f"{S}/suppliers/{sup['id']}/messages/reply",
        json={"body_original": "亲，单价28元，100件起订，下单后3天发货，包邮"},
    )
    assert r.status_code == 201, r.text
    reply = r.json()
    assert reply["direction"] == "inbound" and reply["body_vi"]
    ex = reply["extracted"]
    assert ex["unit_price"] == 28 and ex["moq"] == 100 and ex["lead_days"] == 3 and ex["currency"] == "CNY"
    msgs = (await owner_client.get(f"{S}/suppliers/{sup['id']}/messages")).json()
    assert [m["direction"] for m in msgs] == ["outbound", "inbound"]


# ---- d7 ------------------------------------------------------------------------------------------------------------


async def test_inbound_milestones_and_arrived_once(owner_client: httpx.AsyncClient) -> None:
    ship = (await owner_client.post(f"{S}/inbound", json={"code": "KIEN-01"})).json()
    assert ship["status"] == "ordered" and len(ship["milestones"]) == 1
    with capture("inbound.arrived") as seen:
        for st in ("at_agent_warehouse", "customs", "delivered", "delivered"):
            r = await owner_client.post(f"{S}/inbound/{ship['id']}/milestones", json={"status": st, "note": "Ví dụ"})
            assert r.status_code == 200
    assert seen == [("inbound.arrived", {"inbound_shipment_id": ship["id"]})]
    got = (await owner_client.get(f"{S}/inbound/{ship['id']}")).json()
    assert got["received_at"] and len(got["milestones"]) == 5
    r = await owner_client.post(f"{S}/inbound/{ship['id']}/sync")
    assert r.status_code == 400 and r.json()["code"] == "no_tracking"


async def test_inbound_sync_from_mock_shipping(owner_client: httpx.AsyncClient) -> None:
    drv = get_driver("shipping")
    created = await drv.create(
        ShippingRequest(
            order_code="LO-1", to=Address(name="Kho", phone="0900000000", address_line="x", province="Hà Nội")
        ),
        "standard",
    )
    ship = (await owner_client.post(f"{S}/inbound", json={"tracking_code": created.tracking_code})).json()
    drv.advance(2)  # created → picked_up → in_transit
    got = (await owner_client.post(f"{S}/inbound/{ship['id']}/sync")).json()
    assert got["status"] == "international_transit"
    assert [m["source"] for m in got["milestones"]] == ["manual", "shipping", "shipping"]
    drv.advance(5)
    with capture("inbound.arrived") as seen:
        got = (await owner_client.post(f"{S}/inbound/{ship['id']}/sync")).json()
        await owner_client.post(f"{S}/inbound/{ship['id']}/sync")
    assert got["status"] == "delivered" and len(seen) == 1


# ---- d4 ------------------------------------------------------------------------------------------------------------


async def test_provenance_documents_and_warnings(owner_client: httpx.AsyncClient) -> None:
    sup = await _supplier(owner_client)
    c = await make_candidate(supplier_id=uuid.UUID(sup["id"]))
    po = (
        await owner_client.post(
            f"{S}/purchase-orders",
            json={"kind": "batch", "supplier_id": sup["id"], "lines": [
                {"candidate_id": str(c.id), "description": "X型晾衣架", "quantity": 40, "unit_price_amount": "28"}]},
        )
    ).json()  # fmt: skip
    assert po["status"] == "pending_approval" and po["total_vnd"] == 40 * 28 * 3650
    assert (await owner_client.get(f"{S}/documents/warnings")).json() == []  # chưa duyệt thì chưa nhắc
    await _approve(owner_client, po["approval_item_id"])
    warn = (await owner_client.get(f"{S}/documents/warnings")).json()
    assert warn[0]["missing"] == ["invoice", "original_label"] and warn[0]["missing_labels"][0] == "Hoá đơn mua"

    r = await owner_client.post(
        f"{S}/documents",
        data={"kind": "invoice", "purchase_order_id": po["id"], "doc_number": "HD-001"},
        files={"file": ("hoa-don.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["supplier_id"] == sup["id"] and doc["url"].startswith("/api/files/private/provenance/")
    po = (await owner_client.post(f"{S}/purchase-orders/{po['id']}/status", json={"to": "sent"})).json()
    ship_id = po["inbound"][0]["id"]
    r = await owner_client.post(
        f"{S}/documents",
        data={"kind": "original_label", "inbound_shipment_id": ship_id},
        files={"file": ("nhan.jpg", b"\xff\xd8\xff fake", "image/jpeg")},
    )
    assert r.status_code == 201
    assert (await owner_client.get(f"{S}/documents/warnings")).json() == []
    assert len((await owner_client.get(f"{S}/documents", params={"purchase_order_id": po["id"]})).json()) == 2
    ship = (await owner_client.get(f"{S}/inbound/{ship_id}")).json()
    assert ship["missing_documents"] == [] and ship["po_code"] == po["code"]

    r = await owner_client.post(
        f"{S}/documents", data={"kind": "invoice", "purchase_order_id": po["id"]},
        files={"file": ("a.txt", b"hi", "text/plain")},
    )  # fmt: skip
    assert r.status_code == 400
    r = await owner_client.post(
        f"{S}/documents", data={"kind": "invoice"}, files={"file": ("a.pdf", b"%PDF", "application/pdf")}
    )
    assert r.status_code == 400
    assert (await owner_client.delete(f"{S}/documents/{doc['id']}")).status_code == 204
    assert (await owner_client.get(f"{S}/documents/warnings")).json()[0]["missing"] == ["invoice"]


async def test_suppliers_crud_and_search(owner_client: httpx.AsyncClient, client) -> None:
    assert (await client.get(f"{S}/suppliers")).status_code == 401
    a = await _supplier(owner_client, "Shop Khăn Nhật (ví dụ)", kind="shop", language="ja", country="jp")
    assert a["country"] == "JP" and a["trust_label"] == "Chưa có lịch sử"
    await _supplier(owner_client, "Bên mua hộ Quảng Châu (ví dụ)", kind="purchasing_agent", agent_fee_pct="3")
    got = (await owner_client.get(f"{S}/suppliers", params={"q": "khăn"})).json()
    assert got["total"] == 1
    got = (await owner_client.get(f"{S}/suppliers", params={"kind": "purchasing_agent"})).json()
    assert Decimal(got["items"][0]["agent_fee_pct"]) == 3
    r = await owner_client.patch(f"{S}/suppliers/{a['id']}", json={"is_blocked": True, "notes": "Giao chậm"})
    assert r.json()["trust_label"] == "Đã chặn"
    c = await make_candidate()
    r = await owner_client.post(f"{S}/purchase-orders/sample", json={"candidate_id": str(c.id), "supplier_id": a["id"]})
    assert r.status_code == 400 and r.json()["code"] == "supplier_blocked"
    assert (await owner_client.delete(f"{S}/suppliers/{a['id']}")).status_code == 204
