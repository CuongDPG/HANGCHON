"""Vòng đời trọn vẹn của một món hàng qua mọi module (AI fake, driver mock), mỗi bước kiểm dữ liệu thật.

ra đề → quét ứng viên → thẩm định, chấm điểm → mua mẫu (đơn đặt mẫu chờ duyệt) → đang thử, ghi chú → Đã chọn (AI soạn
lý do, chị chốt) → sản phẩm nháp → giá vốn, duyệt giá → duyệt và đăng sản phẩm → bài các kênh, soát lời, duyệt, lịch,
tới giờ đăng → mở đợt → khách thấy con dấu + lý do chọn → giỏ, đặt, chuyển khoản → đã trả, khách nhận tin, sổ doanh
thu → khách nhắn, AI soạn, chị gửi → đóng đợt → đơn đặt nguồn, chị duyệt → lô về → vận đơn → giao xong → mời đánh giá,
khách gửi, chị duyệt → «Hôm nay», nhật ký AI, báo cáo tuần."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.jobs import JOBS, job_context
from app.core.timeutil import local_today, now_utc
from app.integrations import get_driver
from app.modules.catalog.models import Drop, DropItem, DropStatus, Product, ProductStatus, Review, ReviewStatus
from app.modules.content.models import PostStatus, ScheduledPost
from app.modules.content.schedule import src_code
from app.modules.finance.models import LedgerEntry, LedgerKind
from app.modules.orders.models import Customer, Notification, Order, OrderStatus
from app.modules.sourcing.models import Candidate, CandidateStage
from app.modules.supply.models import POKind, PurchaseOrder
from tests.orders.conftest import send_transfer

BRIEF = "Tìm bình giữ nhiệt inox 304 khoảng 500 ml, giữ nóng lâu, dưới 250k về tay, ưu tiên hàng Nhật"
ADDRESS = {"address_line": "12 Ngõ Ví Dụ", "ward": "Phường Mẫu", "district": "Quận Mẫu", "province": "Hà Nội"}


async def ok(r: httpx.Response, code: int = 200) -> dict:
    assert r.status_code == code, f"{r.request.method} {r.request.url} → {r.status_code}: {r.text}"
    return r.json()


async def approve_pending(c: httpx.AsyncClient, action: str, payload: dict | None = None, **params) -> dict:
    """Duyệt việc chờ mới nhất của một action (chị bấm duyệt ở «Chờ duyệt»)."""
    items = (await ok(await c.get("/api/desk/control/approvals", params={"status": "pending", "action": action})))[
        "items"
    ]
    assert items, f"không có việc chờ {action}"
    item = next((i for i in items if all(str(i.get(k)) == str(v) for k, v in params.items())), items[0])
    return await ok(
        await c.post(f"/api/desk/control/approvals/{item['id']}/approve", json={"payload": payload} if payload else {})
    )


async def test_one_product_full_lifecycle(owner_client: httpx.AsyncClient, client: httpx.AsyncClient) -> None:
    c = owner_client
    D = "/api/desk"

    # ---- a1 + a4: ra đề, AI hiểu, quét nhiều nguồn ------------------------------------------------------------
    brief = await ok(await c.post(f"{D}/sourcing/briefs", json={"text": BRIEF}), 201)
    assert brief["interpretation"] and brief["keywords_translated"]
    run = await ok(await c.post(f"{D}/sourcing/briefs/{brief['id']}/run"))
    assert run["status"] == "succeeded"
    cands = (await ok(await c.get(f"{D}/sourcing/briefs/{brief['id']}/candidates", params={"size": 50})))["items"]
    assert len(cands) >= 2
    cid = cands[0]["id"]

    # ---- b1–b7: thẩm định, chấm điểm, chị xác nhận ------------------------------------------------------------
    a = await ok(await c.post(f"{D}/assessment/candidates/{cid}/run", json={}))
    assert a["status"] == "ready" and a["score_status"] == "ai_draft"
    await ok(await c.patch(f"{D}/assessment/assessments/{a['id']}/scores/chat_luong", json={"owner_score": 9}))
    a = await ok(await c.post(f"{D}/assessment/assessments/{a['id']}/confirm-score"))
    assert a["score_status"] == "confirmed"
    async with SessionLocal() as s:
        cand = await s.get(Candidate, uuid.UUID(cid))
        assert abs(cand.ai_score - float(a["score_total"])) <= 0.5  # sourcing nghe candidate.assessed

    # ---- d1/d5: mua mẫu từ hồ sơ thẩm định → đơn đặt mẫu chờ chị (luôn hỏi) ------------------------------------
    sup = await ok(
        await c.post(f"{D}/supply/suppliers", json={"name": "Xưởng Ví Dụ", "kind": "factory", "platform": "1688"}),
        201,
    )
    async with SessionLocal() as s:
        cand = await s.get(Candidate, uuid.UUID(cid))
        cand.supplier_id = uuid.UUID(sup["id"])
        await s.commit()
    await ok(await c.post(f"{D}/selection/candidates/{cid}/stage", json={"to": "sample"}))
    pos = (await ok(await c.get(f"{D}/supply/purchase-orders", params={"candidate_id": cid})))["items"]
    assert len(pos) == 1 and pos[0]["kind"] == "sample" and pos[0]["status"] == "pending_approval"
    await ok(await c.post(f"{D}/control/approvals/{pos[0]['approval_item_id']}/approve", json={}))
    assert (await ok(await c.get(f"{D}/supply/purchase-orders/{pos[0]['id']}")))["status"] == "approved"

    # ---- c1/c2: đang thử, ghi chú thử ----------------------------------------------------------------------------
    await ok(await c.post(f"{D}/selection/candidates/{cid}/stage", json={"to": "trial"}))
    for text in ("Giữ nóng 8 tiếng, nước vẫn ấm tới chiều", "Nắp kín, lật ngược không rỉ", "Hộp hơi móp khi giao"):
        await ok(await c.post(f"{D}/selection/candidates/{cid}/notes", data={"text": text}), 201)
    detail = await ok(await c.get(f"{D}/selection/candidates/{cid}"))
    assert len(detail["notes"]) == 3

    # ---- c3: Đã chọn → AI soạn lý do, chị sửa rồi chốt → sản phẩm nháp tự sinh (e1) ----------------------------
    st = await ok(await c.post(f"{D}/selection/candidates/{cid}/stage", json={"to": "selected"}))
    d = st["decision"]
    assert d["draft_status"] == "pending_review" and d["draft_reasons_list"]
    await ok(
        await c.post(
            f"{D}/selection/decisions/{d['id']}/approve",
            json={"reason_selected": ["Giữ nóng tới chiều.", "Nắp kín, không rỉ."], "not_satisfied": ["Hộp móp."]},
        )
    )
    async with SessionLocal() as s:
        product = (await s.execute(select(Product).where(Product.candidate_id == uuid.UUID(cid)))).scalar_one()
        assert product.status in (ProductStatus.DRAFT, ProductStatus.PENDING_REVIEW)
        pid = product.id
    await JOBS["catalog.write_product_page"](job_context(), str(pid))

    # ---- d2/d3: giá vốn về tay, đề xuất giá, chị duyệt → catalog nhận giá ---------------------------------------
    sheet = await ok(
        await c.post(
            f"{D}/supply/cost-sheets",
            json={"candidate_id": cid, "unit_price_amount": "38", "currency": "CNY", "weight_grams": 420},
        ),
        201,
    )
    assert sheet["landed_cost_vnd"] > 0
    prof = await ok(await c.get(f"{D}/assessment/candidates/{cid}"))
    assert prof["cost"]["source"] == "cost_sheet" and prof["cost"]["landed_cost_vnd"] == sheet["landed_cost_vnd"]
    prop = await ok(await c.post(f"{D}/supply/price-proposals", json={"candidate_id": cid}), 201)
    await ok(
        await c.post(
            f"{D}/control/approvals/{prop['approval_item_id']}/approve", json={"payload": {"price_vnd": 289000}}
        )
    )
    async with SessionLocal() as s:
        assert (await s.get(Product, pid)).price_vnd == 289000

    # ---- e1: chị duyệt và đăng sản phẩm → content soạn bài các kênh (f1) ----------------------------------------
    pub = await ok(await c.post(f"{D}/catalog/products/{pid}/publish"))
    assert pub["status"] == "published"
    await JOBS["content.compose_pending"](job_context())
    studio = await ok(await c.get(f"{D}/content/studio/product/{pid}"))
    drafts = {dr["channel"]: dr for dr in studio["drafts"]}
    assert {"facebook", "instagram", "tiktok", "zalo_oa"} <= set(drafts)
    fb = drafts["facebook"]
    assert fb["check_status"] in ("passed", "warnings")  # f5 soát lời
    approved = await ok(await c.post(f"{D}/content/drafts/{fb['id']}/approve", json={}))
    post_id = approved["post"]["id"]
    async with SessionLocal() as s:
        sp = await s.get(ScheduledPost, uuid.UUID(post_id))
        sp.scheduled_at = now_utc() - timedelta(minutes=1)
        await s.commit()
    assert await JOBS["content.publish_due"](job_context()) >= 1
    async with SessionLocal() as s:
        sp = await s.get(ScheduledPost, uuid.UUID(post_id))
        assert sp.status == PostStatus.PUBLISHED and sp.external_post_id
        src = src_code(sp)  # mã bài trong link ?src=
    assert get_driver("social").published

    # ---- e3: mở đợt ------------------------------------------------------------------------------------------------
    drop = await ok(
        await c.post(
            f"{D}/catalog/drops",
            json={
                "title": "Đồ giữ nhiệt mùa đông",
                "closes_at": (now_utc() + timedelta(days=3)).isoformat(),
                "expected_arrival_date": (local_today() + timedelta(days=20)).isoformat(),
                "items": [{"product_id": str(pid), "slots_total": 30, "max_per_order": 3}],
            },
        ),
        201,
    )
    opened = await ok(await c.post(f"{D}/catalog/drops/{drop['id']}/open"))
    if opened["status"] != "open":
        await approve_pending(c, "catalog.open_drop")
    async with SessionLocal() as s:
        assert (await s.get(Drop, uuid.UUID(drop["id"]))).status == DropStatus.OPEN

    # ---- e2: khách thấy món có con dấu và lý do chọn; hồ sơ chọn đầy đủ chỉ ở desk -----------------------------------
    slug = pub["slug"]
    page = await ok(await client.get(f"/api/store/catalog/products/{slug}"))
    assert page["seal"]["chosen"] == 1 and page["seal"]["total"] == len(cands) and "funnel" not in page
    dossier = await ok(await c.get(f"{D}/catalog/products/{pid}/dossier"))
    assert "Giữ nóng tới chiều." in str(dossier)

    # ---- e4/g2: giỏ → đặt → chuyển khoản → đã trả, khách nhận tin, sổ doanh thu ----------------------------------
    lines = [{"product_id": str(pid), "drop_id": drop["id"], "quantity": 2}]
    placed = await ok(
        await client.post(
            "/api/store/orders",
            json={
                "items": lines,
                "name": "Khách Ví Dụ",
                "phone": "0900000123",
                **ADDRESS,
                "payment_method": "bank_transfer",
                "src": src,
            },
        ),
        201,
    )
    await ok(await send_transfer(client, placed["payment"]["amount_due_vnd"], placed["payment"]["transfer_content"]))
    async with SessionLocal() as s:
        order = (await s.execute(select(Order).where(Order.code == placed["code"]))).scalar_one()
        assert order.paid_at is not None and order.status == OrderStatus.AWAITING_STOCK
        assert order.raw.get("src") == src  # f7: đơn gắn với bài
        oid = order.id
        di = (await s.execute(select(DropItem).where(DropItem.drop_id == uuid.UUID(drop["id"])))).scalar_one()
        assert di.slots_reserved == 2  # catalog ghi suất của đơn đã trả, một lần
        revenue = await s.scalar(
            select(func.sum(LedgerEntry.amount_vnd)).where(
                LedgerEntry.order_id == oid, LedgerEntry.kind == LedgerKind.REVENUE
            )
        )
        assert revenue == order.total_vnd
        sent = [
            n.event.value for n in (await s.execute(select(Notification).where(Notification.order_id == oid))).scalars()
        ]
        assert sent, "khách phải nhận tin xác nhận"

    # ---- h1/h2: khách nhắn hỏi, AI soạn trả lời, chị gửi ------------------------------------------------------------
    t = await ok(
        await c.post(
            f"{D}/inbox/dev/simulate",
            json={
                "text": "Bình giữ nhiệt này giữ nóng được bao lâu ạ?",
                "author_name": "Khách Hỏi",
                "author_external_id": "psid-x1",
            },
        ),
        201,
    )
    assert t["customer_id"]  # người lạ có hồ sơ khách ngay
    assert t["draft"] and t["draft"]["body"]
    assert t["draft"]["kind"] != "escalation", t["draft"]
    await ok(await c.post(f"{D}/inbox/drafts/{t['draft']['id']}/send", json={}))
    assert get_driver("social", "mock").sent

    # ---- g3: đóng đợt → đơn đặt nguồn soạn sẵn, chị duyệt ----------------------------------------------------------
    await ok(await c.post(f"{D}/catalog/drops/{drop['id']}/close"))
    async with SessionLocal() as s:
        batch = (
            await s.execute(select(PurchaseOrder).where(PurchaseOrder.drop_id == uuid.UUID(drop["id"])))
        ).scalar_one()
        assert batch.kind == POKind.BATCH and batch.lines[0].quantity == 2
    bpo = await ok(await c.get(f"{D}/supply/purchase-orders/{batch.id}"))
    await ok(await c.post(f"{D}/control/approvals/{bpo['approval_item_id']}/approve", json={}))
    bpo = await ok(await c.post(f"{D}/supply/purchase-orders/{batch.id}/status", json={"to": "sent"}))
    assert bpo["inbound"]

    # ---- d7: lô về → đơn chờ giao, đợt sang giao ------------------------------------------------------------------
    lot = bpo["inbound"][0]
    for stt in ("seller_shipped", "international_transit", "customs", "domestic_transit", "delivered"):
        await ok(await c.post(f"{D}/supply/inbound/{lot['id']}/milestones", json={"status": stt}))
    async with SessionLocal() as s:
        assert (await s.get(Order, oid)).status == OrderStatus.READY_TO_SHIP
        assert (await s.get(Drop, uuid.UUID(drop["id"]))).status == DropStatus.FULFILLING

    # ---- g4/g5: vận đơn → giao xong ----------------------------------------------------------------------------------
    res = (await ok(await c.post(f"{D}/orders/shipments", json={"order_ids": [str(oid)]})))["results"][0]
    assert res["shipment_id"], res
    get_driver("shipping", "mock").advance(6)
    await ok(await c.post(f"{D}/orders/shipments/{res['shipment_id']}/sync"))
    async with SessionLocal() as s:
        assert (await s.get(Order, oid)).status == OrderStatus.DELIVERED

    # ---- e8: mời đánh giá → khách gửi → chị duyệt hiển thị --------------------------------------------------------
    async with SessionLocal() as s:
        review = (await s.execute(select(Review).where(Review.order_id == oid))).scalar_one()
        assert review.status == ReviewStatus.REQUESTED
        token = review.token
    await ok(
        await client.post(
            f"/api/store/catalog/reviews/{token}", data={"rating": "5", "body": "Giữ nóng tốt, nắp kín, đáng tiền."}
        )
    )
    async with SessionLocal() as s:
        review = await s.get(Review, review.id)
        rid = review.id
    if review.status != ReviewStatus.PUBLISHED:
        await ok(await c.post(f"{D}/catalog/reviews/{rid}/approve"))
    page = await ok(await client.get(f"/api/store/catalog/products/{slug}"))
    assert page["review_count"] == 1

    # ---- i1/i4/i5: «Hôm nay», nhật ký AI, báo cáo tuần ----------------------------------------------------------
    today = await ok(await c.get(f"{D}/control/today"))
    stats = {s["key"]: s for s in today["stats"]}
    total = placed["total_vnd"]
    assert stats["orders.new_today"]["value"] == 1 and stats["orders.cash_today"]["value"] == total
    assert stats["finance.month_revenue"]["value"] == total and stats["catalog.on_shelf"]["value"] == 1
    assert stats["control.pending"]["value"] == today["pending"]["total"] > 0  # các bài kênh khác còn chờ chị
    acts = await ok(await c.get(f"{D}/control/activity", params={"size": 100}))
    actions = {x["action"] for x in acts["items"]}
    assert {"sourcing.interpret_brief", "catalog.publish_product"} <= actions, actions
    rep = await ok(await c.post(f"{D}/finance/reports/generate", json={}))
    assert rep["status"] == "ready" and rep["revenue_vnd"] == total and rep["order_count"] == 1
    async with SessionLocal() as s:
        cust = await s.scalar(select(func.count(Customer.id)))
        assert cust >= 2  # khách đặt + khách nhắn
        cand = await s.get(Candidate, uuid.UUID(cid))
        assert cand.stage == CandidateStage.SELECTED
