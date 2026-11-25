"""Giọng với khách: người bán tự xưng «mình», gọi khách «bạn». «Chị» chỉ là cách gọi người bán trong nội bộ
(bàn làm việc), không bao giờ có trong câu chữ gửi tới khách: mẫu tin, câu trả lời mẫu, hàm giả của AI, lỗi API
của route `/api/store/**`."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app import ai
from app.ai.registry import FAKES
from app.core import errors
from app.modules.assistant.ai_tasks import AnswerIn, Fact
from app.modules.assistant.service import HANDOFF_TEXT, OFFLINE_TEXT
from app.modules.catalog.drops import reminder_text
from app.modules.content.fakes import GENERIC_Q
from app.modules.crm.ai_tasks import DropAnnouncementIn, DropItemFact, ReorderIn
from app.modules.crm.service import DEFAULT_INVITE, OPT_OUT_FOOTER
from app.modules.inbox.ai_tasks import DraftReplyIn, ProductFact
from app.modules.inbox.service import DEFAULT_ACK_TEXT
from app.modules.orders.notify import CARRIER_NAMES, DEFAULT_TEMPLATES, render
from app.modules.orders.refs import INBOUND_LABELS
from tests.catalog.factories import published_product

# «chị» đứng riêng (không phải một phần của từ khác như «chịu»)
CHI = re.compile(r"(?<!\w)chị(?!\w)", re.IGNORECASE)

# tác vụ AI sinh nội dung khách đọc hoặc nghe
CUSTOMER_TASKS = [
    "assistant.answer",
    "inbox.draft_reply",
    "orders.assess_return",
    "crm.draft_drop_announcement",
    "crm.draft_reorder",
    "catalog.write_product_page",
    "content.compose",
    "content.rewrite",
    "content.livestream",
    "selection.draft_reasons",
]


def no_chi(*texts: str) -> None:
    for t in texts:
        assert not CHI.search(t), f"gọi người bán là «chị» trong câu gửi khách: {t!r}"


def test_message_templates_and_labels():
    sample = {k: "x" for k in ("ten", "ma_don", "mon", "link", "hang", "noi_dung", "ket_qua")}
    no_chi(*DEFAULT_TEMPLATES.values(), *(render(t, sample) for t in DEFAULT_TEMPLATES.values()))
    no_chi(*CARRIER_NAMES.values(), *INBOUND_LABELS.values())
    no_chi(HANDOFF_TEXT, OFFLINE_TEXT, DEFAULT_ACK_TEXT, DEFAULT_INVITE, OPT_OUT_FOOTER)
    drop = SimpleNamespace(
        code="D2", title="Đồ bếp Nhật", slug="do-bep-nhat", closes_at=datetime(2026, 12, 1, tzinfo=UTC)
    )
    text = reminder_text(drop)  # type: ignore[arg-type]
    no_chi(text)
    assert "mua chung" in text


def test_store_error_messages_use_customer_voice():
    no_chi(*errors._STORE_MESSAGES.values())


@pytest.mark.parametrize("name", CUSTOMER_TASKS)
def test_customer_facing_prompts_forbid_chi(name):
    system = ai.TASKS[name].system
    assert "«mình»" in system, name
    assert "không bao giờ gọi người" in system.lower(), name


def test_fakes_never_call_the_seller_chi():
    fakes = FAKES
    answer = fakes["assistant.answer"]
    no_chi(answer(AnswerIn(question="Có bảo hành không?", facts=[])).answer)
    known = answer(AnswerIn(question="dung tích", facts=[Fact(ref="r", label="Dung tích", text="480 ml")]))
    no_chi(known.answer)

    product = ProductFact(id="p1", name="Bình giữ nhiệt", price_vnd=245000, in_stock=3)
    for message in ("Hàng bị lỗi rồi, đổi giúp mình", "Còn hàng không?", "Cảm ơn nhé", "Bé dùng có an toàn không?"):
        out = fakes["inbox.draft_reply"](
            DraftReplyIn(
                channel="facebook", kind="direct_message", customer_name="Hà", message=message, products=[product]
            )
        )
        no_chi(out.reply, *(o.reply for o in out.options))

    drop = fakes["crm.draft_drop_announcement"](
        DropAnnouncementIn(drop_title="Đợt 2", closes_at=None, expected_arrival=None, link="http://x",
                           audience_size=3, items=[DropItemFact(name="Bình", price_vnd=245000)])
    )  # fmt: skip
    reorder = fakes["crm.draft_reorder"](
        ReorderIn(customer_name="Lan", product_name="Túi lọc", bought_on="2026-10-01", quantity=1, cycle_days=30)
    )
    no_chi(drop.body, reorder.body, *(q for q, _ in GENERIC_Q))


async def test_assistant_answers_on_store(db, client):
    p = await published_product(db)
    await db.commit()
    for q in ("Có giữ lạnh được không?", "Có bảo hành không?"):
        r = await client.post("/api/store/assistant/ask", json={"question": q, "product_slug": p.slug})
        assert r.status_code == 200, r.text
        no_chi(r.json()["answer"]["content"])


async def test_store_validation_error_in_customer_voice(client):
    r = await client.post("/api/store/assistant/ask", json={})
    assert r.status_code == 422
    no_chi(r.json()["detail"])
    assert "bạn" in r.json()["detail"]
