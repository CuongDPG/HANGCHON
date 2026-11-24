"""a1 ra đề bằng lời · a4 quét nhiều nguồn: endpoint, phân quyền, mức tự chủ auto/ask/off, hoàn tác, lỗi AI."""

from __future__ import annotations

import pytest

from app import ai
from app.core import events
from tests.sourcing.util import API, BRIEF, new_brief, scanned_brief, set_level


@pytest.fixture
def seen_events():
    got: list[dict] = []

    @events.on("brief.created")
    async def _grab(db, payload):
        got.append(payload)

    yield got
    events._handlers["brief.created"].remove(_grab)


async def test_create_brief_parses_criteria(owner_client, seen_events):
    b = await new_brief(owner_client)
    assert b["status"] == "draft"
    assert b["title"] == "Giá phơi gấp gọn"
    assert b["interpretation"].startswith("Em hiểu là chị cần giá phơi gấp gọn")
    f = b["filters"]
    assert f["materials"] == ["inox"] and f["min_rating"] == 4.7 and set(f["origins"]) == {"jp", "cn"}
    assert b["target_landed_cost_max_vnd"] == 300_000
    assert any("晾衣架" in k for k in b["keywords_translated"]["zh"])
    assert b["keywords_translated"]["ja"]
    assert set(b["platforms"]) == {"1688", "taobao", "rakuten", "amazon_jp"}
    assert b["ai_run_id"]
    assert seen_events and seen_events[0]["brief_id"] == b["id"]
    # việc AI làm được ghi nhật ký
    r = await owner_client.get("/api/desk/control/activity", params={"action": "sourcing.interpret_brief"})
    assert r.json()["total"] == 1


async def test_requires_login(client):
    r = await client.post(f"{API}/briefs", json={"text": BRIEF})
    assert r.status_code == 401


async def test_helper_can_create_and_validation(helper_client):
    r = await helper_client.post(f"{API}/briefs", json={"text": "ab"})
    assert r.status_code == 422
    r = await helper_client.post(f"{API}/briefs", json={"text": "tìm hộp cơm inox", "input_mode": "voice"})
    assert r.status_code == 201
    assert r.json()["input_mode"] == "voice"


async def test_patch_chips_and_rules(owner_client):
    b = await new_brief(owner_client)
    r = await owner_client.patch(
        f"{API}/briefs/{b['id']}",
        json={
            "filters": {"materials": ["inox 304"], "origins": ["jp"], "min_rating": 4.5},
            "target_landed_cost_max_vnd": 250_000,
            "keywords_translated": {"zh": ["不锈钢晾衣架"]},
        },
    )
    assert r.status_code == 200, r.text
    nb = r.json()
    assert nb["filters"]["materials"] == ["inox 304"] and nb["filters"]["product_type"] == "giá phơi gấp gọn"
    assert nb["platforms"] == ["rakuten", "amazon_jp"]
    assert nb["target_landed_cost_max_vnd"] == 250_000
    assert nb["keywords_translated"]["zh"] == ["不锈钢晾衣架"] and nb["keywords_translated"]["ja"]
    r = await owner_client.patch(f"{API}/briefs/{b['id']}", json={"keywords_translated": {"xx": ["a"]}})
    assert r.status_code == 422
    r = await owner_client.patch(f"{API}/briefs/{b['id']}", json={"is_scheduled": True})
    assert r.status_code == 400  # chưa xác nhận đề
    r = await owner_client.patch(f"{API}/briefs/{b['id']}", json={"clear_landed_cost": True})
    assert r.json()["target_landed_cost_max_vnd"] is None
    r = await owner_client.get(f"{API}/briefs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


async def test_reinterpret(owner_client):
    b = await new_brief(owner_client)
    r = await owner_client.post(
        f"{API}/briefs/{b['id']}/reinterpret", json={"text": "tìm bình giữ nhiệt hàng Nhật dưới 400k"}
    )
    assert r.status_code == 200
    assert r.json()["title"].lower().startswith("bình giữ nhiệt")
    assert r.json()["target_landed_cost_max_vnd"] == 400_000


async def test_scan_finds_ranked_candidates(owner_client):
    b, items = await scanned_brief(owner_client)
    assert 6 <= len(items) <= 9
    scores = [c["ai_score"] for c in items]
    assert scores == sorted(scores, reverse=True) and len(set(scores)) > 3
    for c in items:
        assert c["rank_reason"].startswith("Đáng xem vì")
        assert c["title_vi"].startswith("Giá phơi")
        assert c["landed_estimate_vnd"] <= 300_000
        assert c["stage"] == "candidate" and c["origin"] == "brief_scan"
    assert len({c["title_vi"] for c in items}) == len(items)  # đã gom cùng mẫu
    r = await owner_client.get(f"{API}/briefs/{b['id']}")
    card = r.json()
    assert card["status"] == "active" and card["candidate_count"] == len(items)
    run = card["last_run"]
    assert run["found_count"] >= len(items) and run["above_threshold_count"] == len(items)
    assert run["progress"]["done"] == run["progress"]["total"] == 4
    r = await owner_client.get(f"{API}/runs/{run['id']}")
    assert r.json()["new_count"] == len(items)
    r = await owner_client.get(f"{API}/candidates/{items[0]['id']}")
    assert r.status_code == 200 and r.json()["offers"]


async def test_rescan_dedupes(owner_client):
    b, items = await scanned_brief(owner_client)
    r = await owner_client.post(f"{API}/briefs/{b['id']}/run")
    assert r.json()["new_count"] == 0
    r = await owner_client.get(f"{API}/briefs/{b['id']}/candidates")
    assert r.json()["total"] == len(items)


async def test_scan_ask_level_waits_for_owner(owner_client):
    await set_level(owner_client, "sourcing.save_candidates", "ask")
    b = await new_brief(owner_client)
    run = (await owner_client.post(f"{API}/briefs/{b['id']}/run")).json()
    assert run["progress"]["step"] == "pending"
    item_id = run["progress"]["approval_item_id"]
    assert (await owner_client.get(f"{API}/briefs/{b['id']}/candidates")).json()["total"] == 0
    r = await owner_client.post(f"/api/desk/control/approvals/{item_id}/approve", json={})
    assert r.status_code == 200, r.text
    assert (await owner_client.get(f"{API}/briefs/{b['id']}/candidates")).json()["total"] >= 6


async def test_scan_off_level_is_blocked(owner_client):
    await set_level(owner_client, "sourcing.save_candidates", "off")
    b = await new_brief(owner_client)
    run = (await owner_client.post(f"{API}/briefs/{b['id']}/run")).json()
    assert run["status"] == "cancelled" and run["progress"]["step"] == "blocked"


async def test_undo_saved_candidates(owner_client):
    b, _items = await scanned_brief(owner_client)
    acts = (await owner_client.get("/api/desk/control/activity", params={"action": "sourcing.save_candidates"})).json()
    act = acts["items"][0]
    assert act["undoable"]
    r = await owner_client.post(f"/api/desk/control/activity/{act['id']}/undo")
    assert r.status_code == 200, r.text
    assert (await owner_client.get(f"{API}/briefs/{b['id']}/candidates")).json()["total"] == 0


async def test_scan_ai_failure_marks_run_failed(owner_client, fake_ai):
    b = await new_brief(owner_client)

    def refuse(inp):
        raise ai.FakeRefusal("policy")

    fake_ai["sourcing.rank_candidates"] = refuse
    run = (await owner_client.post(f"{API}/briefs/{b['id']}/run")).json()
    assert run["status"] == "failed" and run["error"]


async def test_closed_brief_cannot_run(owner_client):
    b, _ = await scanned_brief(owner_client)
    r = await owner_client.patch(f"{API}/briefs/{b['id']}", json={"status": "archived"})
    assert r.json()["status"] == "archived"
    r = await owner_client.post(f"{API}/briefs/{b['id']}/run")
    assert r.status_code == 400
    r = await owner_client.get(f"{API}/briefs")
    assert r.json()["total"] == 0  # đề đã lưu trữ không hiện mặc định


async def test_voice_intent_creates_brief(db, owner):
    from app import control

    spec = control.INTENTS["sourcing.new_brief"]
    params = spec.params(text="tìm giúp chị giá phơi gấp gọn inox dưới 300k")
    res = await spec.fn(control.CommandContext(db=db, user=owner, text=params.text), params)
    assert res.href.startswith("/desk/san-hang/de/") and "Giá phơi gấp gọn" in res.message
