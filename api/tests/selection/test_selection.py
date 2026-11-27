"""Bàn chọn (c1–c6): chuyển cột, nhật ký thử, lý do chọn/loại, nguyên tắc, gu của chị."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
from sqlalchemy import select

from app.core import events
from app.core.db import SessionLocal
from app.core.jobs import enqueue
from app.core.timeutil import now_utc
from app.modules.catalog.models import Category
from app.modules.control.models import ApprovalItem, ApprovalStatus
from app.modules.selection.models import TasteProfile
from app.modules.sourcing.models import CandidateStage
from tests.selection.helpers import capture, make_brief, make_candidate

B = "/api/desk/selection"


async def _stage(c: httpx.AsyncClient, cid, to: str, **kw) -> httpx.Response:
    return await c.post(f"{B}/candidates/{cid}/stage", json={"to": to, **kw})


async def _note(c: httpx.AsyncClient, cid, text: str, **files) -> httpx.Response:
    return await c.post(f"{B}/candidates/{cid}/notes", data={"text": text}, files=files or None)


# ---- c1 ------------------------------------------------------------------------------------------------------------


async def test_board_requires_login(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{B}/board")).status_code == 401


async def test_board_columns_trial_progress_and_seal(owner_client: httpx.AsyncClient, helper_client) -> None:
    brief = await make_brief()
    await make_candidate("Khăn tắm cho bé", stage=CandidateStage.TRIAL, days_in_stage=8.5, brief_id=brief.id)
    await make_candidate("Giá phơi chữ X", brief_id=brief.id)
    await make_candidate("Hộp cơm inox", stage=CandidateStage.SELECTED, days_in_stage=1, brief_id=brief.id)

    r = await helper_client.get(f"{B}/board")  # người phụ xem được
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["counts"] == {"candidate": 1, "sample": 0, "trial": 1, "selected": 1, "rejected": 0}
    trial = body["columns"]["trial"][0]
    assert trial["trial_day"] == 9 and trial["trial_days"] == 14
    assert trial["seal"] == {"chosen": 1, "total": 3}

    await owner_client.patch(f"{B}/settings", json={"trial_days": 10})
    assert (await owner_client.get(f"{B}/board")).json()["columns"]["trial"][0]["trial_days"] == 10


async def test_move_emits_stage_changed_and_orders_column(owner_client: httpx.AsyncClient) -> None:
    a = await make_candidate("Bình giữ nhiệt")
    b = await make_candidate("Hộp đựng gia vị")
    with capture("candidate.stage_changed") as seen:
        r = await _stage(owner_client, a.id, "trial")
        assert r.status_code == 200, r.text
        assert r.json()["card"]["stage"] == "trial" and r.json()["card"]["trial_day"] == 1
        await _stage(owner_client, b.id, "trial")
    assert ("candidate.stage_changed", {"candidate_id": str(a.id), "from": "candidate", "to": "trial"}) in seen
    # món mới vào nằm trên cùng; kéo thả đổi thứ tự trong cột không phát sự kiện
    col = (await owner_client.get(f"{B}/board")).json()["columns"]["trial"]
    assert [x["title"] for x in col] == ["Hộp đựng gia vị", "Bình giữ nhiệt"]
    with capture("candidate.stage_changed") as seen:
        r = await _stage(owner_client, a.id, "trial", position=0)
        assert r.status_code == 200
    assert seen == []
    col = (await owner_client.get(f"{B}/board")).json()["columns"]["trial"]
    assert [x["title"] for x in col] == ["Bình giữ nhiệt", "Hộp đựng gia vị"]
    r = await _stage(owner_client, a.id, "trial")
    assert r.status_code == 409 and r.json()["code"] == "same_stage"


async def test_board_sort_by_time_keeps_manual_order(owner_client: httpx.AsyncClient, monkeypatch) -> None:
    old = await make_candidate("Móc treo cũ", stage=CandidateStage.TRIAL, days_in_stage=5)
    mid = await make_candidate("Kẹp phơi", stage=CandidateStage.TRIAL, days_in_stage=3)
    new = await make_candidate("Giá úp cốc", stage=CandidateStage.TRIAL, days_in_stage=1)
    # thứ tự chị kéo: kẹp phơi, móc treo, giá úp cốc
    for cid, pos in ((mid.id, 0), (old.id, 1), (new.id, 2)):
        assert (await _stage(owner_client, cid, "trial", position=pos)).status_code == 200

    async def titles(**query) -> list[str]:
        r = await owner_client.get(f"{B}/board", params=query)
        assert r.status_code == 200, r.text
        return [x["title"] for x in r.json()["columns"]["trial"]]

    manual = ["Kẹp phơi", "Móc treo cũ", "Giá úp cốc"]
    assert await titles() == manual
    assert await titles(sort="newest") == ["Giá úp cốc", "Kẹp phơi", "Móc treo cũ"]
    assert await titles(sort="oldest") == ["Móc treo cũ", "Kẹp phơi", "Giá úp cốc"]
    assert await titles(sort="manual") == manual  # xếp theo thời gian không ghi đè thứ tự tự xếp

    # cột vượt trần: trần chọn đúng phần đầu theo cách xếp
    monkeypatch.setattr("app.modules.selection.service.BOARD_LIMIT", 2)
    assert await titles(sort="newest") == ["Giá úp cốc", "Kẹp phơi"]
    assert await titles(sort="oldest") == ["Móc treo cũ", "Kẹp phơi"]
    assert await titles() == manual[:2]
    assert (await owner_client.get(f"{B}/board", params={"sort": "newest"})).json()["counts"]["trial"] == 3

    # ứng viên chưa chuyển cột lần nào: tính theo lúc tìm thấy
    await make_candidate("Tìm trước", created_at=now_utc() - timedelta(days=2))
    await make_candidate("Tìm sau", created_at=now_utc() - timedelta(days=1))
    r = await owner_client.get(f"{B}/board", params={"sort": "oldest"})
    assert [x["title"] for x in r.json()["columns"]["candidate"]] == ["Tìm trước", "Tìm sau"]

    assert (await owner_client.get(f"{B}/board", params={"sort": "moi"})).status_code == 422


async def test_helper_cannot_decide(helper_client: httpx.AsyncClient) -> None:
    c = await make_candidate()
    assert (await _stage(helper_client, c.id, "trial")).status_code == 403


async def test_unknown_candidate_404(owner_client: httpx.AsyncClient) -> None:
    assert (await _stage(owner_client, uuid.uuid4(), "trial")).status_code == 404
    r = await owner_client.post(f"{B}/candidates/{uuid.uuid4()}/stage", json={"to": "nope"})
    assert r.status_code == 422


# ---- c4 ------------------------------------------------------------------------------------------------------------


async def test_reject_requires_reason_and_feeds_stats(owner_client: httpx.AsyncClient, client) -> None:
    brief = await make_brief()
    a = await make_candidate("Bình nước thể thao", stage=CandidateStage.TRIAL, brief_id=brief.id)
    b = await make_candidate("Hộp cơm giữ nhiệt", stage=CandidateStage.TRIAL, brief_id=brief.id)
    r = await _stage(owner_client, a.id, "rejected")
    assert r.status_code == 400 and r.json()["code"] == "reason_required"

    with capture("candidate.rejected") as seen:
        r = await _stage(owner_client, a.id, "rejected", reason="Rò nước ở nắp sau 3 ngày")
    assert r.status_code == 200, r.text
    d = r.json()["decision"]
    assert d["decision"] == "rejected" and d["rejection_tags"] == ["ro_ri"]
    assert d["rejection_groups"] == [{"key": "ro_ri", "label": "Rò nước"}]
    assert seen == [("candidate.rejected", {"candidate_id": str(a.id), "decision_id": d["id"]})]
    r = await _stage(owner_client, b.id, "rejected", reason="Không thích", reason_tags=["mui"])
    assert r.json()["decision"]["rejection_tags"] == ["mui"]

    stats = (await owner_client.get(f"{B}/rejection-stats", params={"brief_id": str(brief.id)})).json()
    assert stats["total"] == 2 and stats["summary"].startswith("2 mẫu loại: ")
    # thống kê lý do loại chỉ ở desk, không còn route công khai
    assert (await client.get("/api/store/selection/rejection-stats")).status_code == 404

    reasons = (await owner_client.get(f"{B}/reject-reasons")).json()
    assert reasons["frequent"][0]["count"] >= 1 and any(g["key"] == "ro_ri" for g in reasons["groups"])


# ---- c2 ------------------------------------------------------------------------------------------------------------


async def test_trial_note_text_photo_audio_organized(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate(stage=CandidateStage.TRIAL, days_in_stage=3)
    r = await _note(
        owner_client,
        c.id,
        "Phơi chăn mùa đông không võng. Gấp lại dày 6 cm. Ốc hơi lỏng sau một tuần",
        photos=("anh.jpg", b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg"),
        audio=("ghi-am.webm", b"\x1aE\xdf\xa3fakewebm", "audio/webm"),
    )
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["trial_day"] == 4 and n["kind"] == "voice" and n["processing_status"] == "done"
    assert [p["kind"] for p in n["points"]] == ["good", "measure", "bad"]
    assert n["photo_urls"][0].startswith("/api/files/private/trial-notes/")
    assert n["audio_url"] and (await owner_client.get(n["audio_url"])).status_code == 200

    detail = (await owner_client.get(f"{B}/candidates/{c.id}")).json()
    assert detail["card"]["note_count"] == 1 and len(detail["notes"]) == 1

    r = await owner_client.post(f"{B}/candidates/{c.id}/notes", data={"text": "  "})
    assert r.status_code == 400 and r.json()["code"] == "empty_note"
    r = await owner_client.post(
        f"{B}/candidates/{c.id}/notes", data={"text": "x"}, files={"photos": ("a.txt", b"hi", "text/plain")}
    )
    assert r.status_code == 400 and r.json()["code"] == "bad_file_type"

    r = await owner_client.patch(f"{B}/notes/{n['id']}", json={"points": [{"kind": "good", "text": "Chắc tay."}]})
    assert r.json()["points"] == [{"kind": "good", "text": "Chắc tay."}]
    assert (await owner_client.delete(f"{B}/notes/{n['id']}")).status_code == 204


async def test_loose_note_assigned_by_ai(owner_client: httpx.AsyncClient) -> None:
    target = await make_candidate("Giá phơi chữ X", stage=CandidateStage.TRIAL)
    await make_candidate("Khăn tắm cho bé", stage=CandidateStage.TRIAL)
    r = await owner_client.post(f"{B}/notes", data={"text": "Cái giá phơi gấp gọn, phơi chăn được", "voice": "true"})
    assert r.status_code == 201, r.text
    assert r.json()["candidate_id"] == str(target.id) and r.json()["ai_assigned"] is True
    r = await owner_client.post(f"{B}/notes", data={"text": "Hôm nay trời mưa"})
    assert r.json()["candidate_id"] is None
    assert len((await owner_client.get(f"{B}/notes/unassigned")).json()) == 1


async def test_organize_note_waits_when_level_ask(owner_client: httpx.AsyncClient) -> None:
    await owner_client.patch("/api/desk/control/autonomy/selection.organize_note", json={"level": "ask"})
    c = await make_candidate(stage=CandidateStage.TRIAL)
    n = (await _note(owner_client, c.id, "Rửa nhanh, không bám dầu")).json()
    assert n["processing_status"] == "pending" and n["points"] == []
    async with SessionLocal() as s:
        item = await s.scalar(select(ApprovalItem).where(ApprovalItem.action == "selection.organize_note"))
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "approved"
    notes = (await owner_client.get(f"{B}/candidates/{c.id}/notes")).json()
    assert notes[0]["processing_status"] == "done" and notes[0]["points"]


# ---- c3 ------------------------------------------------------------------------------------------------------------


async def test_select_drafts_reasons_only_from_notes_then_owner_approves(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate(stage=CandidateStage.TRIAL, days_in_stage=13)
    await _note(owner_client, c.id, "Phơi chăn mùa đông không võng. Dựng sau cửa rất gọn. Inox chắc tay")
    await _note(owner_client, c.id, "Hộp móp khi giao")
    with capture("candidate.selected") as seen:
        r = await _stage(owner_client, c.id, "selected")
    assert r.status_code == 200, r.text
    d = r.json()["decision"]
    assert seen == [("candidate.selected", {"candidate_id": str(c.id), "decision_id": d["id"]})]
    assert d["draft_status"] == "pending_review" and d["trial_days"] == 13
    assert len(d["draft_reasons_list"]) == 3
    joined = " ".join(d["draft_reasons_list"] + d["draft_not_satisfied_list"]).lower()
    assert "võng" in joined and "móp" in d["draft_not_satisfied_list"][0].lower()
    assert d["approval_item_id"]  # mặc định «hỏi chị»: nằm trong hàng chờ duyệt

    r = await owner_client.post(
        f"{B}/decisions/{d['id']}/approve",
        json={"reason_selected": ["Phơi chăn mùa đông không võng.", "Gấp gọn sau cửa."], "not_satisfied": ["Hộp móp."]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["draft_status"] == "approved" and r.json()["reasons_list"][1] == "Gấp gọn sau cửa."
    async with SessionLocal() as s:
        item = await s.get(ApprovalItem, uuid.UUID(d["approval_item_id"]))
        assert item.status == ApprovalStatus.APPROVED and item.edited_payload


async def test_select_without_notes_and_auto_level(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate(stage=CandidateStage.TRIAL)
    d = (await _stage(owner_client, c.id, "selected")).json()["decision"]
    assert d["draft_status"] == "pending_review" and d["draft_reasons_list"] == []
    r = await owner_client.post(f"{B}/decisions/{d['id']}/approve", json={"reason_selected": [], "not_satisfied": []})
    assert r.status_code == 422

    await owner_client.patch("/api/desk/control/autonomy/selection.draft_reasons", json={"level": "auto"})
    c2 = await make_candidate("Thớt gỗ", stage=CandidateStage.TRIAL)
    await _note(owner_client, c2.id, "Không mùi gỗ, cắt không trượt")
    d2 = (await _stage(owner_client, c2.id, "selected")).json()["decision"]
    assert d2["draft_status"] == "approved" and d2["reasons_list"]


async def test_return_draft_redrafts_and_change_mind_cancels(owner_client: httpx.AsyncClient) -> None:
    c = await make_candidate(stage=CandidateStage.TRIAL)
    await _note(owner_client, c.id, "Gọn, nhẹ")
    d = (await _stage(owner_client, c.id, "selected")).json()["decision"]
    r = await owner_client.post(
        f"/api/desk/control/approvals/{d['approval_item_id']}/return", json={"note": "Ngắn hơn"}
    )
    assert r.json()["status"] == "returned"
    async with SessionLocal() as s:
        pending = (await s.execute(select(ApprovalItem).where(ApprovalItem.status == ApprovalStatus.PENDING))).scalars()
        assert [i.action for i in pending] == ["selection.draft_reasons"]  # AI soạn lại theo lời nhắn
    # đổi ý: kéo về Đang thử → bản nháp đang chờ bị huỷ
    await _stage(owner_client, c.id, "trial")
    async with SessionLocal() as s:
        left = await s.scalar(select(ApprovalItem).where(ApprovalItem.status == ApprovalStatus.PENDING))
        assert left is None


async def test_selected_links_to_product_and_rejected_points_to_chosen(owner_client: httpx.AsyncClient) -> None:
    """Đã chọn → sản phẩm nháp (lối sang Nội dung); món loại cùng đề → biết món nào được chọn thay."""
    brief = await make_brief()
    a = await make_candidate("Bình giữ nhiệt nắp bật", stage=CandidateStage.TRIAL, brief_id=brief.id)
    b = await make_candidate("Bình giữ nhiệt nắp vặn", stage=CandidateStage.TRIAL, brief_id=brief.id)
    lone = await make_candidate("Hộp cơm không đề", stage=CandidateStage.TRIAL)
    assert (await _stage(owner_client, a.id, "selected")).status_code == 200
    await _stage(owner_client, b.id, "rejected", reason="Nắp vặn khó mở khi tay ướt")
    await _stage(owner_client, lone.id, "rejected", reason="Ám mùi nhựa")

    board = (await owner_client.get(f"{B}/board")).json()
    card = next(x for x in board["columns"]["selected"] if x["id"] == str(a.id))
    assert card["product_id"]
    assert all(x["product_id"] is None for x in board["columns"]["rejected"])

    da = (await owner_client.get(f"{B}/candidates/{a.id}")).json()
    assert da["decision"]["product_id"] == card["product_id"] and da["chosen_peers"] == []
    db_ = (await owner_client.get(f"{B}/candidates/{b.id}")).json()
    assert db_["chosen_peers"] == [
        {"candidate_id": str(a.id), "title": "Bình giữ nhiệt nắp bật", "product_id": card["product_id"]}
    ]
    assert (await owner_client.get(f"{B}/candidates/{lone.id}")).json()["chosen_peers"] == []


# ---- c5 ------------------------------------------------------------------------------------------------------------


async def test_principles_crud(owner_client: httpx.AsyncClient, helper_client) -> None:
    async with SessionLocal() as s:
        cat = Category(name="Nhà bếp", slug="nha-bep-test")
        s.add(cat)
        await s.commit()
    r = await owner_client.post(f"{B}/principles", json={"kind": "must_not", "text": "Không chọn hàng có pin"})
    assert r.status_code == 201
    general = r.json()
    r = await owner_client.post(
        f"{B}/principles", json={"kind": "prefer", "text": "Ưu tiên inox 304", "category_id": str(cat.id)}
    )
    kitchen = r.json()
    assert (await helper_client.post(f"{B}/principles", json={"kind": "must", "text": "abc"})).status_code == 403
    bad = await owner_client.post(
        f"{B}/principles", json={"kind": "must", "text": "abcd", "category_id": str(uuid.uuid4())}
    )
    assert bad.status_code == 400

    got = (await owner_client.get(f"{B}/principles", params={"category_id": str(cat.id), "active_only": True})).json()
    assert {p["id"] for p in got} == {general["id"], kitchen["id"]}
    r = await owner_client.patch(f"{B}/principles/{kitchen['id']}", json={"is_active": False, "text": "Ưu tiên inox"})
    assert r.json()["is_active"] is False and r.json()["text"] == "Ưu tiên inox"
    got = (await owner_client.get(f"{B}/principles", params={"category_id": str(cat.id), "active_only": True})).json()
    assert [p["id"] for p in got] == [general["id"]]
    assert (await owner_client.delete(f"{B}/principles/{general['id']}")).status_code == 204
    assert (await owner_client.delete(f"{B}/principles/{general['id']}")).status_code == 404
    cats = (await helper_client.get(f"{B}/categories")).json()
    assert any(c["slug"] == "nha-bep-test" for c in cats)


# ---- c6 ------------------------------------------------------------------------------------------------------------


async def test_taste_learns_from_decisions_and_owner_edits(owner_client: httpx.AsyncClient) -> None:
    a = await make_candidate("Giá phơi chữ X", stage=CandidateStage.TRIAL)
    b = await make_candidate("Bình nước", stage=CandidateStage.TRIAL)
    await _note(owner_client, a.id, "Inox chắc tay, không gỉ")
    d = (await _stage(owner_client, a.id, "selected")).json()["decision"]
    await owner_client.post(
        f"{B}/decisions/{d['id']}/approve", json={"reason_selected": ["Inox chắc tay, không gỉ."], "not_satisfied": []}
    )
    await _stage(owner_client, b.id, "rejected", reason="Rò nước ở nắp")

    profiles = (await owner_client.get(f"{B}/taste-profiles")).json()
    assert profiles[0]["pending_count"] == 2 and profiles[0]["summary"] is None
    # người nghe chạy lặp lại không sinh trùng
    async with SessionLocal() as s:
        await events.emit("candidate.rejected", {"candidate_id": str(b.id), "decision_id": "x"}, db=s)
        await s.commit()
    assert (await owner_client.get(f"{B}/taste-profiles")).json()[0]["pending_count"] == 2

    assert await enqueue("selection.retrain_taste") == 1
    p = (await owner_client.get(f"{B}/taste-profiles")).json()[0]
    assert p["pending_count"] == 0 and p["sample_count"] == 2 and p["version"] == 2
    assert "Rò nước" in [t["trait"] for t in p["dislikes"]] and p["likes"]
    assert "chọn" in p["summary"]
    assert await enqueue("selection.retrain_taste") == 0  # không có gì mới

    r = await owner_client.patch(
        f"/api/desk/selection/taste-profiles/{p['id']}",
        json={"summary": "Chị thích đồ inox chắc, ghét rò nước.", "dislikes": [{"trait": "Rò nước", "weight": -1}]},
    )
    assert r.status_code == 200 and r.json()["owner_edited"] and r.json()["dislikes"][0]["weight"] == -1
    r = await owner_client.post(f"{B}/taste-profiles/retrain", json={"all": True})
    assert r.status_code == 200
    async with SessionLocal() as s:
        prof = await s.scalar(select(TasteProfile).where(TasteProfile.category_id.is_(None)))
        assert prof.weights["Rò nước"] == -1  # giữ điều chị đã sửa
