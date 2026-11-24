from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import control
from app.core.db import SessionLocal
from app.modules.control.models import (
    AIActivity,
    AIRun,
    ApprovalItem,
    ApprovalStatus,
    AppSetting,
    AuditLog,
    AutonomyLevel,
    User,
)

pytestmark = pytest.mark.usefixtures("temp_registry")


@pytest.fixture
def calls() -> dict[str, list[Any]]:
    """Đăng ký bộ hành động thử: test.internal (auto), test.post (ask, khách thấy), test.refund (khoá)."""
    log: dict[str, list[Any]] = {"run": [], "undo": [], "returned": []}
    control.register_action("test.internal", "Việc nội bộ", "Thử", default="auto")
    control.register_action("test.post", "Đăng bài thử", "Thử", default="ask", customer_facing=True)
    control.register_action("test.refund", "Hoàn tiền thử", "Thử", locked=True)
    control.register_action("test.broken", "Việc lỗi", "Thử", default="auto")

    for key in ("test.internal", "test.post", "test.refund"):

        @control.handler(key)
        async def _run(ctx: control.ActionContext, key: str = key) -> control.HandlerResult:
            log["run"].append((key, ctx.mode, dict(ctx.payload), ctx.user.email if ctx.user else None))
            ctx.db.add(AppSetting(key=f"test.{len(log['run'])}", value=ctx.payload))
            return control.HandlerResult(result={"ok": True}, undo={"key": f"test.{len(log['run'])}"})

    @control.undoer("test.internal")
    async def _undo(ctx: control.UndoContext) -> None:
        log["undo"].append(ctx.undo)
        row = await ctx.db.get(AppSetting, ctx.undo["key"])
        await ctx.db.delete(row)

    @control.on_returned("test.post")
    async def _ret(ctx: control.ReturnContext) -> None:
        log["returned"].append(ctx.note)

    @control.handler("test.broken")
    async def _broken(ctx: control.ActionContext) -> None:
        ctx.db.add(AppSetting(key="should.rollback", value=1))
        raise RuntimeError("hỏng")

    return log


async def _propose(action: str, **kw: Any) -> control.ProposeOutcome:
    async with SessionLocal() as db:
        out = await control.propose(action, kw.pop("title", f"Thử {action}"), kw.pop("payload", {"a": 1}), db=db, **kw)
        await db.commit()
        return out


async def test_propose_auto_applies_logs_and_undoes(calls: dict, owner_client: httpx.AsyncClient) -> None:
    out = await _propose("test.internal", rationale="vì thử", sources=[{"url": "https://x"}])
    assert out.status == "applied" and out.level == AutonomyLevel.AUTO and out.result == {"ok": True}
    assert calls["run"] == [("test.internal", "auto", {"a": 1}, None)]
    r = await owner_client.get("/api/desk/control/activity")
    item = r.json()["items"][0]
    assert item["mode"] == "auto" and item["undoable"] and item["rationale"] == "vì thử"
    r = await owner_client.post(f"/api/desk/control/activity/{item['id']}/undo")
    assert r.status_code == 200 and r.json()["undone_at"]
    assert calls["undo"] == [{"key": "test.1"}]
    async with SessionLocal() as s:
        assert await s.get(AppSetting, "test.1") is None
    again = await owner_client.post(f"/api/desk/control/activity/{item['id']}/undo")
    assert again.status_code == 409 and again.json()["code"] == "already_undone"


async def test_propose_ask_then_approve(calls: dict, owner_client: httpx.AsyncClient, owner: User) -> None:
    out = await _propose("test.post", preview={"text": "Bài mới"}, payload={"text": "Bài mới", "channel": "facebook"})
    assert out.status == "pending" and out.item_id and calls["run"] == []
    r = await owner_client.get("/api/desk/control/approvals")
    assert r.json()["total"] == 1 and r.json()["items"][0]["preview"] == {"text": "Bài mới"}
    r = await owner_client.post(f"/api/desk/control/approvals/{out.item_id}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["was_edited"] is False
    assert calls["run"] == [("test.post", "approved", {"text": "Bài mới", "channel": "facebook"}, owner.email)]
    async with SessionLocal() as s:
        act = (await s.execute(select(AIActivity))).scalar_one()
        audit = (await s.execute(select(AuditLog).where(AuditLog.action == "control.approved"))).scalar_one()
    assert act.mode == "approved" and act.approval_item_id == out.item_id
    assert audit.actor_user_id == owner.id
    again = await owner_client.post(f"/api/desk/control/approvals/{out.item_id}/approve", json={})
    assert again.status_code == 409


async def test_edit_then_approve_merges_payload(calls: dict, owner_client: httpx.AsyncClient) -> None:
    out = await _propose("test.post", payload={"text": "Bản AI", "channel": "facebook"})
    r = await owner_client.post(
        f"/api/desk/control/approvals/{out.item_id}/approve", json={"payload": {"text": "Bản chị sửa"}, "note": "ok"}
    )
    body = r.json()
    assert body["was_edited"] is True and body["edited_payload"] == {"text": "Bản chị sửa"}
    assert calls["run"][0][2] == {"text": "Bản chị sửa", "channel": "facebook"}


async def test_return_with_note_calls_module(calls: dict, owner_client: httpx.AsyncClient) -> None:
    out = await _propose("test.post")
    empty = await owner_client.post(f"/api/desk/control/approvals/{out.item_id}/return", json={"note": ""})
    assert empty.status_code == 422
    r = await owner_client.post(f"/api/desk/control/approvals/{out.item_id}/return", json={"note": "Viết ngắn hơn"})
    assert r.status_code == 200 and r.json()["status"] == "returned" and r.json()["decision_note"] == "Viết ngắn hơn"
    assert calls["returned"] == ["Viết ngắn hơn"] and calls["run"] == []
    assert (await owner_client.post(f"/api/desk/control/approvals/{out.item_id}/approve", json={})).status_code == 409


async def test_off_blocks(calls: dict, db: AsyncSession) -> None:
    await control.set_level(db, "test.post", AutonomyLevel.OFF, None)
    await db.commit()
    out = await _propose("test.post")
    assert out.status == "blocked" and calls["run"] == []
    async with SessionLocal() as s:
        assert (await s.execute(select(ApprovalItem))).first() is None


async def test_locked_action_always_asks(calls: dict, owner_client: httpx.AsyncClient) -> None:
    out = await _propose("test.refund")
    assert out.status == "pending" and out.level == AutonomyLevel.LOCKED_ASK
    r = await owner_client.patch("/api/desk/control/autonomy/test.refund", json={"level": "auto"})
    assert r.status_code == 403 and r.json()["code"] == "autonomy_locked"
    rows = {a["action"]: a for a in (await owner_client.get("/api/desk/control/autonomy")).json()}
    assert rows["test.refund"]["locked"] and rows["test.refund"]["level"] == "locked_ask"
    assert rows["test.post"]["level"] == "ask" and rows["test.post"]["customer_facing"]
    # việc khoá có sẵn của hệ thống
    assert rows["control.raise_ai_budget"]["locked"]


async def test_change_autonomy_then_propose_applies(calls: dict, owner_client: httpx.AsyncClient) -> None:
    r = await owner_client.patch("/api/desk/control/autonomy/test.post", json={"level": "auto"})
    assert r.status_code == 200 and r.json()["level"] == "auto"
    assert (await _propose("test.post")).status == "applied"
    bad = await owner_client.patch("/api/desk/control/autonomy/test.post", json={"level": "locked_ask"})
    assert bad.status_code == 422
    missing = await owner_client.patch("/api/desk/control/autonomy/khong.co", json={"level": "auto"})
    assert missing.status_code == 404


async def test_helper_cannot_decide(calls: dict, helper_client: httpx.AsyncClient) -> None:
    out = await _propose("test.post")
    assert (await helper_client.get("/api/desk/control/approvals")).status_code == 200
    r = await helper_client.post(f"/api/desk/control/approvals/{out.item_id}/approve", json={})
    assert r.status_code == 403
    assert (
        await helper_client.patch("/api/desk/control/autonomy/test.post", json={"level": "auto"})
    ).status_code == 403


async def test_auto_failure_rolls_back_and_reports(calls: dict) -> None:
    out = await _propose("test.broken")
    assert out.status == "failed" and "hỏng" in (out.error or "")
    async with SessionLocal() as s:
        assert await s.get(AppSetting, "should.rollback") is None
        assert (await s.execute(select(AIActivity))).first() is None
        assert (await s.execute(select(AuditLog).where(AuditLog.action == "control.auto_failed"))).scalar_one()


async def test_approve_failure_marks_failed_and_can_retry(calls: dict, owner_client: httpx.AsyncClient) -> None:
    control.register_action("test.flaky", "Việc chập chờn", "Thử", default="ask")
    state = {"fail": True}

    @control.handler("test.flaky")
    async def _flaky(ctx: control.ActionContext) -> dict:
        if state["fail"]:
            raise RuntimeError("Mạng lỗi")
        return {"done": True}

    out = await _propose("test.flaky")
    r = await owner_client.post(f"/api/desk/control/approvals/{out.item_id}/approve", json={})
    assert r.json()["status"] == "failed" and r.json()["error"] == "Mạng lỗi"
    state["fail"] = False
    r = await owner_client.post(f"/api/desk/control/approvals/{out.item_id}/approve", json={})
    assert r.json()["status"] == "approved" and r.json()["attempts"] == 2 and r.json()["result"] == {"done": True}


async def test_dedupe_key_refreshes_pending_item(calls: dict) -> None:
    a = await _propose("test.post", dedupe_key="post:1", payload={"v": 1})
    b = await _propose("test.post", dedupe_key="post:1", payload={"v": 2}, title="Bản mới")
    c = await _propose("test.post", dedupe_key="post:2")
    assert a.item_id == b.item_id != c.item_id
    async with SessionLocal() as s:
        item = await s.get(ApprovalItem, a.item_id)
    assert item.payload == {"v": 2} and item.title == "Bản mới"


async def test_cancel_pending(calls: dict, db: AsyncSession) -> None:
    await _propose("test.post", dedupe_key="x")
    assert await control.cancel_pending(db, action="test.post", dedupe_key="x") == 1
    await db.commit()
    async with SessionLocal() as s:
        assert (await s.execute(select(ApprovalItem))).scalar_one().status == ApprovalStatus.CANCELLED


async def test_today_gathers_pending_done_and_stats(calls: dict, owner_client: httpx.AsyncClient) -> None:
    @control.stat_provider("test.orders", order=5)
    async def _orders(db: AsyncSession) -> list[control.Stat]:
        return [
            control.Stat(key="orders.today", label="Đơn hôm nay", value=3, order=3),
            control.Stat(key="orders.cash", label="Tiền về", value=450_000, format="vnd", order=4),
        ]

    @control.stat_provider("test.broken")
    async def _broken(db: AsyncSession) -> control.Stat:
        raise RuntimeError("provider hỏng")

    await _propose("test.post")
    await _propose("test.internal")
    r = await owner_client.get("/api/desk/control/today")
    assert r.status_code == 200
    body = r.json()
    assert body["pending"]["total"] == 1 and body["ai_done"]["total"] == 1
    stats = {s["key"]: s for s in body["stats"]}
    assert stats["control.pending"]["value"] == 1 and stats["orders.cash"]["format"] == "vnd"
    assert [s["key"] for s in body["stats"]][:4] == [
        "control.pending",
        "control.ai_done_today",
        "orders.today",
        "orders.cash",
    ]
    assert body["ai_cost"]["budget_vnd"] == 1_500_000


async def test_ai_costs_and_budget(owner_client: httpx.AsyncClient) -> None:
    async with SessionLocal() as s:
        for task, cost in (("a.x", 1000), ("a.x", 500), ("b.y", 200)):
            s.add(AIRun(task=task, provider="anthropic", model="m", tier="fast", status="ok", cost_vnd=cost))
        s.add(AIRun(task="b.y", provider="anthropic", model="m", tier="fast", status="error"))
        await s.commit()
    body = (await owner_client.get("/api/desk/control/ai/costs")).json()
    assert body["spent_vnd"] == 1700 and body["run_count"] == 4 and body["error_count"] == 1
    assert body["by_task"][0] == {"task": "a.x", "runs": 2, "cost_vnd": 1500, "input_tokens": 0, "output_tokens": 0}
    assert len(body["by_day"]) == 1
    r = await owner_client.patch("/api/desk/control/ai/budget", json={"monthly_budget_vnd": 3_000_000})
    assert r.status_code == 200 and r.json()["budget_vnd"] == 3_000_000
    assert (await owner_client.get("/api/desk/control/ai/costs?month=2026-1")).status_code == 422


async def test_approving_budget_raise_unblocks_ai(owner_client: httpx.AsyncClient) -> None:
    from pydantic import BaseModel

    from app import ai

    class Out(BaseModel):
        x: int

    async with SessionLocal() as s:
        s.add(AIRun(task="x", provider="anthropic", model="m", tier="fast", status="ok", cost_vnd=1_600_000))
        await s.commit()
    with pytest.raises(ai.AIBudgetExceeded):
        await ai.run("t.x", {"a": 1}, Out)
    item = (await owner_client.get("/api/desk/control/approvals")).json()["items"][0]
    assert item["action"] == "control.raise_ai_budget"
    r = await owner_client.post(f"/api/desk/control/approvals/{item['id']}/approve", json={})
    assert r.json()["status"] == "approved"
    assert (await ai.run("t.x", {"a": 1}, Out)).output.x == 1


async def test_settings_and_audit(owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient) -> None:
    rows = {s["key"]: s for s in (await owner_client.get("/api/desk/control/settings")).json()}
    assert rows["store.name"]["value"] == "Hàng Chọn" and rows["store.name"]["is_default"]
    r = await owner_client.patch("/api/desk/control/settings/store.name", json={"value": "Hàng Chọn Thử"})
    assert r.status_code == 200 and r.json()["value"] == "Hàng Chọn Thử" and not r.json()["is_default"]
    assert (await helper_client.patch("/api/desk/control/settings/store.name", json={"value": "x"})).status_code == 403
    audit = (await owner_client.get("/api/desk/control/audit?action=control.setting_changed")).json()
    assert audit["total"] == 1 and audit["items"][0]["data"]["to"] == "Hàng Chọn Thử"
    assert (await helper_client.get("/api/desk/control/audit")).status_code == 403


async def test_voice_command(calls: dict, owner_client: httpx.AsyncClient) -> None:
    intents = {i["key"] for i in (await owner_client.get("/api/desk/control/commands")).json()}
    assert {"control.pending_summary", "control.set_autonomy"} <= intents

    await _propose("test.post", title="Đăng bài bình giữ nhiệt")
    r = await owner_client.post("/api/desk/control/command", json={"text": "có việc gì chờ chị duyệt không"})
    body = r.json()
    assert body["status"] == "done" and body["intent"] == "control.pending_summary"
    assert "Đăng bài bình giữ nhiệt" in body["message"]

    r = await owner_client.post(
        "/api/desk/control/command",
        json={"text": "cho AI tự đăng bài", "context": {"action": "test.post", "level": "auto"}},
    )
    assert r.json()["status"] == "done", r.json()
    rows = {a["action"]: a for a in (await owner_client.get("/api/desk/control/autonomy")).json()}
    assert rows["test.post"]["level"] == "auto"

    r = await owner_client.post("/api/desk/control/command", json={"text": "thời tiết hôm nay thế nào"})
    assert r.json()["status"] == "unknown" and r.json()["message"]

    # thiếu tham số → hỏi lại
    r = await owner_client.post("/api/desk/control/command", json={"text": "cho AI tự đăng bài"})
    assert r.json()["status"] == "needs_clarification"


async def test_expire_approvals_job(calls: dict) -> None:
    from datetime import timedelta

    from app.core.jobs import enqueue
    from app.core.timeutil import now_utc

    old = await _propose("test.post", dedupe_key="old")
    fresh = await _propose("test.post", dedupe_key="fresh")
    async with SessionLocal() as s:
        (await s.get(ApprovalItem, old.item_id)).expires_at = now_utc() - timedelta(minutes=1)
        (await s.get(ApprovalItem, fresh.item_id)).expires_at = now_utc() + timedelta(days=1)
        await s.commit()
    assert await enqueue("control.expire_approvals") == 1
    async with SessionLocal() as s:
        assert (await s.get(ApprovalItem, old.item_id)).status == ApprovalStatus.EXPIRED
        assert (await s.get(ApprovalItem, fresh.item_id)).status == ApprovalStatus.PENDING
