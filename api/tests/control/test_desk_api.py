"""Endpoint control thêm cho bàn làm việc: duyệt hàng loạt, nhóm việc chờ, gợi ý nới mức tự chủ, «Hôm nay» gom theo
loại, lọc nhật ký theo ngày, lưu vết kèm tên người, cài đặt hàng loạt, danh sách driver tích hợp."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest

from app import control
from app.core.db import SessionLocal
from app.core.timeutil import local_today, now_utc
from app.modules.control.models import AIActivity, ApprovalItem, ApprovalStatus, User
from app.modules.control.service import SUGGEST_STREAK

pytestmark = pytest.mark.usefixtures("temp_registry")


@pytest.fixture
def actions() -> list[Any]:
    ran: list[Any] = []
    control.register_action("t.post", "Đăng bài thử", "Nội dung", default="ask", customer_facing=True)
    control.register_action("t.refund", "Hoàn tiền thử", "Đơn hàng", locked=True)
    control.register_action("t.reply", "Trả lời thử", "Khách", default="auto")

    for key in ("t.post", "t.refund", "t.reply"):

        @control.handler(key)
        async def _h(ctx: control.ActionContext, key: str = key) -> dict:
            if ctx.payload.get("boom"):
                raise RuntimeError("hỏng")
            ran.append((key, ctx.payload))
            return {"ok": True}

    return ran


async def _propose(action: str, n: int = 1, **kw: Any) -> list[control.ProposeOutcome]:
    out = []
    async with SessionLocal() as db:
        for i in range(n):
            out.append(await control.propose(action, f"{action} #{i}", {"i": i, **kw}, {"text": f"Bài {i}"}, db=db))
        await db.commit()
    return out


async def test_groups_and_batch_approve(
    actions: list, owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    posts = await _propose("t.post", 3)
    await _propose("t.refund", 1)
    broken = (await _propose("t.post", 1, boom=True))[0]
    groups = (await owner_client.get("/api/desk/control/approvals/groups")).json()
    assert groups[0] == {"action": "t.post", "label": "Đăng bài thử", "group": "Nội dung", "locked": False, "count": 4}
    assert groups[1]["locked"] is True

    items = (await owner_client.get("/api/desk/control/approvals?action=t.refund")).json()["items"]
    assert items[0]["locked"] and items[0]["action_label"] == "Hoàn tiền thử"

    ids = [str(p.item_id) for p in posts] + [str(broken.item_id), str(posts[0].item_id)]
    assert (await helper_client.post("/api/desk/control/approvals/approve-batch", json={"ids": ids})).status_code == 403
    r = await owner_client.post("/api/desk/control/approvals/approve-batch", json={"ids": ids, "note": "ok"})
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] == 3 and body["failed"] == 1 and len(body["results"]) == 4  # id trùng bị gộp
    assert next(x for x in body["results"] if x["status"] == "failed")["error"] == "hỏng"
    again = (await owner_client.post("/api/desk/control/approvals/approve-batch", json={"ids": ids[:1]})).json()
    assert again["results"][0]["status"] is None and "xử lý" in again["results"][0]["error"]
    assert len(actions) == 3

    done = (await owner_client.get("/api/desk/control/approvals?status=approved&status=failed")).json()
    assert done["total"] == 4
    assert (await owner_client.post("/api/desk/control/approvals/approve-batch", json={"ids": []})).status_code == 422


async def test_autonomy_suggests_loosening_after_clean_streak(
    actions: list, owner_client: httpx.AsyncClient, owner: User
) -> None:
    async with SessionLocal() as db:
        base = now_utc() - timedelta(days=1)
        # cũ nhất: 1 lần sửa rồi duyệt, sau đó SUGGEST_STREAK lần duyệt thẳng
        for i in range(SUGGEST_STREAK + 1):
            db.add(ApprovalItem(action="t.post", module="t", title="x", status=ApprovalStatus.APPROVED,
                                edited_payload={"a": 1} if i == 0 else None, decided_at=base + timedelta(minutes=i),
                                decided_by_id=owner.id))  # fmt: skip
        db.add(ApprovalItem(action="t.refund", module="t", title="x", status=ApprovalStatus.APPROVED,
                            decided_at=base, decided_by_id=owner.id))  # fmt: skip
        await db.commit()
    rows = {a["action"]: a for a in (await owner_client.get("/api/desk/control/autonomy")).json()}
    assert rows["t.post"]["history"] == {
        "approved": SUGGEST_STREAK + 1,
        "edited": 1,
        "returned": 0,
        "streak": SUGGEST_STREAK,
    }
    assert rows["t.post"]["suggest_auto"] is True
    assert rows["t.refund"]["suggest_auto"] is False  # khoá cứng thì không gợi ý
    assert rows["t.reply"]["suggest_auto"] is False and rows["t.reply"]["history"]["streak"] == 0

    # một lần trả lại mới nhất → chuỗi về 0
    async with SessionLocal() as db:
        db.add(ApprovalItem(action="t.post", module="t", title="x", status=ApprovalStatus.RETURNED, decided_at=now_utc(),
                            decided_by_id=owner.id))  # fmt: skip
        await db.commit()
    rows = {a["action"]: a for a in (await owner_client.get("/api/desk/control/autonomy")).json()}
    assert rows["t.post"]["history"]["streak"] == 0 and rows["t.post"]["suggest_auto"] is False

    await owner_client.patch("/api/desk/control/autonomy/t.post", json={"level": "auto"})
    rows = {a["action"]: a for a in (await owner_client.get("/api/desk/control/autonomy")).json()}
    assert rows["t.post"]["level"] == "auto" and rows["t.post"]["suggest_auto"] is False


async def test_today_groups_auto_work(actions: list, owner_client: httpx.AsyncClient) -> None:
    await _propose("t.reply", 3)
    p = (await _propose("t.post", 1))[0]
    await owner_client.post(f"/api/desk/control/approvals/{p.item_id}/approve", json={})
    body = (await owner_client.get("/api/desk/control/today")).json()
    assert body["ai_done"]["total"] == 4 and body["ai_done"]["auto_total"] == 3
    assert body["ai_done"]["groups"] == [{"action": "t.reply", "label": "Trả lời thử", "count": 3}]
    assert body["ai_done"]["items"][0]["action_label"]


async def test_activity_date_filter(actions: list, owner_client: httpx.AsyncClient) -> None:
    await _propose("t.reply", 2)
    async with SessionLocal() as db:
        act = AIActivity(action="t.reply", module="t", title="cũ", mode="auto")
        db.add(act)
        await db.flush()
        act.created_at = now_utc() - timedelta(days=3)
        await db.commit()
    today = local_today().isoformat()
    r = (await owner_client.get(f"/api/desk/control/activity?date_from={today}&date_to={today}")).json()
    assert r["total"] == 2
    old = (local_today() - timedelta(days=3)).isoformat()
    r = (await owner_client.get(f"/api/desk/control/activity?date_from={old}&date_to={old}")).json()
    assert r["total"] == 1 and r["items"][0]["title"] == "cũ"
    assert (await owner_client.get("/api/desk/control/activity?date_from=2026-13-01")).status_code == 422


async def test_audit_has_actor_name_and_multi_filter(actions: list, owner_client: httpx.AsyncClient) -> None:
    p = await _propose("t.post", 2)
    await owner_client.post(f"/api/desk/control/approvals/{p[0].item_id}/approve", json={})
    await owner_client.post(f"/api/desk/control/approvals/{p[1].item_id}/return", json={"note": "viết lại"})
    r = (await owner_client.get("/api/desk/control/audit?actions=control.approved&actions=control.returned")).json()
    assert r["total"] == 2 and {x["action"] for x in r["items"]} == {"control.approved", "control.returned"}
    assert all(x["actor_name"] == "Chị" for x in r["items"]) and r["pages"] == 1


async def test_bulk_settings(owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient) -> None:
    vals = {
        "store.curator_name": "Chị Thử",
        "store.bank_account_no": "0123456789",
        "store.default_shipping_fee_vnd": 25000,
    }
    r = await owner_client.patch("/api/desk/control/settings", json={"values": vals})
    assert r.status_code == 200
    rows = {s["key"]: s for s in r.json()}
    assert rows["store.curator_name"]["value"] == "Chị Thử" and rows["store.default_shipping_fee_vnd"]["value"] == 25000
    assert rows["store.name"]["is_default"] is True
    bad = await owner_client.patch(
        "/api/desk/control/settings", json={"values": {"store.default_shipping_fee_vnd": -1}}
    )
    assert bad.status_code == 400
    unknown = await owner_client.patch("/api/desk/control/settings", json={"values": {"khong.co": 1}})
    assert unknown.status_code == 400
    assert (await helper_client.patch("/api/desk/control/settings", json={"values": vals})).status_code == 403


async def test_integrations_list(helper_client: httpx.AsyncClient) -> None:
    rows = {x["kind"]: x for x in (await helper_client.get("/api/desk/control/integrations")).json()}
    assert rows["einvoice"]["driver"] == "mock" and rows["einvoice"]["is_mock"] is True
    assert rows["storage"]["driver"] == "local" and "s3" in rows["storage"]["available"]
    assert rows["payments"]["label"] == "Thanh toán chuyển khoản"


def test_demo_actions_not_loaded_by_default() -> None:
    assert not any(k.startswith("demo.") for k in control.ACTIONS)
