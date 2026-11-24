"""e1 tự dựng trang sản phẩm, e2 con dấu + hồ sơ chọn, kệ hàng, e10 dữ liệu có cấu trúc."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import func, select

from app import control
from app.core import events
from app.core.jobs import job_context
from app.modules.catalog import products as svc
from app.modules.catalog.jobs import write_product_page
from app.modules.catalog.models import Product, ProductStatus
from app.modules.control.models import ApprovalItem, ApprovalStatus, AutonomyLevel
from tests.catalog.factories import category, published_product, selected_candidate


@pytest.fixture
def published_events():
    seen: list[dict] = []

    async def listener(db, payload):
        seen.append(payload)

    events.on("product.published")(listener)
    yield seen
    events._handlers["product.published"].remove(listener)


async def _draft(db, **kw):
    data = await selected_candidate(db, **kw)
    await events.emit("candidate.selected", {"candidate_id": str(data["candidate"].id),
                                             "decision_id": str(data["decision"].id)}, db=db)  # fmt: skip
    await db.commit()
    p = (await db.execute(select(Product).where(Product.candidate_id == data["candidate"].id))).scalar_one()
    return data, p


async def test_candidate_selected_creates_draft_with_dossier_snapshot(db):
    _data, p = await _draft(db, rejected=5, tried=2, brand="HãngBíMật")
    assert p.status == ProductStatus.DRAFT
    assert (p.selected_count, p.considered_count) == (1, 6)
    assert p.trial_days == 21 and p.reason_selected.startswith("Giữ nóng")
    assert p.origin_country == "JP"
    funnel = p.dossier["funnel"]
    assert funnel == {"viewed": 6, "compared": 3, "tried": 3, "selected": 1}
    # món bị loại: không lộ tên thương hiệu / shop
    assert [a["label"] for a in p.rejected_alternatives] == ["Mẫu B", "Mẫu C"]
    blob = str(p.rejected_alternatives)
    assert "HãngBíMật" not in blob and "Shop" not in blob
    assert p.rejected_alternatives[0]["stage"] == "tried"
    groups = {g["label"]: g["count"] for g in p.dossier["reject_groups"]}
    assert groups["Rò nước"] == 2 and p.dossier["screened_out"] == 3
    assert p.dossier["reviews_read"] == 412 and p.dossier["review_languages"] == ["tiếng Nhật"]
    # specs không có dòng thương hiệu
    assert all("Thương hiệu" not in s["label"] for s in p.specs)


async def test_candidate_selected_is_idempotent(db):
    data, _p = await _draft(db)
    await events.emit("candidate.selected", {"candidate_id": str(data["candidate"].id)}, db=db)
    await db.commit()
    n = (await db.execute(select(func.count()).where(Product.candidate_id == data["candidate"].id))).scalar_one()
    assert n == 1


async def test_write_page_job_proposes_for_review(db, fake_ai):
    seen = {}

    def fake(inp):
        seen["refs"] = [f.ref for f in inp.facts]
        return {
            "name": "Bình giữ nhiệt 480 ml", "subtitle": "Nhật Bản · inox 316",
            "short_description": "Giữ nóng 9 giờ, diệt khuẩn 99% tốt nhất thị trường.",
            "description": "Mình dùng 21 ngày. Giữ nóng 15 giờ.",
            "specs": [
                {"label": "Dung tích", "value": "480 ml", "ref": "spec:Dung tích"},
                {"label": "Giữ nóng", "value": "24 giờ", "ref": "spec:Giữ nóng"},  # số bịa → bỏ
                {"label": "Chống va đập", "value": "Có", "ref": "spec:Không có"},  # không có nguồn → bỏ
            ],
            "faq": [
                {"q": "Thử bao lâu?", "a": "Mình dùng thử 21 ngày.", "refs": ["decision.trial_days"]},
                {"q": "Có chữa đau dạ dày?", "a": "Có", "refs": []},  # không căn cứ → bỏ
            ],
            "seo_title": "Bình giữ nhiệt", "seo_description": "Bình giữ nhiệt inox",
        }  # fmt: skip

    fake_ai["catalog.write_product_page"] = fake
    _, p = await _draft(db)
    assert await write_product_page(job_context(), str(p.id)) == "pending"
    await db.refresh(p)
    assert p.status == ProductStatus.PENDING_REVIEW and p.ai_generated
    assert [s["label"] for s in p.specs] == ["Dung tích"]
    assert [f["q"] for f in p.faq] == ["Thử bao lâu?"]
    assert p.faq[0]["source"] == "Thời gian thử"
    assert "spec:Dung tích" in seen["refs"] and "assessment.summary" in seen["refs"]
    item = await db.get(ApprovalItem, p.approval_item_id)
    assert item.status == ApprovalStatus.PENDING and item.action == "catalog.publish_product"
    checks = item.preview["checks"]
    assert "Giữ nóng: 24 giờ" in checks["dropped_specs"] and "Có chữa đau dạ dày?" in checks["dropped_faq"]
    assert {"field": "description", "numbers": ["15"]} in checks["unsupported_numbers"]
    assert {"diet khuan", "tot nhat"} <= set(checks["overclaims"])


async def test_publish_needs_price_then_emits_event(db, owner_client, published_events):
    _, p = await _draft(db)
    await write_product_page(job_context(), str(p.id))
    r = await owner_client.post(f"/api/desk/catalog/products/{p.id}/publish")
    assert r.status_code == 400 and r.json()["code"] == "no_price"
    r = await owner_client.patch(
        f"/api/desk/catalog/products/{p.id}", json={"price_vnd": 385000, "name": "Bình 480 ml"}
    )
    assert r.status_code == 200 and r.json()["name"] == "Bình 480 ml"
    r = await owner_client.post(f"/api/desk/catalog/products/{p.id}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"
    assert published_events == [{"product_id": str(p.id)}]
    item = await db.get(ApprovalItem, r.json()["approval_item_id"])
    assert item.status == ApprovalStatus.APPROVED  # đăng = duyệt việc chờ (có nhật ký)


async def test_auto_level_publishes_immediately(db, published_events):
    await control.set_level(db, "catalog.publish_product", AutonomyLevel.AUTO, None)
    _, p = await _draft(db)
    p.price_vnd = 200000
    await db.commit()
    assert await write_product_page(job_context(), str(p.id)) == "applied"
    await db.refresh(p)
    assert p.status == ProductStatus.PUBLISHED and len(published_events) == 1


async def test_return_with_note_rewrites(db, owner_client, fake_ai):
    notes = []

    def fake(inp):
        notes.append(inp.owner_note)
        from app.modules.catalog.ai_tasks import _fake_write_page

        return _fake_write_page(inp)

    fake_ai["catalog.write_product_page"] = fake
    _, p = await _draft(db)
    await write_product_page(job_context(), str(p.id))
    await db.refresh(p)
    r = await owner_client.post(
        f"/api/desk/control/approvals/{p.approval_item_id}/return", json={"note": "Viết ngắn hơn"}
    )
    assert r.status_code == 200, r.text
    assert notes == [None, "Viết ngắn hơn"]
    pending = (
        (
            await db.execute(
                select(ApprovalItem).where(
                    ApprovalItem.action == "catalog.publish_product", ApprovalItem.status == ApprovalStatus.PENDING
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(pending) == 1


async def test_price_approved_updates_price(db):
    data, p = await _draft(db)
    await events.emit("price.approved", {"candidate_id": str(data["candidate"].id), "price_vnd": 399000}, db=db)
    await db.commit()
    await db.refresh(p)
    assert p.price_vnd == 399000


async def test_desk_permissions(db, client, helper_client):
    _, p = await _draft(db)
    assert (await client.get(f"/api/desk/catalog/products/{p.id}")).status_code == 401
    assert (await helper_client.get(f"/api/desk/catalog/products/{p.id}")).status_code == 200
    assert (await helper_client.post(f"/api/desk/catalog/products/{p.id}/publish")).status_code == 403
    rows = (await helper_client.get("/api/desk/catalog/products", params={"q": "binh giu"})).json()
    assert rows["total"] == 1


async def test_from_candidate_endpoint(db, owner_client):
    data = await selected_candidate(db)
    await db.commit()
    r = await owner_client.get("/api/desk/catalog/candidates/selectable")
    assert [c["id"] for c in r.json()] == [str(data["candidate"].id)]
    r = await owner_client.post(
        "/api/desk/catalog/products/from-candidate", json={"candidate_id": str(data["candidate"].id)}
    )
    assert r.status_code == 201 and r.json()["status"] == "pending_review"
    assert (await owner_client.get("/api/desk/catalog/candidates/selectable")).json() == []
    rejected = data["rejected"][0]
    r = await owner_client.post("/api/desk/catalog/products/from-candidate", json={"candidate_id": str(rejected.id)})
    assert r.status_code == 400


async def test_public_product_and_dossier(db, client):
    _draft_data, draft = await _draft(db, title="Hộp cơm inox")
    p = await published_product(db, brand="HãngBíMật")
    await db.commit()
    assert (await client.get(f"/api/store/catalog/products/{draft.slug}")).status_code == 404
    r = await client.get(f"/api/store/catalog/products/{p.slug}")
    assert r.status_code == 200
    body = r.json()
    assert body["seal"] == {"chosen": 1, "total": 6}
    assert body["reason_selected"] == ["Giữ nóng 9 tiếng", "Nắp tháo rời"]
    assert body["not_satisfied"] == "Miệng hẹp." and body["proof"] == "Thử 3 tuần · Nhật"
    assert body["funnel"]["tried"] == 3 and body["available"] is False
    d = (await client.get(f"/api/store/catalog/products/{p.slug}/dossier")).json()
    assert d["product"]["seal"]["total"] == 6 and len(d["alternatives"]) == 2
    assert "HãngBíMật" not in str(d)
    assert d["reviews_read"] == 412


async def test_shelf_search_and_filter(db, client):
    bep = await category(db)
    await published_product(db, name="Bình giữ nhiệt 480 ml", category=bep)
    await published_product(db, name="Khăn tắm cho bé")
    await db.commit()
    shelf = (await client.get("/api/store/catalog/shelf")).json()
    assert shelf["total"] == 2 and shelf["chips"] == [{"slug": "nha-bep", "name": "Nhà bếp", "count": 1}]
    hit = (await client.get("/api/store/catalog/shelf", params={"q": "binh giu nhiet"})).json()
    assert [i["name"] for i in hit["items"]] == ["Bình giữ nhiệt 480 ml"]
    hit = (await client.get("/api/store/catalog/shelf", params={"q": "KHĂN tắm"})).json()
    assert [i["name"] for i in hit["items"]] == ["Khăn tắm cho bé"]
    assert (await client.get("/api/store/catalog/shelf", params={"q": "máy xay"})).json()["items"] == []
    by_cat = (await client.get("/api/store/catalog/shelf", params={"nhom": "nha-bep"})).json()
    assert len(by_cat["items"]) == 1


async def test_feed_sitemap_about(db, client):
    p = await published_product(db)
    await db.commit()
    r = await client.get("/api/store/catalog/feed.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(r.text)
    ns = {"g": "http://base.google.com/ns/1.0"}
    item = root.find("channel/item")
    assert item.find("g:title", ns).text == p.name
    assert item.find("g:price", ns).text == "385000 VND"
    assert item.find("g:availability", ns).text == "out_of_stock"
    sm = (await client.get("/api/store/catalog/sitemap")).json()
    assert {"path": f"/san-pham/{p.slug}"}.items() <= sm[0].items()
    about = (await client.get("/api/store/catalog/about")).json()
    assert about["stats"]["viewed"] == 6 and about["stats"]["chosen"] == 1
    assert about["picker_name"] == "Người chọn hàng"


async def test_store_settings_override_about(db, client, owner):
    await control.set_setting(db, "store.picker_name", "Chị Ví Dụ", owner)
    await db.commit()
    about = (await client.get("/api/store/catalog/about")).json()
    assert about["picker_name"] == "Chị Ví Dụ"


async def test_unpublish(db, owner_client):
    p = await published_product(db)
    await db.commit()
    r = await owner_client.post(f"/api/desk/catalog/products/{p.id}/unpublish")
    assert r.json()["status"] == "paused"
    assert svc  # dùng module để giữ import cho kiểu
