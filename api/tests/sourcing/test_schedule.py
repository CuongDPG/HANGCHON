"""a7 săn theo lịch: chỉ tạo việc chờ chị khi có ứng viên MỚI đạt ngưỡng."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.timeutil import now_utc
from app.modules.control.models import ApprovalItem
from app.modules.sourcing import jobs, service
from app.modules.sourcing.models import SourcingBrief
from tests.sourcing.util import API, scanned_brief


async def _make_due(brief_id: str) -> None:
    async with SessionLocal() as s:
        await s.execute(
            update(SourcingBrief)
            .where(SourcingBrief.id == brief_id)
            .values(next_run_at=now_utc() - timedelta(minutes=1))
        )
        await s.commit()


async def _alerts(db) -> list[ApprovalItem]:
    return list(
        (await db.execute(select(ApprovalItem).where(ApprovalItem.action == "sourcing.scheduled_alert"))).scalars()
    )


async def test_schedule_alerts_only_on_new_above_threshold(owner_client, db):
    b, _items = await scanned_brief(owner_client)
    r = await owner_client.patch(f"{API}/briefs/{b['id']}", json={"is_scheduled": True, "alert_min_score": 50})
    sb = r.json()
    assert sb["is_scheduled"] and sb["schedule_interval_days"] == 7 and sb["next_run_at"]
    # lần chạy lại không có món mới → không làm phiền chị
    await _make_due(b["id"])
    await jobs.scheduled_scans({"db": SessionLocal})
    assert await _alerts(db) == []
    # đổi từ khoá → nguồn trả món mới → có việc chờ chị
    await owner_client.patch(
        f"{API}/briefs/{b['id']}", json={"keywords_translated": {"zh": ["阳台伸缩晾衣架"], "ja": ["伸縮物干し"]}}
    )
    await _make_due(b["id"])
    await jobs.scheduled_scans({"db": SessionLocal})
    alerts = await _alerts(db)
    assert len(alerts) == 1 and alerts[0].status == "pending"
    assert alerts[0].preview["items"] and all(i["score"] >= 50 for i in alerts[0].preview["items"])
    nb = (await owner_client.get(f"{API}/briefs/{b['id']}")).json()
    assert nb["last_run"]["kind"] == "scheduled_scan"
    assert nb["next_run_at"] > now_utc().isoformat()
    r = await owner_client.post(f"/api/desk/control/approvals/{alerts[0].id}/approve", json={})
    assert r.status_code == 200 and r.json()["result"]["href"].endswith(b["id"])


async def test_high_threshold_no_alert_and_not_due(owner_client, db):
    b, _ = await scanned_brief(owner_client)
    await owner_client.patch(f"{API}/briefs/{b['id']}", json={"is_scheduled": True, "alert_min_score": 100})
    async with SessionLocal() as s:
        assert await service.due_briefs(s) == []  # chưa tới hạn
    await owner_client.patch(f"{API}/briefs/{b['id']}", json={"keywords_translated": {"zh": ["阳台伸缩晾衣架"]}})
    await _make_due(b["id"])
    async with SessionLocal() as s:
        runs = await service.run_due_scheduled(s)
        await s.commit()
    assert runs and runs[0].new_count > 0
    assert await _alerts(db) == []
    r = await owner_client.patch(f"{API}/briefs/{b['id']}", json={"is_scheduled": False})
    assert r.json()["next_run_at"] is None
