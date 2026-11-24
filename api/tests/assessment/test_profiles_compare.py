"""b4 khung chấm theo nhóm hàng · b3 bảng so sánh cạnh nhau · dữ liệu mẫu."""

from __future__ import annotations

import uuid

from app.modules.catalog.models import Category
from app.modules.sourcing.models import Candidate
from tests.sourcing.util import scanned_brief

API = "/api/desk/assessment"


def crit(weights):
    return [{"key": f"tc_{i}", "label": f"Tiêu chí {i}", "weight": w} for i, w in enumerate(weights)]


async def test_scoring_profiles(owner_client, helper_client, db):
    profs = (await owner_client.get(f"{API}/scoring-profiles")).json()
    assert len(profs) == 1 and profs[0]["is_default"] and len(profs[0]["criteria"]) == 7
    default_id = profs[0]["id"]
    cat = Category(slug="nha-bep", name="Nhà bếp")
    db.add(cat)
    await db.commit()
    body = {"name": "Khung đồ bếp", "category_id": str(cat.id), "criteria": crit([40, 30, 30]), "pass_score": 75}
    assert (await helper_client.post(f"{API}/scoring-profiles", json=body)).status_code == 403
    r = await owner_client.post(f"{API}/scoring-profiles", json=body)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert (await owner_client.post(f"{API}/scoring-profiles", json=body)).status_code == 400  # trùng nhóm
    bad = {**body, "criteria": crit([40, 30, 20])}
    r = await owner_client.patch(f"{API}/scoring-profiles/{pid}", json={"criteria": bad["criteria"]})
    assert r.status_code == 400 and "100" in r.json()["detail"]
    r = await owner_client.patch(f"{API}/scoring-profiles/{default_id}", json={"criteria": crit([25, 25, 25, 25])})
    assert r.status_code == 200 and len(r.json()["criteria"]) == 4
    assert (await owner_client.delete(f"{API}/scoring-profiles/{default_id}")).status_code == 400
    assert (await owner_client.delete(f"{API}/scoring-profiles/{pid}")).status_code == 204
    r = await owner_client.post(f"{API}/scoring-profiles", json={**body, "category_id": None})
    assert r.status_code == 400


async def test_category_profile_used_for_scoring(owner_client, db):
    _b, items = await scanned_brief(owner_client)
    cat = Category(slug="sap-xep", name="Sắp xếp, lưu trữ")
    db.add(cat)
    await db.commit()
    c = await db.get(Candidate, uuid.UUID(items[0]["id"]))
    c.category_id = cat.id
    await db.commit()
    bad = [{"key": "chat_luong", "label": "Chất lượng", "weight": 60}, {"key": "nguon", "label": "Nguồn", "weight": 39}]
    bad.append({"key": "an_toan", "label": "An toàn", "weight": 0.5})
    r = await owner_client.post(
        f"{API}/scoring-profiles", json={"name": "Khung lưu trữ", "category_id": str(cat.id), "criteria": bad}
    )
    assert r.status_code == 400  # tổng phải đúng 100
    r = await owner_client.post(
        f"{API}/scoring-profiles",
        json={"name": "Khung lưu trữ", "category_id": str(cat.id), "criteria": [
            {"key": "chat_luong", "label": "Chất lượng", "weight": 50}, {"key": "nguon", "label": "Nguồn", "weight": 30},
            {"key": "van_chuyen", "label": "Vận chuyển", "weight": 20}]},
    )  # fmt: skip
    assert r.status_code == 201
    a = (await owner_client.post(f"{API}/candidates/{c.id}/run", json={})).json()
    assert [s["criterion_key"] for s in a["scores"]] == ["chat_luong", "nguon", "van_chuyen"]


async def test_comparison(owner_client):
    b, items = await scanned_brief(owner_client)
    for c in items[:2]:
        await owner_client.post(f"{API}/candidates/{c['id']}/run", json={})
    ids = [c["id"] for c in items[:3]]
    r = await owner_client.post(f"{API}/comparisons", json={"candidate_ids": ids})
    assert r.status_code == 201, r.text
    comp = r.json()
    assert comp["brief_id"] == b["id"] and comp["conclusion"]
    assert comp["recommended_candidate_id"] in ids
    assert [i["candidate_id"] for i in comp["items"]] == ids and len(comp["candidates"]) == 3
    keys = [k["key"] for k in comp["criteria"]]
    assert keys[0] == "score_total" and {"landed", "vn_price", "margin", "safety", "risk"} <= set(keys)
    assert any(i["values"]["score_total"].get("best") for i in comp["items"])
    assert (await owner_client.get(f"{API}/comparisons/{comp['id']}")).json()["id"] == comp["id"]
    lst = (await owner_client.get(f"{API}/comparisons", params={"brief_id": b["id"]})).json()
    assert lst["total"] == 1
    assert (await owner_client.post(f"{API}/comparisons", json={"candidate_ids": ids[:1]})).status_code == 422
    _, other = await scanned_brief(owner_client, "tìm bình giữ nhiệt hàng Nhật dưới 400k")
    r = await owner_client.post(f"{API}/comparisons", json={"candidate_ids": [ids[0], other[0]["id"]]})
    assert r.status_code == 400
    assert (await owner_client.get(f"{API}/comparisons/{uuid.uuid4()}")).status_code == 404
