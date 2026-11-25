"""Theo dõi hai chiều một sản phẩm ở desk: Hồ sơ chọn (dấu vết), Hồ sơ bán (nội dung → kênh → khách), dòng danh sách."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.modules.assistant.models import AssistantConversation, ConversationStatus
from app.modules.catalog.models import InventoryItem, Product, Review, ReviewStatus
from app.modules.content.models import (
    ContentDraft,
    DraftFormat,
    DraftStatus,
    PostMetric,
    PostStatus,
    ScheduledPost,
)
from app.modules.inbox.models import Thread, ThreadKind
from app.modules.orders.models import (
    Customer,
    ListingStatus,
    MarketplaceListing,
    Order,
    OrderItem,
    OrderStatus,
)
from app.modules.selection.models import TrialNote, TrialNoteKind
from app.modules.supply.models import CostSheet, POKind, POStatus, PurchaseOrder
from tests.catalog.factories import published_product

PREFIX = "/api/desk/catalog/products"


async def _clean_drafts(db, p: Product) -> None:
    """Đăng trang thì xưởng nội dung tự soạn bài; test tự dựng bản nháp để biết chắc trạng thái từng kênh."""
    await db.execute(delete(ScheduledPost).where(ScheduledPost.product_id == p.id))
    await db.execute(delete(ContentDraft).where(ContentDraft.product_id == p.id))


def _order(code: str, status: OrderStatus, *, customer: Customer | None, paid: bool, channel=Channel.WEB) -> Order:
    return Order(
        code=code, status=status, channel=channel, customer_id=customer.id if customer else None,
        recipient_name="Khách ví dụ", recipient_phone="0900000000", placed_at=now_utc(),
        paid_at=now_utc() if paid else None,
    )  # fmt: skip


async def _add_order(db, p: Product, o: Order, qty: int, price: int = 385_000) -> None:
    db.add(o)
    await db.flush()
    db.add(OrderItem(order_id=o.id, product_id=p.id, name=p.name, quantity=qty, unit_price_vnd=price,
                     line_total_vnd=qty * price))  # fmt: skip


async def _seed_sales(db, p: Product) -> dict[str, ScheduledPost]:
    await _clean_drafts(db, p)
    fb = ContentDraft(product_id=p.id, channel=Channel.FACEBOOK, format=DraftFormat.POST, status=DraftStatus.PUBLISHED)
    ig = ContentDraft(product_id=p.id, channel=Channel.INSTAGRAM, format=DraftFormat.CAROUSEL,
                      status=DraftStatus.SCHEDULED)  # fmt: skip
    th = ContentDraft(product_id=p.id, channel=Channel.THREADS, format=DraftFormat.POST,
                      status=DraftStatus.PENDING_REVIEW)  # fmt: skip
    tt = ContentDraft(product_id=p.id, channel=Channel.TIKTOK, format=DraftFormat.VIDEO_SCRIPT,
                      status=DraftStatus.DRAFTING)  # fmt: skip
    db.add_all([fb, ig, th, tt])  # Zalo: chưa soạn
    await db.flush()
    fb_post = ScheduledPost(draft_id=fb.id, product_id=p.id, channel=Channel.FACEBOOK, status=PostStatus.PUBLISHED,
                            scheduled_at=now_utc() - timedelta(days=2), published_at=now_utc() - timedelta(days=2),
                            external_post_id="fb_1", external_url="https://facebook.example/p/1")  # fmt: skip
    ig_post = ScheduledPost(draft_id=ig.id, product_id=p.id, channel=Channel.INSTAGRAM, status=PostStatus.APPROVED,
                            scheduled_at=now_utc() + timedelta(days=1))  # fmt: skip
    db.add_all([fb_post, ig_post])
    await db.flush()
    db.add(PostMetric(scheduled_post_id=fb_post.id, captured_at=now_utc() - timedelta(days=1), reach=100, clicks=1))
    db.add(PostMetric(scheduled_post_id=fb_post.id, captured_at=now_utc(), reach=900, clicks=40, likes=30,
                      comments=5, messages_started=3, orders_attributed=1, revenue_attributed_vnd=385_000))  # fmt: skip

    ha, minh = Customer(name="Hà (ví dụ)"), Customer(name="Minh (ví dụ)")
    db.add_all([ha, minh])
    await db.flush()
    tag = uuid.uuid4().hex[:6].upper()
    await _add_order(db, p, _order(f"T{tag}1", OrderStatus.DELIVERED, customer=ha, paid=True), 2)
    await _add_order(
        db, p, _order(f"T{tag}2", OrderStatus.CONFIRMED, customer=ha, paid=True, channel=Channel.FACEBOOK), 1
    )
    await _add_order(db, p, _order(f"T{tag}3", OrderStatus.PENDING_PAYMENT, customer=minh, paid=False), 1)
    await _add_order(db, p, _order(f"T{tag}4", OrderStatus.CANCELLED, customer=minh, paid=False), 5)
    await _add_order(db, p, _order(f"T{tag}5", OrderStatus.DRAFT, customer=None, paid=False), 1)

    db.add(Thread(channel=Channel.FACEBOOK, kind=ThreadKind.DIRECT_MESSAGE, external_thread_id=uuid.uuid4().hex,
                  product_id=p.id, participant_name="Lan (ví dụ)", snippet="Còn hàng không?", needs_owner=True,
                  last_message_at=now_utc()))  # fmt: skip
    db.add(AssistantConversation(session_key=uuid.uuid4().hex, product_id=p.id, message_count=4,
                                 status=ConversationStatus.HANDED_OFF))  # fmt: skip
    db.add(AssistantConversation(session_key=uuid.uuid4().hex, product_id=p.id, message_count=2))
    db.add(Review(product_id=p.id, token=uuid.uuid4().hex, status=ReviewStatus.PUBLISHED, rating=5))
    db.add(Review(product_id=p.id, token=uuid.uuid4().hex, status=ReviewStatus.PENDING_REVIEW, rating=4))
    db.add(InventoryItem(product_id=p.id, on_hand=10, reserved=3, low_stock_threshold=8))
    db.add(MarketplaceListing(marketplace=Channel.SHOPEE, product_id=p.id, status=ListingStatus.ACTIVE,
                              external_id="sp_1", price_vnd=399_000))  # fmt: skip
    await db.flush()
    return {"fb": fb_post, "ig": ig_post}


async def test_sales_requires_login(db, client, helper_client):
    p = await published_product(db)
    await db.commit()
    for path in (f"{PREFIX}/{p.id}/sales", f"{PREFIX}/{p.id}/selection", f"{PREFIX}/pipeline"):
        assert (await client.get(path)).status_code == 401
        assert (await helper_client.get(path)).status_code == 200  # người phụ giúp cũng xem được
    assert (await helper_client.get(f"{PREFIX}/{uuid.uuid4()}/sales")).status_code == 404


async def test_sales_aggregates_content_channels_and_customers(db, owner_client):
    p = await published_product(db)
    await _seed_sales(db, p)
    await db.commit()

    r = await owner_client.get(f"{PREFIX}/{p.id}/sales")
    assert r.status_code == 200, r.text
    d = r.json()

    content = d["content"]
    assert content["website"]["state"] == "approved"
    states = {c["channel"]: c["state"] for c in content["channels"]}
    assert states == {"facebook": "approved", "instagram": "approved", "threads": "pending", "tiktok": "drafting",
                      "zalo_oa": "none"}  # fmt: skip
    assert (content["ready"], content["total"]) == (3, 6)

    live = d["live"]
    assert live["website"]["published"] and live["website"]["url"].endswith(f"/san-pham/{p.slug}")
    assert live["channels_live"] == ["Website", "Facebook", "Shopee"]  # bài Instagram mới hẹn giờ, chưa đăng
    posts = {x["channel"]: x for x in live["posts"]}
    assert posts["instagram"]["status"] == "approved" and posts["instagram"]["metrics"] is None
    assert posts["facebook"]["metrics"]["reach"] == 900  # bản đo mới nhất, không cộng dồn
    assert posts["facebook"]["simulated"] is True  # SOCIAL_DRIVER=mock trong test
    assert live["marketplaces"][0]["label"] == "Shopee" and live["marketplaces_simulated"] is True

    cu = d["customers"]
    assert cu["posts"]["reach"] == 900 and cu["posts"]["interactions"] == 35 and cu["posts"]["messages"] == 3
    assert cu["posts"]["orders_from_posts"] == 1 and cu["posts"]["simulated"] is True
    o = cu["orders"]
    # đơn còn sống: giao xong + xác nhận + chờ chuyển khoản; không tính đơn nháp và đơn huỷ
    assert (o["count"], o["units"]) == (3, 4)
    assert o["revenue_vnd"] == 3 * 385_000 and o["unpaid_vnd"] == 385_000
    assert (o["customers"], o["repeat_buyers"], o["drafts"], o["cancelled"]) == (2, 1, 1, 1)
    assert {x["label"]: x["count"] for x in o["by_channel"]} == {"Website": 2, "Facebook": 1}
    assert {x["status"] for x in o["by_status"]} == {"delivered", "confirmed", "pending_payment", "cancelled", "draft"}
    assert len(o["recent"]) == 5
    assert cu["inbox"]["threads"] == 1 and cu["inbox"]["needs_owner"] == 1
    assert cu["assistant"] == {"conversations": 2, "handed_off": 1, "messages": 6}
    assert cu["stock"] == {"sale_mode": p.sale_mode.value, "tracked": True, "on_hand": 10, "reserved": 3,
                           "available": 7, "low": True}  # fmt: skip
    assert cu["reviews"]["published"] == 1 and cu["reviews"]["waiting_owner"] == 1


async def test_sales_empty_product(db, owner_client):
    p = await published_product(db)
    await _clean_drafts(db, p)
    await db.commit()
    d = (await owner_client.get(f"{PREFIX}/{p.id}/sales")).json()
    assert d["content"]["ready"] == 1  # chỉ trang website
    assert all(c["state"] == "none" for c in d["content"]["channels"])
    assert d["live"]["posts"] == [] and d["live"]["marketplaces"] == []
    assert d["customers"]["orders"]["count"] == 0 and d["customers"]["posts"]["measured_posts"] == 0
    assert d["customers"]["stock"]["tracked"] is False


async def test_selection_trail(db, owner_client, owner):
    p = await published_product(db, trial_days=14)
    c_id = p.candidate_id
    db.add(TrialNote(candidate_id=c_id, kind=TrialNoteKind.TEXT, text="Ngày 3: nắp kín, không rò",
                     recorded_at=now_utc() - timedelta(days=2), trial_day=3))  # fmt: skip
    db.add(PurchaseOrder(code=f"PO{uuid.uuid4().hex[:8]}", kind=POKind.SAMPLE, status=POStatus.RECEIVED,
                         candidate_id=c_id, total_vnd=320_000, received_at=now_utc()))  # fmt: skip
    db.add(CostSheet(candidate_id=c_id, unit_price_amount=Decimal("1500"), currency="JPY", fx_rate=Decimal("170"),
                     unit_price_vnd=255_000, landed_cost_vnd=231_000,
                     breakdown=[{"label": "Giá gốc", "amount_vnd": 200_000}, {"label": "Cước", "amount_vnd": 31_000}]))  # fmt: skip
    await db.commit()

    r = await owner_client.get(f"{PREFIX}/{p.id}/selection")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["candidate_id"] == str(c_id)
    assert d["hunt"]["brief_title"].startswith("Đề ") and d["hunt"]["platform"] == "Rakuten"
    assert d["assessment"]["summary"].startswith("Bình inox") and d["assessment"]["safety_label"] == "Chưa kiểm"
    assert [s["code"] for s in d["samples"]] and d["samples"][0]["status_label"] == "Đã nhận"
    assert d["trial"]["trial_days"] == 14 and d["trial"]["note_count"] == 1
    assert d["trial"]["notes"][0]["text"].startswith("Ngày 3")
    assert d["decision"]["reason_selected"].startswith("Giữ nóng") and d["decision"]["not_satisfied"] == "Miệng hẹp."
    cost = d["cost"]
    assert cost["landed_cost_vnd"] == 231_000 and cost["price_vnd"] == 385_000
    assert cost["margin_pct"] == 40.0 and [b["label"] for b in cost["breakdown"]] == ["Giá gốc", "Cước"]


async def test_selection_trail_without_candidate(db, owner_client):
    p = Product(slug=f"mon-tu-them-{uuid.uuid4().hex[:6]}", name="Món chị tự thêm", price_vnd=100_000)
    db.add(p)
    await db.commit()
    d = (await owner_client.get(f"{PREFIX}/{p.id}/selection")).json()
    assert d["candidate_id"] is None and d["hunt"] is None and d["samples"] == []
    assert d["cost"]["price_vnd"] == 100_000 and d["cost"]["margin_pct"] is None


async def test_pipeline_rows(db, owner_client):
    p = await published_product(db, name="Bình giữ nhiệt 480 ml")
    await _seed_sales(db, p)
    q = await published_product(db, name="Hộp đựng gia vị")
    await _clean_drafts(db, q)
    await db.commit()

    r = await owner_client.get(f"{PREFIX}/pipeline")
    assert r.status_code == 200
    rows = {x["product_id"]: x for x in r.json()}
    a, b = rows[str(p.id)], rows[str(q.id)]
    assert (a["content_ready"], a["content_total"]) == (3, 6)
    assert a["channels_live"] == ["Website", "Facebook", "Shopee"]
    assert (a["orders"], a["units"], a["revenue_vnd"]) == (3, 4, 3 * 385_000)
    assert a["trial_days"] == 21 and a["chosen_at"] is not None
    assert (b["content_ready"], b["channels_live"], b["orders"]) == (1, ["Website"], 0)
