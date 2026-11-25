"""Việc «AI tự làm» của thẩm định hoàn tác được · b7 so ảnh theo hình (băm dhash) · nguyên tắc/gu giữ sau thẩm định."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.enums import SourcePlatform
from app.modules.assessment import service
from app.modules.assessment.models import Assessment, Comparison, MarketPrice
from app.modules.selection.models import PrincipleKind, SelectionPrinciple
from app.modules.sourcing.models import Candidate
from tests.sourcing.util import scanned_brief

API = "/api/desk/assessment"
CTRL = "/api/desk/control"


async def _run(client, cid: str, steps=None) -> dict:
    r = await client.post(f"{API}/candidates/{cid}/run", json={"steps": steps} if steps else {})
    assert r.status_code == 200, r.text
    return r.json()


async def _act(client, action: str) -> dict:
    items = (await client.get(f"{CTRL}/activity", params={"action": action})).json()["items"]
    assert items, action
    assert items[0]["undoable"], action
    return items[0]


async def _undo(client, act: dict) -> int:
    return (await client.post(f"{CTRL}/activity/{act['id']}/undo")).status_code


async def test_auto_actions_are_undoable(owner_client):
    _, items = await scanned_brief(owner_client)
    cid = items[0]["id"]
    await _run(owner_client, cid)
    for action in ("assessment.market_prices", "assessment.safety_check", "assessment.risk_flags",
                   "assessment.write_profile", "assessment.digest_reviews"):  # fmt: skip
        await _act(owner_client, action)


async def test_undo_market_prices(owner_client, db):
    _, items = await scanned_brief(owner_client)
    cid = uuid.UUID(items[0]["id"])
    await _run(owner_client, str(cid), ["market"])
    n = (await db.execute(select(func.count()).where(MarketPrice.candidate_id == cid))).scalar_one()
    assert n > 0
    assert await _undo(owner_client, await _act(owner_client, "assessment.market_prices")) == 200
    assert (await db.execute(select(func.count()).where(MarketPrice.candidate_id == cid))).scalar_one() == 0


async def test_undo_safety_restores_previous_and_respects_owner(owner_client, db):
    _, items = await scanned_brief(owner_client)
    cid = items[0]["id"]
    a = await _run(owner_client, cid, ["safety"])
    assert a["safety_status"] != "unchecked"
    assert await _undo(owner_client, await _act(owner_client, "assessment.safety_check")) == 200
    page = (await owner_client.get(f"{API}/candidates/{cid}")).json()["assessment"]
    assert page["safety_status"] == "unchecked" and page["safety"] == {}
    # chị xác nhận sau khi AI soát → không hoàn tác bản nháp nữa
    await _run(owner_client, cid, ["safety"])
    await owner_client.post(f"{API}/assessments/{a['id']}/confirm-safety", json={"status": "ok"})
    act = await _act(owner_client, "assessment.safety_check")
    r = await owner_client.post(f"{CTRL}/activity/{act['id']}/undo")
    assert r.status_code == 409 and "xác nhận" in r.json()["detail"]


async def test_undo_write_profile(owner_client, db):
    _, items = await scanned_brief(owner_client)
    cid = items[0]["id"]
    first = await _run(owner_client, cid)
    assert first["score_status"] == "ai_draft"
    # chị sửa một điểm, rồi chạy lại chấm: hoàn tác lần chấm sau trả về đúng bản trước (giữ điểm chị sửa)
    await owner_client.patch(f"{API}/assessments/{first['id']}/scores/chat_luong", json={"owner_score": 3})
    before = (await owner_client.get(f"{API}/candidates/{cid}")).json()["assessment"]
    acts_before = (await owner_client.get(f"{CTRL}/activity", params={"action": "assessment.write_profile"})).json()
    await _run(owner_client, cid, ["score"])
    act = await _act(owner_client, "assessment.write_profile")
    assert act["id"] != acts_before["items"][0]["id"]
    # bản cũ hơn không hoàn tác được khi đã có bản mới hơn
    r = await owner_client.post(f"{CTRL}/activity/{acts_before['items'][0]['id']}/undo")
    assert r.status_code == 409
    assert await _undo(owner_client, act) == 200
    after = (await owner_client.get(f"{API}/candidates/{cid}")).json()["assessment"]
    assert after["summary"] == before["summary"] and after["score_total"] == before["score_total"]
    assert [(s["criterion_key"], s["ai_score"], s["owner_score"]) for s in after["scores"]] == [
        (s["criterion_key"], s["ai_score"], s["owner_score"]) for s in before["scores"]
    ]
    # hoàn tác cả lần chấm đầu → hồ sơ về lúc chưa chấm
    assert await _undo(owner_client, acts_before["items"][0]) == 200
    empty = (await owner_client.get(f"{API}/candidates/{cid}")).json()["assessment"]
    assert empty["score_status"] == "none" and empty["score_total"] is None and not empty["scores"]
    assert not any(n["kind"] == "uncertain" for n in empty["risk_notes"])


async def test_undo_write_profile_refused_after_owner_confirms(owner_client):
    _, items = await scanned_brief(owner_client)
    a = await _run(owner_client, items[0]["id"])
    await owner_client.post(f"{API}/assessments/{a['id']}/confirm-score")
    act = await _act(owner_client, "assessment.write_profile")
    r = await owner_client.post(f"{CTRL}/activity/{act['id']}/undo")
    assert r.status_code == 409 and "duyệt điểm" in r.json()["detail"]


async def test_undo_risk_flags(owner_client, db):
    _, items = await scanned_brief(owner_client)
    cid = items[0]["id"]
    a = await _run(owner_client, cid, ["risk"])
    assert a["counterfeit_risk"] != "unknown"
    assert await _undo(owner_client, await _act(owner_client, "assessment.risk_flags")) == 200
    row = await db.get(Assessment, uuid.UUID(a["id"]))
    assert row.counterfeit_risk.value == "unknown" and row.fake_review_risk.value == "unknown"


async def test_undo_compare(owner_client, db):
    _, items = await scanned_brief(owner_client)
    r = await owner_client.post(f"{API}/comparisons", json={"candidate_ids": [c["id"] for c in items[:2]]})
    assert r.status_code == 201, r.text
    assert await _undo(owner_client, await _act(owner_client, "assessment.compare")) == 200
    assert (await db.execute(select(func.count()).select_from(Comparison))).scalar_one() == 0


# ---- b7: so ảnh theo hình ------------------------------------------------------------------------------------------


async def test_same_image_by_look_across_shops(owner_client, db):
    _, items = await scanned_brief(owner_client)
    c = await db.get(Candidate, uuid.UUID(items[0]["id"]))
    c.image_hash = "f0f0f0f0f0f0f0f0"
    await db.commit()
    assert not any("Ảnh chính trùng" in n["text"] for n in await service.risk_signals(db, c, None))
    # ảnh khác URL nhưng cùng hình (lệch 2 bit sau khi nén lại) ở shop khác
    db.add(Candidate(source_platform=SourcePlatform.ALIBABA_1688, source_external_id="look", title_vi="Bản khác",
                     main_image_url="https://cdn.example/khac.jpg", seller_name="Shop nhái",
                     image_hash="f0f0f0f0f0f0f0f3"))  # fmt: skip
    # ảnh khác hẳn → không tính
    db.add(Candidate(source_platform=SourcePlatform.ALIBABA_1688, source_external_id="other", title_vi="Món khác",
                     main_image_url="https://cdn.example/x.jpg", seller_name="Shop lạ", image_hash="0f0f0f0f0f0f0f0f"))  # fmt: skip
    await db.commit()
    notes = [n for n in await service.risk_signals(db, c, None) if "Ảnh chính trùng" in n["text"]]
    assert len(notes) == 1 and "1 shop khác" in notes[0]["text"] and "so theo hình" in notes[0]["text"]


async def test_same_image_by_look_in_offers(owner_client, db):
    _, items = await scanned_brief(owner_client)
    c = await db.get(Candidate, uuid.UUID(items[0]["id"]))
    c.image_hash = "aaaaaaaaaaaaaaaa"
    c.raw = {**c.raw, "offers": [
        {"external_id": c.source_external_id, "seller_name": c.seller_name, "image_hash": "aaaaaaaaaaaaaaaa"},
        {"external_id": "s2", "seller_name": "Shop B", "image_hash": "aaaaaaaaaaaaaaab"},
        {"external_id": "s3", "seller_name": "Shop C", "image_hash": "aaaaaaaaaaaaaaa8"},
        {"external_id": "s4", "seller_name": "Shop D", "image_hash": "5555555555555555"},
    ]}  # fmt: skip
    await db.commit()
    notes = [n for n in await service.risk_signals(db, c, None) if "Ảnh chính trùng" in n["text"]]
    assert notes and "2 shop khác" in notes[0]["text"]


async def test_guidance_kept_after_assessment(owner_client, db):
    db.add(SelectionPrinciple(kind=PrincipleKind.AVOID, text="Tránh giá phơi"))
    await db.commit()
    _, items = await scanned_brief(owner_client)
    cid = items[0]["id"]
    a = await _run(owner_client, cid)
    c = await db.get(Candidate, uuid.UUID(cid))
    await db.refresh(c)
    total = round(float(a["score_total"]))
    assert c.raw["guidance"]["base_score"] == total and c.ai_score == max(0, total - 10)
