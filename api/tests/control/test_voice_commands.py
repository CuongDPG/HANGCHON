"""i6 — ra lệnh bằng lời gọi việc của module khác qua sổ đăng ký lệnh (AI `fake` phân loại theo từ khoá).

Lệnh đổi dữ liệu đi qua control.propose theo mức tự chủ; lệnh chưa rõ đối tượng thì hỏi lại chị."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.timeutil import now_utc
from app.modules.catalog.models import Drop, DropStatus
from app.modules.content.models import ContentDraft
from app.modules.control.matching import match_names
from app.modules.control.models import ApprovalItem, ApprovalStatus, AuditLog
from app.modules.orders.models import OrderStatus
from tests.catalog.factories import published_product
from tests.finance.factory import make_customer, make_order

CMD = "/api/desk/control/command"


async def say(client: httpx.AsyncClient, text: str, **context) -> dict:
    r = await client.post(CMD, json={"text": text, "context": context})
    assert r.status_code == 200, r.text
    return r.json()


def test_match_names_rules() -> None:
    opts = [(1, "Bình giữ nhiệt 480 ml"), (2, "Bình hoa gốm"), (3, "Giá phơi gấp gọn inox")]
    assert match_names("soạn bài cho món bình giữ nhiệt", opts) == [1]
    assert match_names("binh giu nhiet", opts) == [1]  # gõ không dấu
    assert sorted(match_names("bình", opts)) == [1, 2]  # chưa rõ → hai lựa chọn, để hỏi lại
    assert match_names("máy xay sinh tố", opts) == []
    people = [("a", "Trần Thị Lan"), ("b", "Nguyễn Văn Bình")]
    assert match_names("tìm khách tên Lan", people) == ["a"]


async def test_commands_listed(owner_client: httpx.AsyncClient) -> None:
    keys = {i["key"] for i in (await owner_client.get("/api/desk/control/commands")).json()}
    assert {
        "control.pending_summary", "control.ai_cost", "content.compose_for_product", "orders.summary",
        "crm.find_customer", "catalog.open_drop", "catalog.close_drop", "finance.verify_backup", "sourcing.new_brief",
    } <= keys  # fmt: skip


async def test_unknown_command_asks_back(owner_client: httpx.AsyncClient) -> None:
    body = await say(owner_client, "thời tiết hôm nay thế nào")
    assert body["status"] == "unknown" and "nói rõ" in body["message"]


async def test_ai_cost(owner_client: httpx.AsyncClient) -> None:
    body = await say(owner_client, "tháng này AI tốn bao nhiêu tiền")
    assert body["status"] == "done" and body["intent"] == "control.ai_cost"
    assert "AI đã dùng" in body["message"] and body["href"] == "/desk/tu-chu/chi-phi-ai"


async def test_orders_summary_scopes(db, owner_client: httpx.AsyncClient) -> None:
    c = await make_customer(db, "Khách Đơn")
    ship = await make_order(db, customer=c)
    ship.status = OrderStatus.READY_TO_SHIP
    await make_order(db, customer=c, paid=False)
    await db.commit()

    body = await say(owner_client, "còn bao nhiêu đơn chờ giao")
    assert body["intent"] == "orders.summary" and body["data"]["scope"] == "to_ship"
    assert body["data"]["count"] == 1 and ship.code in body["message"]
    body = await say(owner_client, "đơn nào chưa chuyển khoản")
    assert body["data"]["scope"] == "waiting_payment" and body["data"]["count"] == 1
    body = await say(owner_client, "tóm tắt đơn hôm nay")
    assert body["data"]["scope"] == "today" and body["data"]["count"] == 2
    # tham số AI điền (model thật) được ưu tiên hơn đoán từ câu nói
    body = await say(owner_client, "tóm tắt đơn hàng", scope="to_ship")
    assert body["data"]["scope"] == "to_ship"


async def test_find_customer(db, owner_client: httpx.AsyncClient) -> None:
    lan = await make_customer(db, "Trần Thị Lan")
    await make_customer(db, "Nguyễn Thị Hoa")
    await make_customer(db, "Lê Thị Hoa")
    await db.commit()

    body = await say(owner_client, "tìm khách tên Lan")
    assert body["status"] == "done" and body["href"] == f"/desk/khach/so-khach/{lan.id}"
    body = await say(owner_client, f"tìm khách số {lan.phone[:4]} {lan.phone[4:]}")
    assert body["status"] == "done" and body["data"]["customer_id"] == str(lan.id)
    body = await say(owner_client, "tìm khách tên Hoa")
    assert body["status"] == "needs_clarification" and len(body["data"]["customer_ids"]) == 2
    body = await say(owner_client, "tìm khách tên Phượng")
    assert body["status"] == "needs_clarification" and "không thấy" in body["message"]


async def test_compose_for_product(db, owner_client: httpx.AsyncClient) -> None:
    p = await published_product(db, name="Bình giữ nhiệt 480 ml")
    await db.commit()

    body = await say(owner_client, "soạn bài cho món bình giữ nhiệt")
    assert body["intent"] == "content.compose_for_product" and body["status"] == "done", body
    assert body["href"] == f"/desk/noi-dung/san-pham/{p.id}" and "chưa đăng" in body["message"]
    drafts = (await db.execute(select(ContentDraft).where(ContentDraft.product_id == p.id))).scalars().all()
    assert drafts, "AI phải soạn bản nháp"
    # soạn bài không đăng thẳng: bài đăng vẫn chờ chị duyệt
    publish = (
        (
            await db.execute(
                select(ApprovalItem).where(
                    ApprovalItem.action == "content.publish_post", ApprovalItem.status == ApprovalStatus.PENDING
                )
            )
        )
        .scalars()
        .all()
    )
    assert publish

    body = await say(owner_client, "soạn bài cho món máy xay sinh tố")
    assert body["status"] == "needs_clarification"


async def _draft_drop(db, owner_client: httpx.AsyncClient) -> dict:
    p = await published_product(db, name="Chảo gang 24 cm")
    await db.commit()
    r = await owner_client.post(
        "/api/desk/catalog/drops",
        json={
            "title": "Đồ bếp gọn",
            "closes_at": (now_utc() + timedelta(days=3)).isoformat(),
            "items": [{"product_id": str(p.id), "slots_total": 5, "max_per_order": 2}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_open_and_close_drop_go_through_queue(
    db, owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient
) -> None:
    d = await _draft_drop(db, owner_client)
    body = await say(owner_client, f"mở đợt {d['code'][1:]}")
    assert body["intent"] == "catalog.open_drop" and body["status"] == "pending", body
    item_id = body["data"]["approval_item_id"]
    drop = await db.get(Drop, d["id"])
    await db.refresh(drop)
    assert drop.status == DropStatus.PENDING_REVIEW  # lệnh bằng lời không tự mở thay chị
    r = await owner_client.post(f"/api/desk/control/approvals/{item_id}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    await db.refresh(drop)
    assert drop.status == DropStatus.OPEN

    # người phụ không đóng đợt được (cùng quyền với nút «Đóng đợt»)
    body = await say(helper_client, f"đóng đợt {d['code'][1:]}")
    assert body["status"] == "failed" and "Chỉ chị" in body["message"]

    body = await say(owner_client, f"đóng đợt {d['code'][1:]}")
    assert body["intent"] == "catalog.close_drop" and body["status"] == "pending", body
    await db.refresh(drop)
    assert drop.status == DropStatus.OPEN  # chưa duyệt thì chưa đóng
    r = await owner_client.post(f"/api/desk/control/approvals/{body['data']['approval_item_id']}/approve", json={})
    assert r.json()["status"] == "approved", r.text
    await db.refresh(drop)
    assert drop.status == DropStatus.CLOSED

    body = await say(owner_client, "đóng đợt 999")
    assert body["status"] == "needs_clarification"


async def test_close_drop_auto_level_applies_now(db, owner_client: httpx.AsyncClient) -> None:
    """Chị đã cho AI tự làm «Đóng đợt bán sớm» → lệnh làm luôn, ghi nhật ký."""
    d = await _draft_drop(db, owner_client)
    await owner_client.post(f"/api/desk/catalog/drops/{d['id']}/open")
    r = await owner_client.patch("/api/desk/control/autonomy/catalog.close_drop", json={"level": "auto"})
    assert r.status_code == 200, r.text
    body = await say(owner_client, f"đóng đợt {d['code'][1:]}")
    assert body["status"] == "done" and body["data"]["outcome"] == "applied", body
    drop = await db.get(Drop, d["id"])
    await db.refresh(drop)
    assert drop.status == DropStatus.CLOSED
    # đặt «tắt» thì lệnh bị chặn, không làm gì
    await owner_client.patch("/api/desk/control/autonomy/catalog.open_drop", json={"level": "off"})
    d2 = await _draft_drop(db, owner_client)
    body = await say(owner_client, f"mở đợt {d2['code'][1:]}")
    assert body["status"] == "failed" and "đang tắt" in body["message"]
    await db.refresh(await db.get(Drop, d2["id"]))
    assert (await db.get(Drop, d2["id"])).status == DropStatus.DRAFT


async def test_verify_backup_command(
    owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.finance.test_backups import fake_pg_dump

    body = await say(owner_client, "kiểm bản sao lưu gần nhất")
    assert body["intent"] == "finance.verify_backup" and "Chưa có" in body["message"]
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    assert (await owner_client.post("/api/desk/finance/backups")).json()["status"] == "succeeded"
    body = await say(owner_client, "kiểm bản sao lưu gần nhất")
    assert body["status"] == "done" and body["data"]["ok"] is True and "checksum khớp" in body["message"]
    assert (await say(helper_client, "kiểm bản sao lưu gần nhất"))["status"] == "failed"


async def test_commands_are_audited(db, owner_client: httpx.AsyncClient) -> None:
    await say(owner_client, "tháng này AI tốn bao nhiêu tiền")
    rows = (await db.execute(select(AuditLog).where(AuditLog.action == "control.command"))).scalars().all()
    assert rows and rows[-1].entity_id == "control.ai_cost" and rows[-1].data["status"] == "done"
