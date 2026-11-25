"""Chốt chặn chữ «chị» trước khi đăng ra khách: trang sản phẩm (tên, mô tả, hỏi đáp, thông số) không được gọi người
bán là «chị». Lời trích trong ngoặc (lời khách) và từ như «chịu» không tính."""

from __future__ import annotations

from sqlalchemy import select

from app import control
from app.core import events
from app.core.jobs import job_context
from app.modules.catalog.jobs import write_product_page
from app.modules.catalog.models import Product, ProductStatus
from app.modules.catalog.textutil import seller_address_issues
from app.modules.control.models import ApprovalItem, ApprovalStatus, AutonomyLevel
from tests.catalog.factories import selected_candidate


def test_detects_seller_chi_and_suggests_fix():
    hits = seller_address_issues("Chị đã dùng thử bao lâu?")
    assert hits == [{"quote": "Chị đã dùng thử bao lâu?", "suggestion": "Mình đã dùng thử bao lâu?"}]
    assert seller_address_issues("Mình thử 3 tuần. Chị thấy nắp chặt, chị rất ưng.")[0] == {
        "quote": "Chị thấy nắp chặt, chị rất ưng.",
        "suggestion": "Mình thấy nắp chặt, mình rất ưng.",
    }
    assert seller_address_issues("Anh chị đặt trước 20h nhé!")[0]["suggestion"] == "Bạn đặt trước 20h nhé!"
    assert seller_address_issues("Hợp cho chị em nội trợ.")[0]["suggestion"] == "Hợp cho bạn nội trợ."


def test_ignores_chiu_and_quoted_customer_words():
    assert seller_address_issues("Nắp chịu nhiệt 100 độ, chịu va đập.") == []
    assert seller_address_issues("Khách nhận xét: «Chị bán hàng có tâm, giao nhanh».") == []
    assert seller_address_issues('Một bạn viết: "chị ơi bình giữ nóng tốt".') == []
    assert seller_address_issues(None) == [] and seller_address_issues("") == []
    # ngoài ngoặc vẫn bắt, trong ngoặc giữ nguyên lời khách
    hit = seller_address_issues("Chị đọc lời khách «chị ơi ưng lắm» mà vui.")[0]
    assert hit["suggestion"] == "Mình đọc lời khách «chị ơi ưng lắm» mà vui."


async def _pending_product(db, owner_client) -> Product:
    data = await selected_candidate(db)
    await events.emit("candidate.selected", {"candidate_id": str(data["candidate"].id),
                                             "decision_id": str(data["decision"].id)}, db=db)  # fmt: skip
    await db.commit()
    p = (await db.execute(select(Product).where(Product.candidate_id == data["candidate"].id))).scalar_one()
    await write_product_page(job_context(), str(p.id))
    return p


async def test_publish_blocked_until_chi_removed(db, owner_client):
    p = await _pending_product(db, owner_client)
    url = f"/api/desk/catalog/products/{p.id}"
    faq = [{"q": "Chị đã dùng thử bao lâu?", "a": "Mình dùng 3 tuần, nắp chịu nhiệt tốt.", "source": "Ghi chú"}]
    r = await owner_client.patch(url, json={"price_vnd": 385000, "faq": faq})
    assert r.status_code == 200
    issues = r.json()["voice_issues"]
    assert issues == [{"path": "faq.0.q", "field": "Hỏi đáp 1 (câu hỏi)", "quote": "Chị đã dùng thử bao lâu?",
                       "suggestion": "Mình đã dùng thử bao lâu?"}]  # fmt: skip

    r = await owner_client.post(f"{url}/publish")
    assert r.status_code == 400 and r.json()["code"] == "seller_address"
    assert "Mình đã dùng thử bao lâu?" in r.json()["detail"]
    await db.refresh(p)
    assert p.status == ProductStatus.PENDING_REVIEW
    item = await db.get(ApprovalItem, p.approval_item_id)
    assert item.status in (ApprovalStatus.PENDING, ApprovalStatus.FAILED)

    faq[0]["q"] = "Đã dùng thử bao lâu?"
    assert (await owner_client.patch(url, json={"faq": faq})).json()["voice_issues"] == []
    r = await owner_client.post(f"{url}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"


async def test_approval_queue_warns_and_auto_level_does_not_publish(db, fake_ai):
    from app.ai.registry import FAKES
    from app.modules.catalog.ai_tasks import WritePageOut

    original = FAKES["catalog.write_product_page"]

    def with_chi(inp):  # type: ignore[no-untyped-def] — hàm giả gốc + một câu gọi người bán là «chị»
        out = original(inp)
        out = out if isinstance(out, WritePageOut) else WritePageOut.model_validate(out)
        out.description = (out.description or "") + "\nChị dùng mỗi sáng, rửa nhanh."
        return out

    fake_ai["catalog.write_product_page"] = with_chi
    await control.set_level(db, "catalog.publish_product", AutonomyLevel.AUTO, None)
    data = await selected_candidate(db)
    await events.emit("candidate.selected", {"candidate_id": str(data["candidate"].id),
                                             "decision_id": str(data["decision"].id)}, db=db)  # fmt: skip
    p = (await db.execute(select(Product).where(Product.candidate_id == data["candidate"].id))).scalar_one()
    p.price_vnd = 200000
    await db.commit()
    # mức «AI tự làm» cũng không đăng được trang còn chữ «chị»
    assert await write_product_page(job_context(), str(p.id)) == "failed"
    await db.refresh(p)
    assert p.status != ProductStatus.PUBLISHED

    await control.set_level(db, "catalog.publish_product", AutonomyLevel.ASK, None)
    await db.commit()
    assert await write_product_page(job_context(), str(p.id)) == "pending"
    await db.refresh(p)
    item = await db.get(ApprovalItem, p.approval_item_id)
    pron = item.preview["checks"]["pronouns"]
    assert pron == ["Mô tả: «Chị dùng mỗi sáng, rửa nhanh.» → gợi ý «Mình dùng mỗi sáng, rửa nhanh.»"]
    assert "cần chị xem kỹ" in (item.summary or "")
