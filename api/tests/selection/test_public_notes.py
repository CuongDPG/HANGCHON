"""«Ghi chú dùng thử» trên website (27/11): chị tích từng ghi chú; website chỉ thấy ghi chú đã tích (bản lời cho website,
ảnh chỉ khi tích kèm); ghi chú của người dùng thử không bao giờ ra website."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.enums import SourcePlatform
from app.core.timeutil import now_utc
from app.modules.catalog.models import Product, ProductStatus, SaleMode
from app.modules.selection.models import NoteAuthor, ProcessingStatus, TrialNote, TrialNoteKind
from app.modules.sourcing.models import Candidate, CandidateStage
from tests.catalog.factories import jpeg

B = "/api/desk/selection"


async def _setup(db):
    cand = Candidate(
        title_vi="Bình giữ nhiệt 480 ml", source_platform=SourcePlatform.RAKUTEN, stage=CandidateStage.SELECTED
    )
    db.add(cand)
    await db.flush()
    p = Product(
        slug=f"sp-{uuid.uuid4().hex[:8]}", name="Bình giữ nhiệt 480 ml", price_vnd=385_000, sale_mode=SaleMode.IN_STOCK,
        status=ProductStatus.PUBLISHED, sku=f"SKU-{uuid.uuid4().hex[:6]}", candidate_id=cand.id,
    )  # fmt: skip
    tester = TrialNote(
        candidate_id=cand.id, kind=TrialNoteKind.TEXT, author=NoteAuthor.TESTER, author_name="Lan Ví Dụ",
        text="Nắp hơi chặt (4/5)", recorded_at=now_utc(), processing_status=ProcessingStatus.DONE,
    )  # fmt: skip
    db.add_all([p, tester])
    await db.commit()
    return cand, p, tester


async def test_only_ticked_owner_notes_reach_product_page(owner_client, client, db):
    cand, p, tester = await _setup(db)
    r = await owner_client.post(
        f"{B}/candidates/{cand.id}/notes",
        data={"text": "Chị đo: 7h sáng tới 5h chiều còn ấm."},
        files={"photos": ("a.jpg", jpeg(), "image/jpeg")},
    )
    note = r.json()
    r = await owner_client.post(f"{B}/candidates/{cand.id}/notes", data={"text": "Rửa nhanh, không ám mùi."})
    hidden = r.json()
    assert note["is_public"] is False and note["public_warnings"] == []
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    assert pub["trial_notes"] == []

    # tích «Đưa lên website»: bản cho website mặc định là lời gốc đổi «chị» → «mình»
    r = await owner_client.patch(f"{B}/notes/{note['id']}", json={"is_public": True})
    assert r.status_code == 200, r.text
    assert r.json()["public_text"] == "Mình đo: 7h sáng tới 5h chiều còn ấm." and r.json()["public_photo_urls"] == []
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    assert pub["trial_notes"] == [{"text": "Mình đo: 7h sáng tới 5h chiều còn ấm.", "day": None, "photos": []}]

    # chị sửa lời bản website + tích kèm ảnh: lời gốc giữ nguyên, ảnh là bản sao công khai
    r = await owner_client.patch(
        f"{B}/notes/{note['id']}", json={"public_text": "Giữ ấm từ sáng tới chiều.", "public_photos": True}
    )
    body = r.json()
    assert body["text"].startswith("Chị đo") and body["public_text"] == "Giữ ấm từ sáng tới chiều."
    assert len(body["public_photo_urls"]) == 1 and "public/trial-notes/" in body["public_photo_urls"][0]
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    (tn,) = pub["trial_notes"]
    assert tn["text"] == "Giữ ấm từ sáng tới chiều." and "public/trial-notes/" in tn["photos"][0]["src"]
    assert "private" not in str(pub["trial_notes"]) and "Nắp hơi chặt" not in str(pub)
    assert hidden["text"] not in str(pub["trial_notes"])

    # bỏ tích: ảnh công khai bị gỡ, website hết ghi chú
    r = await owner_client.patch(f"{B}/notes/{note['id']}", json={"is_public": False})
    assert r.json()["public_photo_urls"] == []
    assert (await client.get(f"/api/store/catalog/products/{p.slug}")).json()["trial_notes"] == []

    # ghi chú của người dùng thử không đưa lên được
    r = await owner_client.patch(f"{B}/notes/{tester.id}", json={"is_public": True})
    assert r.status_code == 400 and r.json()["code"] == "tester_note_private"


async def test_public_text_is_checked_like_ad_copy(owner_client, db):
    cand, _, _ = await _setup(db)
    r = await owner_client.post(f"{B}/candidates/{cand.id}/notes", data={"text": "Giữ nóng lâu."})
    nid = r.json()["id"]
    r = await owner_client.patch(
        f"{B}/notes/{nid}",
        json={"is_public": True, "public_text": "Tốt nhất trong 6 mẫu mình thử, hơn hẳn mẫu bị loại. Chị thấy ưng."},
    )
    warnings = " | ".join(r.json()["public_warnings"])
    assert "tốt nhất" in warnings  # nói quá
    assert "quá trình chọn" in warnings  # kể quá trình chọn / mẫu bị loại
    assert "so sánh" in warnings  # so với món khác
    assert "«chị»" in warnings  # gọi người bán là chị
    # chỉ báo, không chặn: vẫn lưu
    assert r.json()["is_public"] is True


async def test_content_facts_use_ticked_notes_and_never_tester_feedback(owner_client, db):
    from app.modules.content import facts

    cand, p, _ = await _setup(db)
    r = await owner_client.post(f"{B}/candidates/{cand.id}/notes", data={"text": "Rửa nhanh."})
    await owner_client.patch(f"{B}/notes/{r.json()['id']}", json={"is_public": True})
    p = (await db.execute(select(Product).where(Product.id == p.id))).scalar_one()
    await db.refresh(p, ["images"])
    pf = await facts.product_facts_full(db, p)
    assert pf.public_trial_notes == ["Rửa nhanh."]
    assert not any("Nắp hơi chặt" in t for t in pf.trial_notes)  # cảm nhận người dùng thử không vào bài cho khách
