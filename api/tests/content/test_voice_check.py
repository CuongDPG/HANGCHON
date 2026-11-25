"""f5 soát lời: mục «Xưng hô với khách» — bài đăng không gọi người bán là «chị» (lời khách trích trong ngoặc thì được,
từ «chịu» không tính). Chưa đạt thì chặn duyệt tới khi sửa, kèm gợi ý câu đã sửa."""

from __future__ import annotations

from app.core.enums import Channel
from app.modules.content.checks import build_findings, can_approve, status_of


def _findings(body: str) -> dict[str, dict]:
    items = build_findings(channel=Channel.FACEBOOK, title=None, body=body, hashtags=[], script=[], product=None,
                           drop=None, ai_generated=True, ai=None)  # fmt: skip
    return {f["key"]: f for f in items}


def test_voice_finding_flags_chi_with_suggestion():
    f = _findings("Chị đã dùng thử 3 tuần, nắp chịu nhiệt. " * 4)["voice"]
    assert f["label"] == "Xưng hô với khách" and not f["ok"]
    assert "«Chị đã dùng thử 3 tuần, nắp chịu nhiệt.»" in f["detail"]
    assert f["suggestion"].startswith("Đổi thành «Mình đã dùng thử 3 tuần, nắp chịu nhiệt.»")
    items = list(_findings("Chị đã dùng thử 3 tuần.").values())
    assert not can_approve(status_of(items))


def test_voice_finding_allows_quoted_review_and_chiu():
    body = "Một khách nhắn mình: «Chị ơi bình giữ nóng tới chiều luôn». Nắp chịu nhiệt, bạn yên tâm. " * 3
    f = _findings(body)["voice"]
    assert f["ok"] and f["suggestion"] is None and f["detail"] == "Xưng «mình», gọi khách «bạn»."


async def test_draft_with_chi_is_blocked_until_fixed(product_factory, owner_client):
    p = await product_factory()
    detail = (await owner_client.post(f"/api/desk/content/studio/product/{p.id}/compose", json={})).json()
    fb = next(x for x in detail["drafts"] if x["channel"] == "facebook")
    url = f"/api/desk/content/drafts/{fb['id']}"
    r = await owner_client.patch(url, json={"body": fb["body"] + "\n\nChị dùng mỗi sáng nên rất ưng."})
    d = r.json()
    voice = next(f for f in d["check_findings"] if f["key"] == "voice")
    assert not voice["ok"] and "Mình dùng mỗi sáng nên rất ưng." in voice["suggestion"]
    assert d["check_status"] == "failed" and not d["can_approve"]
    assert (await owner_client.post(f"{url}/approve", json={})).status_code == 409

    r = await owner_client.patch(url, json={"body": fb["body"] + "\n\nMình dùng mỗi sáng nên rất ưng."})
    d = r.json()
    assert next(f for f in d["check_findings"] if f["key"] == "voice")["ok"] and d["can_approve"]
    assert (await owner_client.post(f"{url}/approve", json={})).status_code == 200
