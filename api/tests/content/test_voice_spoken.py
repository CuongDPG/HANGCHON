"""f2 Giọng của chị: lời chị nói (chép từ giọng nói ở trình duyệt) là một nguồn học giọng, lưu kèm loại «voice»."""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.content.models import VoiceProfile

SPOKEN = "cả nhà ơi mình mới thử cái hộp cơm này mình thấy nắp khít lắm cả nhà ạ mang đi làm không đổ"


async def test_learn_from_spoken_only(owner_client, fake_ai):
    seen = []
    original = fake_ai["content.learn_voice"]

    def spy(inp):  # type: ignore[no-untyped-def]
        seen.append(inp)
        return original(inp)

    fake_ai["content.learn_voice"] = spy
    r = await owner_client.post("/api/desk/content/voice/learn", json={"samples": [], "spoken": ["  "]})
    assert r.status_code == 400  # chỉ có khoảng trắng → chưa có gì để học

    r = await owner_client.post("/api/desk/content/voice/learn", json={"spoken": [SPOKEN]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"
    v = r.json()["voice"]
    assert "mình" in v["pronouns"] and "cả nhà" in v["pronouns"] and v["samples_count"] == 1
    assert seen[-1].spoken == [SPOKEN] and seen[-1].samples == []
    async with SessionLocal() as db:
        vp = await db.scalar(select(VoiceProfile))
    assert vp.sample_sources[-1]["kind"] == "voice" and vp.sample_sources[-1]["text"] == SPOKEN


async def test_spoken_limit(owner_client):
    r = await owner_client.post("/api/desk/content/voice/learn", json={"spoken": ["một câu"] * 11})
    assert r.status_code == 422
