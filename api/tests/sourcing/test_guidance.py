"""c5 + c6 tác dụng ngược lại săn hàng: nguyên tắc hạ hạng (không xoá), gu cộng/trừ điểm, giải thích cho chị.
Kèm b7 băm ảnh theo hình và hoàn tác xu hướng / nhu cầu khách."""

from __future__ import annotations

import io
import uuid
from decimal import Decimal

from PIL import Image, ImageDraw
from sqlalchemy import func, select

from app.core.enums import Language, SourcePlatform
from app.integrations.sources import SourceItem
from app.modules.selection.models import PrincipleKind, SelectionPrinciple, TasteProfile
from app.modules.sourcing import guidance, imagehash, service
from app.modules.sourcing.ai_io import RankItemOut
from app.modules.sourcing.models import (
    CandidateOrigin,
    DemandMention,
    DemandSignal,
    DemandSource,
    SourcingBrief,
    TrendSignal,
)
from tests.sourcing.util import API, scanned_brief

RATES = {"CNY": 3500}


def test_alternatives_and_words():
    assert guidance.alternatives("Không nhập đồ có pin hoặc sạc điện") == [["pin"], ["sac", "dien"]]
    assert guidance.alternatives("Tránh hàng có mùi nhựa") == [["mui", "nhua"]]
    assert guidance.trait_tokens("Không bền") == ["khong ben"]
    assert guidance.trait_tokens("Không pin, cắm USB là dùng") == ["khong pin", "cam", "usb"]


def test_negated_trait_does_not_match_the_opposite():
    g = guidance.Guidance(traits=[guidance.Trait("Không bền", -0.7, guidance.trait_tokens("Không bền"))])
    assert guidance.assess(g, "Người mua khen bền, chắc tay")[0] == 0
    assert guidance.assess(g, "Nhiều người chê không bền")[0] == -7


def _item(ext: str, title: str) -> SourceItem:
    return SourceItem(platform=SourcePlatform.TAOBAO, external_id=ext, url=f"https://x/{ext}", title=title,
                      language=Language.ZH, price_amount=Decimal("20"), currency="CNY", seller_name=f"shop{ext}")  # fmt: skip


def _ranked(ext: str, title_vi: str, score: int) -> RankItemOut:
    return RankItemOut(ref=f"taobao:{ext}", title_vi=title_vi, keep=True, score=score, reason="Đáng xem vì khớp đề.",
                       same_model_key=ext)  # fmt: skip


def test_build_results_applies_principles_and_taste():
    brief = SourcingBrief(id=uuid.uuid4(), title="Giá phơi", filters={})
    items = [_item("a", "A"), _item("b", "B"), _item("c", "C"), _item("d", "D")]
    ranked = {
        "taobao:a": _ranked("a", "Giá phơi cánh bướm có bánh xe", 90),
        "taobao:b": _ranked("b", "Giá phơi treo lan can", 70),
        "taobao:c": _ranked("c", "Giá phơi chân chữ A nhôm", 80),
        "taobao:d": _ranked("d", "Giá phơi gấp 3 tầng", 75),
    }
    g = guidance.Guidance(
        rules=[
            guidance.Rule(PrincipleKind.MUST_NOT, "Không nhập loại có bánh xe", [["banh", "xe"]]),
            guidance.Rule(PrincipleKind.AVOID, "Tránh hàng nhôm", [["nhom"]]),
        ],
        traits=[
            guidance.Trait(
                "Treo lan can, không chiếm sàn", 0.8, guidance.trait_tokens("Treo lan can, không chiếm sàn")
            ),
            guidance.Trait("gấp 3 tầng", -0.5, guidance.trait_tokens("gấp 3 tầng")),
        ],
    )
    out = service.build_results(brief, items, ranked, RATES, CandidateOrigin.BRIEF_SCAN, g)
    by = {c["source_external_id"]: c for c in out}
    assert len(out) == 4  # trái nguyên tắc vẫn giữ lại, không xoá âm thầm
    a = by["a"]["raw"]["guidance"]
    assert a["violates"] and a["base_score"] == 90 and by["a"]["ai_score"] == 60
    assert a["notes"][0]["text"] == "Trái nguyên tắc: Không nhập loại có bánh xe"
    assert by["c"]["ai_score"] == 70 and not by["c"]["raw"]["guidance"]["violates"]  # «tránh»: hạ 10, không gắn cờ
    assert by["b"]["ai_score"] == 70 + 8  # ≥ 2/3 số chữ của đặc điểm có trong tên → +0.8 × 10
    assert by["d"]["ai_score"] == 75 - 5
    assert any(n["text"].startswith("Chị hay loại: gấp 3 tầng") for n in by["d"]["raw"]["guidance"]["notes"])
    # xếp: món trái nguyên tắc «không chấp nhận» xuống cuối dù điểm gốc cao nhất
    assert [c["source_external_id"] for c in out] == ["b", "c", "d", "a"]
    # không có nguyên tắc/gu → không đụng gì
    plain = service.build_results(brief, items, ranked, RATES, CandidateOrigin.BRIEF_SCAN, guidance.Guidance())
    assert all("guidance" not in c["raw"] for c in plain) and plain[0]["ai_score"] == 90


def test_taste_cap():
    g = guidance.Guidance(
        traits=[guidance.Trait(t, 1.0, guidance.trait_tokens(t)) for t in ("inox", "gấp", "ban công")]
    )
    delta, violates, notes = guidance.assess(g, "Giá phơi inox gấp gọn ban công")
    assert delta == guidance.TASTE_CAP and not violates
    assert notes[-1]["text"].startswith("Gu chỉnh tối đa")


async def test_scan_uses_principles_and_taste_from_selection(db, owner_client):
    db.add(SelectionPrinciple(kind=PrincipleKind.MUST_NOT, text="Không nhập giá phơi"))
    db.add(SelectionPrinciple(kind=PrincipleKind.MUST_NOT, text="Không bán hàng có pin", is_active=False))
    db.add(TasteProfile(category_id=None, weights={"Treo lan can": 0.9, "nhỏ": 0.1}))
    await db.commit()
    _, items = await scanned_brief(owner_client)
    assert items, "trái nguyên tắc vẫn hiện, không bị xoá"
    for c in items:
        g = c["guidance"]
        assert g and g["violates"] and g["notes"][0] == {
            "kind": "principle", "delta": -30, "text": "Trái nguyên tắc: Không nhập giá phơi"
        }  # fmt: skip
        assert c["ai_score"] == max(0, g["base_score"] + g["delta"])
        assert "pin" not in str(g)  # nguyên tắc đã tắt không áp
    lan_can = [c for c in items if "lan can" in c["title_vi"].lower()]
    for c in lan_can:
        assert any(n["text"] == "Hợp gu chị: Treo lan can" and n["delta"] == 9 for n in c["guidance"]["notes"])
    detail = (await owner_client.get(f"{API}/candidates/{items[0]['id']}")).json()
    assert detail["guidance"]["violates"]


# ---- b7: băm ảnh theo hình -----------------------------------------------------------------------------------------


def _photo(shift: int = 0, *, size: int = 400, fmt: str = "PNG", flip: bool = False) -> bytes:
    img = Image.new("RGB", (400, 400), (240, 240, 235))
    d = ImageDraw.Draw(img)
    d.rectangle((60 + shift, 80, 260 + shift, 330), fill=(40, 60, 140))
    d.ellipse((200, 40, 360, 200), fill=(200, 90, 60))
    if flip:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    img = img.resize((size, size))
    buf = io.BytesIO()
    img.save(buf, fmt, quality=60) if fmt == "JPEG" else img.save(buf, fmt)
    return buf.getvalue()


def test_dhash_same_picture_survives_resize_and_recompress():
    a = imagehash.dhash(_photo())
    b = imagehash.dhash(_photo(size=180, fmt="JPEG"))  # cùng ảnh, nhỏ hơn, nén JPEG
    c = imagehash.dhash(_photo(flip=True))  # ảnh khác
    assert a and b and c and len(a) == 16
    assert imagehash.same_image(a, b)
    assert not imagehash.same_image(a, c)
    assert imagehash.dhash(b"not an image") is None


async def test_attach_hashes_on_scan(owner_client, monkeypatch):
    calls: list[str] = []

    async def fake_hash(urls):
        calls.extend(urls)
        return {u: "0f0f0f0f0f0f0f0f" for u in urls}

    monkeypatch.setattr(service, "image_hashing_enabled", lambda: True)
    monkeypatch.setattr(imagehash, "hash_urls", fake_hash)
    _, items = await scanned_brief(owner_client)
    detail = (await owner_client.get(f"{API}/candidates/{items[0]['id']}")).json()
    assert detail["image_hash"] == "0f0f0f0f0f0f0f0f"
    assert all(o.get("image_hash") for o in detail["raw"]["offers"] if o.get("image_url"))
    assert calls


async def test_hashing_off_for_simulated_data():
    assert not service.image_hashing_enabled()  # test + driver mock + AI fake: không tải ảnh qua mạng


async def test_fetch_image_refuses_private_hosts():
    import httpx

    async with httpx.AsyncClient() as client:
        assert await imagehash.fetch_image("http://127.0.0.1/a.png", client) is None
        assert await imagehash.fetch_image("file:///etc/passwd", client) is None


# ---- hoàn tác xu hướng (a5) và nhu cầu khách (a6) ------------------------------------------------------------------


async def _last_activity(client, action: str) -> dict:
    acts = (await client.get("/api/desk/control/activity", params={"action": action})).json()["items"]
    assert acts, action
    return acts[0]


async def test_undo_trends(owner_client, db):
    await owner_client.post(f"{API}/trends/refresh")
    total = (await owner_client.get(f"{API}/trends")).json()["total"]
    assert total
    first = await _last_activity(owner_client, "sourcing.save_trends")
    assert first["undoable"]
    keep = (await owner_client.get(f"{API}/trends")).json()["items"][0]
    await owner_client.post(f"{API}/trends/{keep['id']}/brief")  # chị đã mở đề từ tín hiệu này → không xoá
    r = await owner_client.post(f"/api/desk/control/activity/{first['id']}/undo")
    assert r.status_code == 200, r.text
    left = (await db.execute(select(TrendSignal))).scalars().all()
    assert [str(t.id) for t in left] == [keep["id"]]


async def test_undo_trends_restores_updated_rows(owner_client, db):
    await owner_client.post(f"{API}/trends/refresh")
    row = (await db.execute(select(TrendSignal).limit(1))).scalar_one()
    row.reason = "Lý do cũ"
    await db.commit()
    await owner_client.post(f"{API}/trends/refresh")  # cùng ngày → cập nhật tín hiệu đã có
    act = await _last_activity(owner_client, "sourcing.save_trends")
    r = await owner_client.post(f"/api/desk/control/activity/{act['id']}/undo")
    assert r.status_code == 200, r.text
    await db.refresh(row)
    assert row.reason == "Lý do cũ"
    assert (await db.execute(select(func.count()).select_from(TrendSignal))).scalar_one() > 0


async def test_undo_demand(owner_client, db):
    payload = {"key": "gia-phoi", "title": "Giá phơi", "detail": None, "text": "Có giá phơi không shop",
               "source": DemandSource.COMMENT.value, "source_type": "messages", "channel": None, "customer_id": None,
               "find_request_id": None}  # fmt: skip
    from app import control

    out1 = await control.propose(
        "sourcing.record_demand", "Ghi nhu cầu", {**payload, "source_id": str(uuid.uuid4())}, db=db
    )
    out2 = await control.propose(
        "sourcing.record_demand", "Ghi nhu cầu", {**payload, "source_id": str(uuid.uuid4())}, db=db
    )
    await db.commit()
    sig = (await db.execute(select(DemandSignal))).scalar_one()
    assert sig.ask_count == 2
    r = await owner_client.post(f"/api/desk/control/activity/{out2.activity_id}/undo")
    assert r.status_code == 200, r.text
    await db.refresh(sig)
    assert sig.ask_count == 1
    r = await owner_client.post(f"/api/desk/control/activity/{out1.activity_id}/undo")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert (await db.execute(select(func.count()).select_from(DemandSignal))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(DemandMention))).scalar_one() == 0
