"""e8 đánh giá có ảnh: order.delivered → lời mời một lần → khách gửi → AI lọc → chị duyệt → review.published."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app import control
from app.core import events
from app.core.timeutil import now_utc
from app.integrations import get_driver
from app.modules.catalog.models import Review, ReviewStatus
from app.modules.control.models import ApprovalItem, ApprovalStatus, AutonomyLevel
from tests.catalog.factories import jpeg, published_product


@pytest.fixture
def review_events():
    seen: list[dict] = []

    async def listener(db, payload):
        seen.append(payload)

    events.on("review.published")(listener)
    yield seen
    events._handlers["review.published"].remove(listener)


async def _delivered(db):
    from app.modules.orders.models import Order, OrderItem, OrderStatus

    p = await published_product(db)
    o = Order(code="HCTEST9", status=OrderStatus.DELIVERED, recipient_name="Nguyễn Thị Ví Dụ",
              recipient_phone="0000000009", placed_at=now_utc())  # fmt: skip
    db.add(o)
    await db.flush()
    db.add(OrderItem(order_id=o.id, product_id=p.id, name=p.name, quantity=1))
    db.add(OrderItem(order_id=o.id, product_id=None, name="Phí gói quà", quantity=1))
    await db.flush()
    await events.emit("order.delivered", {"order_id": str(o.id)}, db=db)
    await events.emit("order.delivered", {"order_id": str(o.id)}, db=db)  # lặp lại không sinh trùng
    await db.commit()
    r = (await db.execute(select(Review).where(Review.order_id == o.id))).scalars().all()
    return p, o, r


async def test_delivery_creates_one_invite_per_item(db, owner_client):
    _p, _o, reviews = await _delivered(db)
    assert len(reviews) == 1
    r = reviews[0]
    assert r.status == ReviewStatus.REQUESTED and r.display_name == "Dụ" and len(r.token) >= 20
    item = (
        await db.execute(select(ApprovalItem).where(ApprovalItem.action == "catalog.send_review_request"))
    ).scalar_one()
    assert f"/danh-gia/{r.token}" in item.preview["text"]
    res = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert res.status_code == 200 and res.json()["status"] == "approved"
    sent = get_driver("notify").outbox
    assert sent[0].to == "0000000009" and r.token in sent[0].text


async def test_customer_submits_and_owner_publishes(db, client, owner_client, review_events):
    p, _, (r,) = await _delivered(db)
    inv = (await client.get(f"/api/store/catalog/reviews/{r.token}")).json()
    assert inv["status"] == "requested" and inv["product_name"] == p.name
    res = await client.post(
        f"/api/store/catalog/reviews/{r.token}",
        data={"rating": "5", "body": "Giữ nóng đúng như chị nói, nắp dễ rửa.", "display_name": "Lan"},
        files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))],
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "pending_review"
    again = await client.post(f"/api/store/catalog/reviews/{r.token}", data={"rating": "4"})
    assert again.status_code == 409 and again.json()["code"] == "review_already_submitted"

    pending = (await owner_client.get("/api/desk/catalog/reviews", params={"status": "pending_review"})).json()
    assert pending["total"] == 1 and pending["items"][0]["ai_flags"]["recommend"] == "publish"
    assert pending["items"][0]["photo_urls"][0]
    res = await owner_client.post(f"/api/desk/catalog/reviews/{r.id}/approve")
    assert res.json()["status"] == "published"
    assert review_events == [{"review_id": str(r.id), "product_id": str(p.id)}]
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    assert pub["review_count"] == 1 and pub["rating_avg"] == 5.0
    assert pub["reviews"][0]["display_name"] == "Lan" and pub["reviews"][0]["photos"][0]["thumb"]
    res = await owner_client.patch(f"/api/desk/catalog/reviews/{r.id}", json={"owner_reply": "Cảm ơn bạn!"})
    assert res.json()["owner_reply"] == "Cảm ơn bạn!"
    res = await owner_client.post(f"/api/desk/catalog/reviews/{r.id}/reject", json={})
    assert res.json()["status"] == "hidden"
    assert (await client.get(f"/api/store/catalog/products/{p.slug}")).json()["review_count"] == 0


async def test_flagged_review_is_never_auto_published(db, client):
    await control.set_level(db, "catalog.publish_review", AutonomyLevel.AUTO, None)
    _, _, (r,) = await _delivered(db)
    res = await client.post(f"/api/store/catalog/reviews/{r.token}",
                            data={"rating": "1", "body": "Hàng dởm vcl, inbox mình 0000 000 000 bán rẻ hơn"})  # fmt: skip
    assert res.json()["status"] == "hidden"
    await db.refresh(r)
    assert r.ai_flags["offensive"] and r.ai_flags["spam"] and r.ai_flags["personal_info"]


async def test_honest_low_rating_is_recommended_for_publish(db, client, owner_client):
    _, _, (r,) = await _delivered(db)
    await client.post(f"/api/store/catalog/reviews/{r.token}", data={"rating": "2", "body": "Miệng bình hẹp, khó rửa."})
    await db.refresh(r)
    assert r.ai_flags["recommend"] == "publish"
    res = await owner_client.post(f"/api/desk/catalog/reviews/{r.id}/reject", json={"note": "Trùng đơn"})
    assert res.json()["status"] == "rejected"
    item = (await db.execute(select(ApprovalItem).where(ApprovalItem.ref_id == r.id))).scalar_one()
    assert item.status == ApprovalStatus.RETURNED


async def test_bad_token_and_validation(db, client):
    assert (await client.get("/api/store/catalog/reviews/khong-co")).status_code == 404
    _, _, (r,) = await _delivered(db)
    res = await client.post(f"/api/store/catalog/reviews/{r.token}", data={"rating": "9"})
    assert res.status_code == 422
    files = [("photos", (f"{i}.jpg", jpeg(), "image/jpeg")) for i in range(5)]
    res = await client.post(f"/api/store/catalog/reviews/{r.token}", data={"rating": "5"}, files=files)
    assert res.status_code == 400


async def test_choice_reason_flows_to_public_page_only_when_published_and_public(db, client, owner_client):
    p, _, (r,) = await _delivered(db)
    res = await client.post(
        f"/api/store/catalog/reviews/{r.token}",
        data={"rating": "5", "body": "Dùng ổn.", "display_name": "Lan", "choice_reason": "  Cần bình nhỏ  bỏ túi. "},
    )
    assert res.status_code == 200, res.text
    assert res.json()["choice_reason"] == "Cần bình nhỏ bỏ túi."
    pending = (await owner_client.get("/api/desk/catalog/reviews", params={"status": "pending_review"})).json()
    row = pending["items"][0]
    assert row["choice_reason"] == "Cần bình nhỏ bỏ túi." and row["reason_public"] is True
    item = (await db.execute(select(ApprovalItem).where(ApprovalItem.ref_id == r.id))).scalar_one()
    assert item.preview["choice_reason"] == "Cần bình nhỏ bỏ túi."

    # chưa duyệt → website chưa có
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    assert pub["customer_reasons"] == []

    await owner_client.post(f"/api/desk/catalog/reviews/{r.id}/approve")
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    assert pub["customer_reasons"] == [{"display_name": "Lan", "text": "Cần bình nhỏ bỏ túi."}]

    # chị ẩn riêng lý do: đánh giá vẫn hiện, câu trả lời của chị không bị xoá
    await owner_client.patch(f"/api/desk/catalog/reviews/{r.id}", json={"owner_reply": "Cảm ơn bạn!"})
    res = await owner_client.patch(f"/api/desk/catalog/reviews/{r.id}", json={"reason_public": False})
    assert res.status_code == 200
    assert res.json()["reason_public"] is False and res.json()["owner_reply"] == "Cảm ơn bạn!"
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    assert pub["customer_reasons"] == [] and pub["review_count"] == 1

    # hiện lại lý do, rồi ẩn cả đánh giá → lý do cũng mất
    await owner_client.patch(f"/api/desk/catalog/reviews/{r.id}", json={"reason_public": True})
    assert (await client.get(f"/api/store/catalog/products/{p.slug}")).json()["customer_reasons"]
    await owner_client.post(f"/api/desk/catalog/reviews/{r.id}/reject", json={})
    assert (await client.get(f"/api/store/catalog/products/{p.slug}")).json()["customer_reasons"] == []


async def test_choice_reason_is_moderated_and_length_limited(db, client):
    _, _, (r,) = await _delivered(db)
    res = await client.post(f"/api/store/catalog/reviews/{r.token}", data={"rating": "5", "choice_reason": "x" * 301})
    assert res.status_code == 422
    res = await client.post(
        f"/api/store/catalog/reviews/{r.token}",
        data={"rating": "5", "body": "Dùng ổn.", "choice_reason": "Vì rẻ, inbox mình 0000 000 000 nhé"},
    )
    assert res.status_code == 200
    await db.refresh(r)
    assert r.ai_flags["personal_info"] and r.ai_flags["recommend"] == "hide"


async def test_content_facts_quote_only_approved_public_reasons(db, client, owner_client):
    from app.modules.content import facts

    p, _, (r,) = await _delivered(db)
    await client.post(f"/api/store/catalog/reviews/{r.token}",
                      data={"rating": "5", "display_name": "Lan", "choice_reason": "Cần bình nhỏ bỏ túi."})  # fmt: skip
    await db.refresh(p, ["images"])
    assert (await facts.product_facts_full(db, p)).customer_reasons == []
    await owner_client.post(f"/api/desk/catalog/reviews/{r.id}/approve")
    pf = await facts.product_facts_full(db, p)
    assert [(q.name, q.text) for q in pf.customer_reasons] == [("Lan", "Cần bình nhỏ bỏ túi.")]
    await owner_client.patch(f"/api/desk/catalog/reviews/{r.id}", json={"reason_public": False})
    assert (await facts.product_facts_full(db, p)).customer_reasons == []
