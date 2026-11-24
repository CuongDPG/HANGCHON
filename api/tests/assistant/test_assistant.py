"""e7 trợ lý hỏi đáp: chỉ trả lời từ hồ sơ, có dẫn nguồn; không biết thì chuyển chị (việc chờ); giới hạn tần suất."""

from __future__ import annotations

from sqlalchemy import select

from app import ai
from app.modules.assistant.models import AssistantConversation, AssistantMessage, AssistantRole, ConversationStatus
from app.modules.assistant.service import HANDOFF_TEXT, OFFLINE_TEXT, PER_MINUTE
from app.modules.control.models import ApprovalItem, ApprovalStatus
from tests.catalog.factories import published_product


async def test_answers_from_dossier_with_citation(db, client):
    p = await published_product(db)
    await db.commit()
    r = await client.post(
        "/api/store/assistant/ask", json={"question": "Có giữ lạnh được không?", "product_slug": p.slug}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handed_off"] is False
    ans = body["answer"]
    assert "12 tiếng" in ans["content"]
    assert ans["citations"][0]["label"].startswith("Hỏi–đáp") and ans["citations"][0]["ref"].endswith(":faq:0")
    assert "hc_asst" in r.cookies
    conv_id = body["conversation"]["id"]
    r = await client.post(
        "/api/store/assistant/ask", json={"question": "Dung tích bao nhiêu?", "conversation_id": conv_id}
    )
    assert r.json()["conversation"]["id"] == conv_id
    assert [m["role"] for m in r.json()["conversation"]["messages"]] == ["user", "assistant", "user", "assistant"]
    assert "480 ml" in r.json()["answer"]["content"]
    conv = (await db.execute(select(AssistantConversation))).scalar_one()
    assert conv.product_id == p.id and conv.message_count == 4 and conv.ip_hash


async def test_unknown_hands_off_and_owner_reply_reaches_customer(db, client, owner_client):
    p = await published_product(db)
    await db.commit()
    r = await client.post(
        "/api/store/assistant/ask", json={"question": "Vỡ nắp thì mua lẻ được không?", "product_slug": p.slug}
    )
    body = r.json()
    assert body["handed_off"] is True and body["answer"]["content"] == HANDOFF_TEXT
    assert body["answer"]["unknown"] is True and body["answer"]["citations"] == []
    assert body["conversation"]["status"] == "handed_off"
    conv_id = body["conversation"]["id"]
    r = await client.post(f"/api/store/assistant/conversations/{conv_id}/contact", json={"contact": "Zalo 0000000000"})
    assert r.json()["contact_saved"] is True
    item = (
        await db.execute(select(ApprovalItem).where(ApprovalItem.action == "assistant.forward_to_owner"))
    ).scalar_one()
    assert item.status == ApprovalStatus.PENDING and item.preview["question"].startswith("Vỡ nắp")
    # duyệt mà chưa gõ câu trả lời → lỗi, duyệt lại được
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve", json={})
    assert r.json()["status"] == "failed"
    r = await owner_client.post(f"/api/desk/control/approvals/{item.id}/approve",
                                json={"payload": {"reply": "Có bán lẻ nắp, bạn nhắn chị nhé."}})  # fmt: skip
    assert r.json()["status"] == "approved", r.text
    conv = (await client.get(f"/api/store/assistant/conversations/{conv_id}")).json()
    assert conv["messages"][-1]["role"] == "owner" and conv["status"] == "open"
    from app.integrations import get_driver

    assert get_driver("notify").outbox[-1].to == "Zalo 0000000000"


async def test_forward_action_is_locked_ask(owner_client):
    rows = (await owner_client.get("/api/desk/control/autonomy")).json()
    row = next(
        x for x in (rows if isinstance(rows, list) else rows["items"]) if x["action"] == "assistant.forward_to_owner"
    )
    assert row["locked"] is True
    r = await owner_client.patch("/api/desk/control/autonomy/assistant.forward_to_owner", json={"level": "auto"})
    assert r.status_code in (400, 403, 409, 422)


async def test_citation_outside_dossier_is_treated_as_unknown(db, client, fake_ai):
    fake_ai["assistant.answer"] = lambda inp: {
        "answer": "Bình này chữa được đau dạ dày.", "citations": ["internet:1"], "unknown": False, "confidence": 0.9
    }  # fmt: skip
    p = await published_product(db)
    await db.commit()
    r = await client.post(
        "/api/store/assistant/ask", json={"question": "Bình có tốt cho dạ dày?", "product_slug": p.slug}
    )
    assert r.json()["handed_off"] is True and "dạ dày" not in r.json()["answer"]["content"]


async def test_ai_unavailable_still_hands_off(db, client, fake_ai):
    def boom(inp):
        raise ai.AIUnavailable("mất mạng")

    fake_ai["assistant.answer"] = boom
    p = await published_product(db)
    await db.commit()
    r = await client.post("/api/store/assistant/ask", json={"question": "Bao giờ có hàng?", "product_slug": p.slug})
    assert r.status_code == 200 and r.json()["answer"]["content"] == OFFLINE_TEXT


async def test_general_question_uses_shelf(db, client):
    await published_product(db, name="Khăn tắm cho bé")
    await db.commit()
    r = await client.post("/api/store/assistant/ask", json={"question": "Có khăn tắm cho bé không?"})
    assert r.json()["handed_off"] is False and "Khăn tắm" in r.json()["answer"]["content"]


async def test_rate_limit_and_validation(db, client):
    p = await published_product(db)
    await db.commit()
    assert (await client.post("/api/store/assistant/ask", json={"question": " "})).status_code == 400
    for _ in range(PER_MINUTE - 0):
        await client.post("/api/store/assistant/ask", json={"question": "Dung tích?", "product_slug": p.slug})
    r = await client.post("/api/store/assistant/ask", json={"question": "Dung tích?", "product_slug": p.slug})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"
    n = len((await db.execute(select(AssistantMessage).where(AssistantMessage.role == AssistantRole.USER))).all())
    assert n == PER_MINUTE


async def test_conversation_belongs_to_session(db, client):
    import httpx

    from app.main import app as fastapi_app

    p = await published_product(db)
    await db.commit()
    r = await client.post("/api/store/assistant/ask", json={"question": "Dung tích?", "product_slug": p.slug})
    conv_id = r.json()["conversation"]["id"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test") as other:
        assert (await other.get(f"/api/store/assistant/conversations/{conv_id}")).status_code == 404
    r = await client.post(f"/api/store/assistant/conversations/{conv_id}/feedback",
                          json={"message_id": r.json()["answer"]["id"], "value": "up"})  # fmt: skip
    assert r.json()["messages"][1]["feedback"] == "up"
    assert ConversationStatus.OPEN.value == r.json()["status"]
