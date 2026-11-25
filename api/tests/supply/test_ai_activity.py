"""Việc AI tự làm của nguồn cung có nhật ký AI (chỉ khi có thay đổi): d2 tính lại giá vốn, d7 dò mốc lô hàng,
d1 đổi bậc uy tín NCC; d4 AI đọc chứng từ (ảnh, PDF) → `extracted`, chị sửa được, hoàn tác được."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta
from decimal import Decimal

import httpx
from PIL import Image
from sqlalchemy import func, select

from app import control
from app.core.db import SessionLocal
from app.core.jobs import job_context
from app.core.timeutil import local_today, now_utc
from app.integrations import get_driver
from app.integrations.shipping import Address, ShippingRequest
from app.modules.control.models import AIActivity, ApprovalItem, AutonomyLevel
from app.modules.supply import service
from app.modules.supply.jobs import poll_inbound, recalc_cost_sheets
from app.modules.supply.models import (
    InboundShipment,
    POKind,
    POStatus,
    ProvenanceDocument,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from tests.selection.helpers import make_candidate

S = "/api/desk/supply"


async def _activities(action: str) -> list[AIActivity]:
    async with SessionLocal() as db:
        return list(
            (await db.execute(select(AIActivity).where(AIActivity.action == action).order_by(AIActivity.created_at)))
            .scalars()
        )  # fmt: skip


# ---- d2 ------------------------------------------------------------------------------------------------------------


async def test_cost_recalc_logs_only_significant_changes_and_undo_restores(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate()
    body = {"candidate_id": str(c.id), "unit_price_amount": "31", "currency": "CNY", "weight_grams": 2100,
            "domestic_shipping_vnd": 10000, "packaging_vnd": 0}  # fmt: skip
    sheet = (await owner_client.post(f"{S}/cost-sheets", json=body)).json()
    assert sheet["landed_cost_vnd"] == 174930

    # cron hằng ngày không có gì đổi → không ghi nhật ký
    assert await recalc_cost_sheets(job_context()) == 0
    assert await _activities(service.ACTION_RECALC) == []

    params = (await owner_client.get(f"{S}/settings")).json()
    params["fx_rates"]["CNY"] = "3660"  # đổi rất nhỏ (< 2%) → cập nhật lặng lẽ
    assert (await owner_client.patch(f"{S}/settings", json=params)).json()["recalculated"] == 1
    small = (await owner_client.get(f"{S}/cost-sheets/current", params={"candidate_id": str(c.id)})).json()
    assert small["landed_cost_vnd"] > 174930 and small["version"] == 2
    assert await _activities(service.ACTION_RECALC) == []

    params["fx_rates"]["CNY"] = "4000"  # tỷ giá tăng mạnh → nhật ký AI
    assert (await owner_client.patch(f"{S}/settings", json=params)).json()["recalculated"] == 1
    cur = (await owner_client.get(f"{S}/cost-sheets/current", params={"candidate_id": str(c.id)})).json()
    assert cur["version"] == 3 and cur["unit_price_vnd"] == 124000
    acts = await _activities(service.ACTION_RECALC)
    assert len(acts) == 1 and acts[0].undoable
    a = acts[0]
    assert a.title.startswith(f"Giá vốn {c.title_vi}: {small['landed_cost_vnd']:,}".replace(",", "."))
    assert "tăng" in a.summary and "Giá gốc" in (a.rationale or "")

    r = await owner_client.post(f"/api/desk/control/activity/{a.id}/undo")
    assert r.status_code == 200, r.text
    back = (await owner_client.get(f"{S}/cost-sheets/current", params={"candidate_id": str(c.id)})).json()
    assert back["landed_cost_vnd"] == small["landed_cost_vnd"] and back["version"] == 2


async def test_cost_recalc_ask_level_waits_for_owner(owner_client: httpx.AsyncClient) -> None:
    async with SessionLocal() as db:
        await control.set_level(db, service.ACTION_RECALC, AutonomyLevel.ASK, None)
        await db.commit()
    c = await make_candidate()
    await owner_client.post(f"{S}/cost-sheets", json={"candidate_id": str(c.id), "unit_price_amount": "31",
                                                      "currency": "CNY", "weight_grams": 2100})  # fmt: skip
    params = (await owner_client.get(f"{S}/settings")).json()
    params["fx_rates"]["CNY"] = "4200"
    assert (await owner_client.patch(f"{S}/settings", json=params)).json()["recalculated"] == 0
    cur = (await owner_client.get(f"{S}/cost-sheets/current", params={"candidate_id": str(c.id)})).json()
    assert cur["version"] == 1  # chưa duyệt thì giữ số cũ
    async with SessionLocal() as db:
        item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == service.ACTION_RECALC))
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.status_code == 200, r.text
    cur = (await owner_client.get(f"{S}/cost-sheets/current", params={"candidate_id": str(c.id)})).json()
    assert cur["version"] == 2 and cur["unit_price_vnd"] == 31 * 4200


# ---- d7 ------------------------------------------------------------------------------------------------------------


async def test_inbound_cron_logs_new_milestones_only(owner_client: httpx.AsyncClient) -> None:
    drv = get_driver("shipping")
    created = await drv.create(
        ShippingRequest(
            order_code="LO-2", to=Address(name="Kho", phone="0900000000", address_line="x", province="Hà Nội")
        ),
        "standard",
    )
    ship = (
        await owner_client.post(f"{S}/inbound", json={"tracking_code": created.tracking_code, "code": "K-7"})
    ).json()
    assert await poll_inbound(job_context()) == 0  # chưa có mốc mới → không ghi gì
    assert await _activities(service.ACTION_TRACK) == []

    drv.advance(2)
    assert await poll_inbound(job_context()) == 2
    acts = await _activities(service.ACTION_TRACK)
    assert len(acts) == 1 and acts[0].title == "Lô K-7: Đang về Việt Nam" and acts[0].undoable
    assert "Bên bán đã gửi" in acts[0].summary
    assert await poll_inbound(job_context()) == 0 and len(await _activities(service.ACTION_TRACK)) == 1

    # hoàn tác → bỏ các mốc AI vừa thêm
    assert (await owner_client.post(f"/api/desk/control/activity/{acts[0].id}/undo")).status_code == 200
    got = (await owner_client.get(f"{S}/inbound/{ship['id']}")).json()
    assert got["status"] == "ordered" and len(got["milestones"]) == 1

    # chị tự bấm cập nhật → không ghi nhật ký AI
    drv.advance(5)
    got = (await owner_client.post(f"{S}/inbound/{ship['id']}/sync")).json()
    assert got["status"] == "delivered" and len(await _activities(service.ACTION_TRACK)) == 1


async def test_inbound_cron_delivered_not_undoable(owner_client: httpx.AsyncClient) -> None:
    drv = get_driver("shipping")
    created = await drv.create(
        ShippingRequest(
            order_code="LO-3", to=Address(name="Kho", phone="0900000000", address_line="x", province="Hà Nội")
        ),
        "standard",
    )
    await owner_client.post(f"{S}/inbound", json={"tracking_code": created.tracking_code})
    drv.advance(9)
    assert await poll_inbound(job_context()) >= 1
    act = (await _activities(service.ACTION_TRACK))[-1]
    assert not act.undoable  # lô đã về nhà: đơn và kho đã nhận tin, không hoàn tác bằng nhật ký
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(InboundShipment).where(
            InboundShipment.received_at.is_not(None))) == 1  # fmt: skip


# ---- d1 ------------------------------------------------------------------------------------------------------------


async def _received_po(db, supplier: Supplier, *, late_days: int, defects: int) -> None:
    po = PurchaseOrder(
        code=f"LO-{uuid.uuid4().hex[:6]}", kind=POKind.BATCH, status=POStatus.RECEIVED, supplier_id=supplier.id,
        currency="CNY", expected_at=local_today(), sent_at=now_utc() - timedelta(days=10),
        received_at=now_utc() + timedelta(days=late_days), approved_at=now_utc() - timedelta(days=11),
    )  # fmt: skip
    po.lines.append(PurchaseOrderLine(position=0, description="x", quantity=10, unit_price_amount=Decimal(1),
                                      line_total_amount=Decimal(10), received_qty=10, defect_qty=defects))  # fmt: skip
    db.add(po)
    await db.flush()


async def test_trust_band_change_logged_but_score_updates_are_silent(db) -> None:
    s = Supplier(name="Xưởng ví dụ", country="CN")
    db.add(s)
    await db.flush()
    await _received_po(db, s, late_days=0, defects=0)
    await service.recompute_supplier(db, s.id)
    assert s.trust_score == 80  # lần đầu có điểm: không ghi nhật ký
    await _received_po(db, s, late_days=0, defects=0)
    await service.recompute_supplier(db, s.id)
    assert s.trust_score == 85  # vẫn «Tin được»: không ghi
    await db.commit()
    assert await _activities(service.ACTION_TRUST) == []

    for _ in range(2):
        await _received_po(db, s, late_days=5, defects=3)
    await service.recompute_supplier(db, s.id)
    await db.commit()
    acts = await _activities(service.ACTION_TRUST)
    assert len(acts) == 1 and acts[0].title.startswith("Xưởng ví dụ: Tin được →")
    await db.refresh(s)
    assert s.trust_score < 80


# ---- d4 ------------------------------------------------------------------------------------------------------------


def _photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (900, 1200), (240, 240, 235)).save(buf, "JPEG")
    return buf.getvalue()


def _text_pdf(text: str) -> bytes:
    """PDF một trang có chữ (tối thiểu, đủ cho pypdf đọc)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


async def _po(owner_client: httpx.AsyncClient) -> dict:
    sup = (await owner_client.post(f"{S}/suppliers", json={"name": "Xưởng Nghĩa Ô (ví dụ)", "kind": "factory",
                                                           "country": "cn", "language": "zh"})).json()  # fmt: skip
    r = await owner_client.post(f"{S}/purchase-orders", json={"kind": "batch", "supplier_id": sup["id"], "lines": [
        {"description": "Giá phơi chữ X", "quantity": 40, "unit_price_amount": "28"}]})  # fmt: skip
    return r.json()


async def test_document_photo_is_read_and_editable(owner_client: httpx.AsyncClient, fake_ai) -> None:
    seen = []
    original = fake_ai["supply.read_document"]

    def spy(inp):  # type: ignore[no-untyped-def]
        seen.append(inp)
        return original(inp)

    fake_ai["supply.read_document"] = spy
    po = await _po(owner_client)
    r = await owner_client.post(f"{S}/documents", data={"kind": "original_label", "purchase_order_id": po["id"]},
                                files={"file": ("nhan.jpg", _photo(), "image/jpeg")})  # fmt: skip
    assert r.status_code == 201, r.text
    doc = r.json()
    ex = doc["extracted"]
    assert ex["status"] == "read" and ex["product_name"] == "Giá phơi chữ X" and ex["source"] == "image"
    assert ex["manufacturer"] == "Xưởng Nghĩa Ô (ví dụ)"
    assert seen[0].expected_items == ["Giá phơi chữ X"] and seen[0].pdf_text is None
    act = (await _activities(service.ACTION_READ_DOC))[0]
    assert act.undoable and act.ref_id == uuid.UUID(doc["id"])

    # chị sửa phần AI đọc → giữ, đánh dấu đã sửa; AI không ghi đè
    r = await owner_client.patch(f"{S}/documents/{doc['id']}", json={
        "extracted": {"lot_number": "LOT-1102", "origin_country": "CN"}, "doc_number": "NH-01"})  # fmt: skip
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["extracted"]["lot_number"] == "LOT-1102" and got["extracted"]["edited"] is True
    assert got["extracted"]["product_name"] == "Giá phơi chữ X" and got["doc_number"] == "NH-01"

    # đọc lại (chị bấm) → AI đọc mới, bỏ phần đã sửa
    got = (await owner_client.post(f"{S}/documents/{doc['id']}/read")).json()
    assert got["extracted"]["status"] == "read" and not got["extracted"].get("edited")

    # hoàn tác lần đọc gần nhất → về trạng thái trước đó
    act = (await _activities(service.ACTION_READ_DOC))[-1]
    assert (await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")).status_code == 200
    async with SessionLocal() as db:
        d = await db.get(ProvenanceDocument, uuid.UUID(doc["id"]))
    assert d.extracted == {"status": "reading"}


async def test_document_pdf_text_is_read(owner_client: httpx.AsyncClient, fake_ai) -> None:
    seen = []
    original = fake_ai["supply.read_document"]
    fake_ai["supply.read_document"] = lambda inp: (seen.append(inp), original(inp))[1]
    po = await _po(owner_client)
    pdf = _text_pdf("Invoice No: HD2026088  Lot: LOT-778  Made in China  2026-11-02")
    doc = (await owner_client.post(f"{S}/documents", data={"kind": "invoice", "purchase_order_id": po["id"]},
                                   files={"file": ("hd.pdf", pdf, "application/pdf")})).json()  # fmt: skip
    assert "LOT-778" in (seen[0].pdf_text or "")
    ex = doc["extracted"]
    assert ex["lot_number"] == "LOT-778" and ex["origin_country"] == "CN" and ex["source"] == "pdf_text"
    # các ô chị để trống được điền từ chứng từ
    assert doc["doc_number"] == "HD2026088" and doc["doc_date"] == "2026-11-02"


async def test_document_unreadable_failed_and_ask(owner_client: httpx.AsyncClient, fake_ai) -> None:
    po = await _po(owner_client)
    up = {"kind": "invoice", "purchase_order_id": po["id"]}
    doc = (await owner_client.post(f"{S}/documents", data=up,
                                   files={"file": ("x.pdf", b"%PDF-1.4 hong", "application/pdf")})).json()  # fmt: skip
    assert doc["extracted"]["status"] == "unreadable"

    from app import ai

    def boom(inp):  # type: ignore[no-untyped-def]
        raise ai.FakeRefusal("cyber")

    fake_ai["supply.read_document"] = boom
    doc = (await owner_client.post(f"{S}/documents", data=up,
                                   files={"file": ("a.jpg", _photo(), "image/jpeg")})).json()  # fmt: skip
    assert doc["extracted"]["status"] == "failed"  # lỗi AI không chặn việc lưu chứng từ

    fake_ai.pop("supply.read_document")
    async with SessionLocal() as db:
        await control.set_level(db, service.ACTION_READ_DOC, AutonomyLevel.ASK, None)
        await db.commit()
    fake_ai["supply.read_document"] = lambda inp: {"readable": True, "summary": "Hoá đơn", "lot_number": "L-9"}
    doc = (await owner_client.post(f"{S}/documents", data=up,
                                   files={"file": ("b.jpg", _photo(), "image/jpeg")})).json()  # fmt: skip
    assert doc["extracted"] == {"status": "pending"}
    async with SessionLocal() as db:
        item = await db.scalar(select(ApprovalItem).where(ApprovalItem.action == service.ACTION_READ_DOC))
    await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    got = (await owner_client.get(f"{S}/documents", params={"purchase_order_id": po["id"]})).json()
    assert next(d for d in got if d["id"] == doc["id"])["extracted"]["lot_number"] == "L-9"


async def test_document_edit_needs_login(client: httpx.AsyncClient) -> None:
    assert (await client.patch(f"{S}/documents/{uuid.uuid4()}", json={})).status_code == 401
