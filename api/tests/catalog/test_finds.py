"""e9 Nhờ chị tìm: gửi (chống spam), duyệt hiện, «mình cũng cần» một lượt mỗi thiết bị, ngưỡng, trạng thái công khai."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app import control
from app.core import events
from app.core.enums import SourcePlatform
from app.main import app as fastapi_app
from app.modules.catalog.models import FindRequest, FindRequestStatus
from app.modules.control.models import ApprovalItem, ApprovalStatus
from app.modules.sourcing.models import BriefStatus, Candidate, CandidateStage, SourcingBrief
from tests.catalog.factories import published_product


@pytest.fixture
def find_events():
    seen: list[tuple[str, dict]] = []

    async def created(db, payload):
        seen.append(("created", payload))

    async def threshold(db, payload):
        seen.append(("threshold", payload))

    events.on("find_request.created")(created)
    events.on("find_request.threshold")(threshold)
    yield seen
    events._handlers["find_request.created"].remove(created)
    events._handlers["find_request.threshold"].remove(threshold)


def device() -> httpx.AsyncClient:
    """Mỗi client là một «thiết bị» riêng (cookie riêng)."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test")


async def test_create_moderate_publish_vote_threshold(db, owner, owner_client, find_events):
    await control.set_setting(db, "catalog.find_request_threshold", 3, owner)
    await db.commit()
    async with device() as a, device() as b, device() as c:
        r = await a.post("/api/store/catalog/finds", json={"title": "Bình sữa thuỷ tinh cho bé 6 tháng, núm mềm",
                                                           "contact": "Zalo của mình"})  # fmt: skip
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["visible"] is False and body["request"]["vote_count"] == 1
        assert body["request"]["vote_threshold"] == 3
        assert "hc_dev" in r.cookies
        assert find_events[0][0] == "created"
        # chưa duyệt → chưa hiện công khai
        assert (await b.get("/api/store/catalog/finds")).json()["items"] == []
        fr = (await db.execute(select(FindRequest))).scalar_one()
        item = (await db.execute(select(ApprovalItem).where(ApprovalItem.ref_id == fr.id))).scalar_one()
        assert item.action == "catalog.publish_find_request" and item.preview["recommend"] == "publish"
        r = await owner_client.post(f"/api/desk/catalog/finds/{fr.id}/approve")
        assert r.status_code == 200 and r.json()["status"] == "open"
        listing = (await b.get("/api/store/catalog/finds")).json()
        assert listing["threshold"] == 3 and listing["items"][0]["status"]["label"] == "Mới"
        assert listing["items"][0]["voted"] is False
        slug = listing["items"][0]["slug"]
        r = await b.post(f"/api/store/catalog/finds/{slug}/vote")
        assert r.json()["added"] is True and r.json()["request"]["vote_count"] == 2
        r = await b.post(f"/api/store/catalog/finds/{slug}/vote")  # bấm lại cùng thiết bị
        assert r.json()["added"] is False and r.json()["request"]["vote_count"] == 2
        assert (await b.get("/api/store/catalog/finds")).json()["items"][0]["voted"] is True
        r = await c.post(f"/api/store/catalog/finds/{slug}/vote")
        assert r.json()["request"]["vote_count"] == 3
        assert r.json()["request"]["status"]["key"] == "threshold"
    assert [e[0] for e in find_events] == ["created", "threshold"]


async def test_anti_spam(db, client):
    r = await client.post("/api/store/catalog/finds", json={"title": "Bình nước", "website": "http://bot"})
    assert r.status_code == 400 and r.json()["code"] == "spam"
    r = await client.post("/api/store/catalog/finds", json={"title": "abc"})
    assert r.status_code == 400
    r = await client.post("/api/store/catalog/finds", json={"title": "Mua ngay http://a.com http://b.com giảm giá"})
    assert r.status_code == 400
    async with device() as d:
        for i in range(3):
            assert (
                await d.post("/api/store/catalog/finds", json={"title": f"Món cần tìm số {i} cho nhà"})
            ).status_code == 201
        r = await d.post("/api/store/catalog/finds", json={"title": "Món cần tìm số 9 cho nhà"})
        assert r.status_code == 429


async def test_spam_text_recommended_hidden_and_return_rejects(db, client, owner_client):
    r = await client.post("/api/store/catalog/finds", json={"title": "Kiếm tiền online inbox ngay zalo.me/abc"})
    assert r.status_code == 201
    fr = (await db.execute(select(FindRequest))).scalar_one()
    item = (await db.execute(select(ApprovalItem).where(ApprovalItem.ref_id == fr.id))).scalar_one()
    assert item.preview["recommend"] == "hide"
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/return", json={"note": "Quảng cáo"})
    assert r.status_code == 200
    await db.refresh(fr)
    assert fr.status == FindRequestStatus.REJECTED and fr.moderation_note == "Quảng cáo"


async def test_duplicate_title_adds_vote(db, client, owner_client):
    async with device() as a, device() as b:
        await a.post("/api/store/catalog/finds", json={"title": "Thớt gỗ không mốc cho nhà ẩm"})
        fr = (await db.execute(select(FindRequest))).scalar_one()
        await owner_client.post(f"/api/desk/catalog/finds/{fr.id}/approve")
        r = await b.post("/api/store/catalog/finds", json={"title": "thớt gỗ  KHÔNG mốc cho nhà ẩm"})
        assert r.json()["duplicate"] is True and r.json()["request"]["vote_count"] == 2


async def test_public_status_labels_and_found(db, owner_client, client):
    brief = SourcingBrief(title="Nhờ tìm: giá phơi", raw_text="giá phơi", status=BriefStatus.ACTIVE)
    db.add(brief)
    await db.flush()
    fr = FindRequest(public_slug="gia-phoi-1", title="Giá phơi gấp gọn", status=FindRequestStatus.SEARCHING,
                     brief_id=brief.id, vote_count=31)  # fmt: skip
    db.add(fr)
    await db.commit()
    items = (await client.get("/api/store/catalog/finds")).json()["items"]
    assert items[0]["status"] == {"key": "searching", "label": "AI đang tìm ứng viên"}
    for i in range(3):
        db.add(Candidate(brief_id=brief.id, stage=CandidateStage.TRIAL, source_platform=SourcePlatform.TAOBAO,
                         source_external_id=f"t{i}", title_vi=f"Mẫu {i}"))  # fmt: skip
    await db.commit()
    items = (await client.get("/api/store/catalog/finds")).json()["items"]
    assert items[0]["status"]["label"] == "Mình đang thử 3 mẫu"
    r = await owner_client.post(f"/api/desk/catalog/finds/{fr.id}/status", json={"status": "found"})
    assert r.status_code == 400
    p = await published_product(db)
    await db.commit()
    r = await owner_client.post(
        f"/api/desk/catalog/finds/{fr.id}/status", json={"status": "found", "product_id": str(p.id)}
    )
    assert r.json()["public_status"]["label"] == "Đã có trên kệ"
    items = (await client.get("/api/store/catalog/finds")).json()["items"]
    assert items[0]["product_slug"] == p.slug
    r = await owner_client.post(f"/api/desk/catalog/finds/{fr.id}/status", json={"status": "closed"})
    assert r.json()["public_status"]["label"] == "Chưa có món ưng"
    vote = await client.post("/api/store/catalog/finds/gia-phoi-1/vote")
    assert vote.status_code == 409
    assert (await owner_client.get("/api/desk/catalog/finds")).json()["total"] == 1
    _ = ApprovalStatus
