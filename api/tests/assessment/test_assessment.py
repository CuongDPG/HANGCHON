"""b1 hồ sơ · b2 đọc hộ đánh giá · b4 chấm điểm + chị sửa · b5 giá VN · b6 an toàn · b7 nhái/ảo · giá vốn."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from app.core import events
from app.core.enums import SourcePlatform
from app.integrations import IntegrationError, get_driver
from app.modules.assessment import service
from app.modules.sourcing.models import Candidate
from app.modules.supply.models import CostSheet
from tests.sourcing.util import scanned_brief, set_level

API = "/api/desk/assessment"


async def _assess(client, cid: str, steps=None) -> dict:
    r = await client.post(f"{API}/candidates/{cid}/run", json={"steps": steps} if steps else {})
    assert r.status_code == 200, r.text
    return r.json()


async def test_full_profile(owner_client, db):
    got: list[dict] = []

    @events.on("candidate.assessed")
    async def _grab(db_, payload):
        got.append(payload)

    try:
        _, items = await scanned_brief(owner_client)
        cid = items[0]["id"]
        a = await _assess(owner_client, cid)
        assert a["status"] == "ready" and a["error"] is None and a["score_status"] == "ai_draft"
        page = (await owner_client.get(f"{API}/candidates/{cid}")).json()
    finally:
        events._handlers["candidate.assessed"].remove(_grab)
    a = page["assessment"]
    # b4: bảy tiêu chí theo bản thiết kế, có căn cứ, tổng theo trọng số
    assert [s["criterion_label"] for s in a["scores"]] == [
        "Chất lượng", "An toàn", "Biên lợi nhuận", "Khác biệt", "Hàng nhái", "Nguồn", "Vận chuyển"
    ]  # fmt: skip
    assert [float(s["weight"]) for s in a["scores"]] == [25, 20, 15, 15, 10, 10, 5]
    assert all(s["ai_reason"] for s in a["scores"])
    assert abs(sum(s["points"] for s in a["scores"]) - float(a["score_total"])) < 0.05
    assert a["summary"] and a["strengths"]
    # b2
    d = page["review_digest"]
    assert d["reviews_read"] >= 20 and sum(d["rating_histogram"].values()) == d["reviews_read"]
    assert d["praise"] and d["praise"][0]["count"] >= 1 and d["praise"][0]["quotes"][0]["vi"]
    assert d["low_star_summary"]
    assert all(r["vi"] for r in d["low_star_reviews"])
    # b5 + giá vốn ước tính sơ bộ (chưa có cost_sheets)
    m = page["market"]
    assert m["low_vnd"] <= m["median_vnd"] <= m["high_vnd"] and m["listings"]
    assert m["suggested_price_vnd"] < m["low_vnd"] and m["margin_pct"] is not None
    cost = page["cost"]
    assert cost["source"] == "estimate" and "Ước tính sơ bộ" in cost["note"]
    assert (
        sum(line["amount_vnd"] for line in cost["lines"]) == cost["landed_cost_vnd"]
        or cost["landed_cost_vnd"] % 1000 == 0
    )
    # b6 + b7
    assert a["safety_status"] in ("ok", "warning", "blocked") and a["safety"]["findings"]
    assert a["counterfeit_risk"] != "unknown" and a["fake_review_risk"] != "unknown"
    assert any(w["kind"] == "uncertain" for w in page["warnings"])
    assert page["brief"]["considered_count"] == len(items)
    assert page["scoring_profile"]["is_default"]
    # sự kiện + sourcing cập nhật điểm xếp hạng
    assert got == [{"candidate_id": cid, "assessment_id": a["id"]}]
    c = await db.get(Candidate, uuid.UUID(cid))
    assert c.ai_score == round(float(a["score_total"]))
    # nhật ký AI có đủ các bước
    acts = (await owner_client.get("/api/desk/control/activity", params={"module": "assessment"})).json()
    assert {x["action"] for x in acts["items"]} >= {
        "assessment.digest_reviews", "assessment.market_prices", "assessment.safety_check",
        "assessment.risk_flags", "assessment.write_profile",
    }  # fmt: skip


async def test_owner_edits_and_confirms_score(owner_client, helper_client):
    _, items = await scanned_brief(owner_client)
    cid = items[1]["id"]
    a = await _assess(owner_client, cid)
    before = float(a["score_total"])
    r = await helper_client.patch(f"{API}/assessments/{a['id']}/scores/chat_luong", json={"owner_score": 2})
    assert r.status_code == 403
    r = await owner_client.patch(
        f"{API}/assessments/{a['id']}/scores/chat_luong", json={"owner_score": 2, "owner_note": "Mẫu thử bị lỏng ốc"}
    )
    assert r.status_code == 200, r.text
    row = next(s for s in r.json()["scores"] if s["criterion_key"] == "chat_luong")
    assert float(row["owner_score"]) == 2 and float(row["points"]) == 5.0 and row["owner_note"]
    assert float(r.json()["score_total"]) < before
    r = await owner_client.patch(f"{API}/assessments/{a['id']}/scores/khong_co", json={"owner_score": 5})
    assert r.status_code == 404
    r = await owner_client.patch(f"{API}/assessments/{a['id']}/scores/chat_luong", json={"owner_score": 11})
    assert r.status_code == 422
    r = await owner_client.post(f"{API}/assessments/{a['id']}/confirm-score")
    assert r.json()["score_status"] == "confirmed" and r.json()["score_confirmed_by_id"]
    # chạy lại thẩm định giữ điểm chị đã sửa
    a2 = await _assess(owner_client, cid)
    row = next(s for s in a2["scores"] if s["criterion_key"] == "chat_luong")
    assert float(row["owner_score"]) == 2 and a2["version"] == 2 and a2["score_status"] == "ai_draft"


async def test_confirm_safety(owner_client, helper_client):
    _, items = await scanned_brief(owner_client)
    a = await _assess(owner_client, items[0]["id"], ["safety"])
    assert a["safety_status"] != "unchecked"
    assert (await helper_client.post(f"{API}/assessments/{a['id']}/confirm-safety", json={})).status_code == 403
    r = await owner_client.post(
        f"{API}/assessments/{a['id']}/confirm-safety", json={"status": "warning", "note": "Cần xin giấy kiểm nghiệm"}
    )
    assert r.json()["safety_status"] == "warning" and r.json()["safety_confirmed_at"]
    assert r.json()["safety"]["owner_note"] == "Cần xin giấy kiểm nghiệm"


async def test_cost_sheet_from_supply_wins(owner_client, db):
    _, items = await scanned_brief(owner_client)
    cid = uuid.UUID(items[0]["id"])
    db.add(CostSheet(candidate_id=cid, unit_price_amount=Decimal("31"), currency="CNY", fx_rate=Decimal("3650"),
                     unit_price_vnd=113_000, agent_fee_vnd=14_000, intl_shipping_vnd=29_000, tax_vnd=16_000,
                     landed_cost_vnd=172_000))  # fmt: skip
    await db.commit()
    page = (await owner_client.get(f"{API}/candidates/{cid}")).json()
    assert page["cost"]["source"] == "cost_sheet" and page["cost"]["landed_cost_vnd"] == 172_000


async def test_step_failure_does_not_block_others(owner_client, monkeypatch):
    _, items = await scanned_brief(owner_client)

    async def down(query, *, limit=10):
        raise IntegrationError("Sàn đang chặn truy cập.")

    monkeypatch.setattr(get_driver("sources"), "market_prices", down)
    a = await _assess(owner_client, items[0]["id"])
    assert a["status"] == "ready" and "giá ở Việt Nam" in a["error"]
    page = (await owner_client.get(f"{API}/candidates/{items[0]['id']}")).json()
    assert page["market"] is None and page["review_digest"] and page["assessment"]["scores"]


async def test_market_only_rerun(owner_client):
    _, items = await scanned_brief(owner_client)
    cid = items[0]["id"]
    a = await _assess(owner_client, cid, ["market"])
    assert a["status"] == "ready" and a["version"] == 1 and not a["scores"]
    page = (await owner_client.get(f"{API}/candidates/{cid}")).json()
    assert page["market"]["count"] >= 1 and page["assessment"]["summary"] is None


async def test_write_profile_ask_level(owner_client):
    await set_level(owner_client, "assessment.write_profile", "ask")
    _, items = await scanned_brief(owner_client)
    a = await _assess(owner_client, items[0]["id"])
    assert not a["scores"]
    pend = (await owner_client.get("/api/desk/control/approvals", params={"action": "assessment.write_profile"})).json()
    assert pend["total"] == 1
    r = await owner_client.post(f"/api/desk/control/approvals/{pend['items'][0]['id']}/approve", json={})
    assert r.status_code == 200, r.text
    page = (await owner_client.get(f"{API}/candidates/{items[0]['id']}")).json()
    assert len(page["assessment"]["scores"]) == 7


async def test_risk_signals(db, owner_client):
    _, items = await scanned_brief(owner_client)
    c = await db.get(Candidate, uuid.UUID(items[0]["id"]))
    c.raw = {
        **c.raw,
        "offers": [
            {"platform": "taobao", "external_id": c.source_external_id, "price_vnd_estimate": 40_000},
            {"platform": "1688", "external_id": "x1", "price_vnd_estimate": 120_000},
            {"platform": "taobao", "external_id": "x2", "price_vnd_estimate": 130_000},
        ],
    }
    c.review_count, c.sales_count = 900, 100
    await db.commit()
    notes = await service.risk_signals(db, c, None)
    kinds = {(n["kind"], n["level"]) for n in notes}
    assert ("counterfeit", "warning") in kinds and ("fake_review", "danger") in kinds
    cf, fr = service.risk_levels(notes)
    assert cf.value == "medium" and fr.value == "high"
    dup = Candidate(source_platform=SourcePlatform.ALIBABA_1688, source_external_id="dup", title_vi="Bản sao",
                    main_image_url=c.main_image_url, seller_name="Shop khác")  # fmt: skip
    db.add(dup)
    await db.commit()
    notes = await service.risk_signals(db, c, None)
    assert any("Ảnh chính trùng" in n["text"] for n in notes)


async def test_profile_404_and_login(client, owner_client):
    assert (await client.get(f"{API}/candidates/{uuid.uuid4()}")).status_code == 401
    assert (await owner_client.get(f"{API}/candidates/{uuid.uuid4()}")).status_code == 404


async def test_legacy_profile_upgraded(db):
    from app.modules.assessment.models import ScoringProfile

    legacy = [{"key": k, "label": k, "weight": w} for k, w in
              [("cong_nang", 20), ("do_ben", 20), ("an_toan", 15), ("de_dung", 15), ("tham_my", 10), ("gia_tri", 15), ("van_chuyen", 5)]]  # fmt: skip
    db.add(ScoringProfile(name="Khung mặc định", is_default=True, criteria=legacy, pass_score=65))
    await db.commit()
    prof = await service.ensure_seeded_profile(db)
    assert [c["weight"] for c in prof.criteria] == [25, 20, 15, 15, 10, 10, 5]
    await db.commit()
    rows = (await db.execute(select(ScoringProfile))).scalars().all()
    assert len(rows) == 1
