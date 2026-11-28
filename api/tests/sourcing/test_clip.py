"""«Gửi sang Hàng Chọn»: trang sản phẩm chị mở trên trình duyệt → ứng viên (mới hoặc cập nhật món cùng sàn + mã món).
HTTP tải ảnh luôn giả (httpx.MockTransport)."""

from __future__ import annotations

import io
import uuid
from decimal import Decimal

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.enums import SourcePlatform
from app.modules.control.models import AIActivity
from app.modules.sourcing import gallery, service
from app.modules.sourcing.models import Candidate, CandidateStage
from tests.sourcing.util import API, new_brief

OFFER = "https://detail.1688.com/offer/712345678901.html?spm=a26352.13672862&offerId=712345678901"
IMG = "https://cbu01.alicdn.com/img/ibank/O1CN01abc_!!2200000000000-0-cib.jpg"


def clip(**kw) -> dict:
    return {
        "url": OFFER,
        "title": "不锈钢折叠晾衣架 阳台落地",
        "price": "38.5",
        "currency": "CNY",
        "images": [IMG + "_400x400.jpg", "https://cbu01.alicdn.com/img/ibank/O1CN01def.jpg_.webp"],
        "specs": {"材质": "不锈钢", "尺寸": "120cm"},
        "variants": ["银色", "黑色"],
        "seller_name": "义乌某某家居厂",
        "seller_url": "https://shop1234.1688.com/",
        "rating": 4.8,
        "review_count": 1520,
        "sales_count": 30000,
        "moq": 2,
        **kw,
    }


async def _candidate(**kw) -> Candidate:
    async with SessionLocal() as s:
        c = Candidate(
            title_vi="Giá phơi cũ", title_original="旧", price_amount=Decimal("40"), price_currency="CNY", **kw
        )
        s.add(c)
        await s.commit()
        return c


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (90, 110, 140)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def fake_images(monkeypatch):
    seen: list[str] = []
    jpeg = _jpeg()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "cbu01.alicdn.com":
            return httpx.Response(200, content=jpeg, headers={"content-type": "image/jpeg"})
        raise AssertionError(f"Không được gọi tới {request.url}")

    monkeypatch.setattr(
        gallery, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    )
    monkeypatch.setattr(gallery, "_public_host", lambda host: True)
    monkeypatch.setattr(gallery, "caching_enabled", lambda: True)
    return seen


async def test_clip_needs_desk_login(client):
    assert (await client.post(f"{API}/clip", json=clip())).status_code == 401
    assert (await client.get(f"{API}/clip/match", params={"url": OFFER})).status_code == 401


async def test_clip_creates_candidate_and_copies_images(owner_client, fake_images):
    m = (await owner_client.get(f"{API}/clip/match", params={"url": OFFER})).json()
    assert m["platform"] == "1688" and m["external_id"] == "712345678901" and m["candidate_id"] is None
    assert m["canonical_url"] == "https://detail.1688.com/offer/712345678901.html"

    r = await owner_client.post(f"{API}/clip", json=clip())
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["kind"] == "link_import" and run["status"] == "succeeded", run
    cid = run["progress"]["candidate_ids"][0]
    c = (await owner_client.get(f"{API}/candidates/{cid}")).json()
    assert c["source_platform"] == "1688" and c["source_external_id"] == "712345678901"
    assert c["source_url"] == m["canonical_url"] and c["origin"] == "link"
    # ảnh đổi sang cỡ lớn (bỏ đuôi _400x400.jpg / .jpg_.webp)
    assert c["images"] == [IMG, "https://cbu01.alicdn.com/img/ibank/O1CN01def.jpg"]
    assert Decimal(c["price_amount"]) == Decimal("38.5") and c["price_currency"] == "CNY"
    assert c["seller_name"] == "义乌某某家居厂" and c["review_count"] == 1520 and c["sales_count"] == 30000
    assert c["moq"] == 2 and c["specs"] and c["title_vi"]
    assert c["raw"]["clip"]["title"] == "不锈钢折叠晾衣架 阳台落地"

    # ảnh đã lưu bản sao về kho riêng, trạng thái «Lấy ảnh và chi tiết» là xong
    g = (await owner_client.get(f"{API}/candidates/{cid}/gallery")).json()
    assert g["detail_fetch"]["status"] == "done" and g["detail_fetch"]["error"] is None
    assert g["detail_fetch"]["cached"] == 2 and all(i["cached"] for i in g["images"])
    assert sorted(fake_images) == sorted(c["images"])
    async with SessionLocal() as s:
        acts = (await s.execute(select(AIActivity).where(AIActivity.action == "sourcing.import_link"))).scalars()
        assert next(a.title for a in acts).startswith("Nhận hồ sơ từ trang chị mở")

    m2 = (await owner_client.get(f"{API}/clip/match", params={"url": OFFER})).json()
    assert m2["candidate_id"] == cid


async def test_clip_updates_existing_candidate_by_offer_id(helper_client):
    old = await _candidate(
        source_platform=SourcePlatform.ALIBABA_1688,
        source_external_id="712345678901",
        source_url="https://detail.1688.com/offer/712345678901.html",
        images=["https://cbu01.alicdn.com/old.jpg"],
        main_image_url="https://cbu01.alicdn.com/old.jpg",
        ai_score=82,
        stage=CandidateStage.SAMPLE,
        raw={
            "offers": [{"platform": "1688"}],
            "detail_fetch": {"status": "failed", "error": "Không đọc được trang nguồn: captcha", "blocked": True},
        },
    )
    run = (await helper_client.post(f"{API}/clip", json=clip(price=None, currency=None))).json()
    assert run["status"] == "succeeded" and run["progress"]["candidate_ids"] == [str(old.id)]
    assert run["new_count"] == 0
    c = (await helper_client.get(f"{API}/candidates/{old.id}")).json()
    assert c["ai_score"] == 82 and c["stage"] == "sample" and c["title_vi"] == "Giá phơi cũ"
    assert Decimal(c["price_amount"]) == Decimal("40")  # trang không thấy giá → giữ giá cũ
    assert c["images"][0] == IMG and c["images"][-1] == "https://cbu01.alicdn.com/old.jpg"
    assert c["raw"]["offers"] == [{"platform": "1688"}]
    g = (await helper_client.get(f"{API}/candidates/{old.id}/gallery")).json()
    assert g["detail_fetch"]["status"] == "done" and not g["detail_fetch"]["blocked"]


async def test_clip_matches_amazon_by_asin_and_goes_into_brief(owner_client):
    old = await _candidate(
        source_platform=SourcePlatform.AMAZON_JP,
        source_external_id="B0ABCDEF12",
        source_url="https://www.amazon.co.jp/dp/B0ABCDEF12",
    )
    long_url = "https://www.amazon.co.jp/%E3%83%98%E3%83%B3/dp/B0ABCDEF12/ref=sr_1_3?keywords=x&qid=1"
    m = (await owner_client.get(f"{API}/clip/match", params={"url": long_url})).json()
    assert m["candidate_id"] == str(old.id) and m["platform"] == "amazon_jp"

    b = await new_brief(owner_client)
    amazon = clip(
        url="https://www.amazon.co.jp/dp/B0ZZZZZZZ9?th=1",
        title="折りたたみ 物干し",
        currency="JPY",
        price="2980",
        images=["https://m.media-amazon.com/images/I/61SrKBHi8ML._AC_SX300_.jpg", "https://evil.example.com/a.jpg"],
        brief_id=b["id"],
    )
    run = (await owner_client.post(f"{API}/clip", json=amazon)).json()
    assert run["status"] == "succeeded" and run["brief_id"] == b["id"]
    c = (await owner_client.get(f"{API}/candidates/{run['progress']['candidate_ids'][0]}")).json()
    assert c["brief_id"] == b["id"] and c["source_external_id"] == "B0ZZZZZZZ9"
    assert c["images"] == ["https://m.media-amazon.com/images/I/61SrKBHi8ML.jpg"]  # ảnh ngoài máy chủ ảnh bị bỏ


async def test_generic_page_gets_hashed_id(owner_client):
    url = "https://shop.example.com/products/hop-dung-gia-vi?variant=1&utm_source=x"
    run = (await owner_client.post(f"{API}/clip", json=clip(url=url, images=[]))).json()
    assert run["status"] == "succeeded"
    c = (await owner_client.get(f"{API}/candidates/{run['progress']['candidate_ids'][0]}")).json()
    assert (
        c["source_platform"] == "web"
        and c["source_url"] == "https://shop.example.com/products/hop-dung-gia-vi?variant=1"
    )
    run2 = (await owner_client.post(f"{API}/clip", json=clip(url=url, images=[]))).json()
    assert run2["progress"]["candidate_ids"] == run["progress"]["candidate_ids"]


@pytest.mark.parametrize(
    "bad",
    [
        {"images": ["http://cbu01.alicdn.com/a.jpg"]},
        {"images": ["javascript:alert(1)"]},
        {"images": [IMG] * 41},
        {"images": ["https://cbu01.alicdn.com/" + "a" * 1000 + ".jpg"]},
        {"url": "http://detail.1688.com/offer/1.html"},
        {"title": ""},
        {"title": "x" * 501},
        {"description": "x" * 5001},
        {"specs": {f"k{i}": "v" for i in range(61)}},
        {"specs": {"k": "v" * 501}},
        {"seller_url": "http://shop.1688.com/"},
        {"rating": 7},
        {"currency": "yuan"},
        {"brief_id": "khong-phai-uuid"},
    ],
)
async def test_clip_rejects_bad_payloads(owner_client, bad):
    r = await owner_client.post(f"{API}/clip", json=clip(**bad))
    assert r.status_code == 422, r.text


async def test_clip_unknown_brief_is_404(owner_client):
    r = await owner_client.post(f"{API}/clip", json=clip(brief_id=str(uuid.uuid4())))
    assert r.status_code == 404


async def test_blocked_fetch_is_flagged(owner_client, monkeypatch):
    from app.integrations import IntegrationError
    from app.integrations.sources.mock import Driver as Mock

    async def boom(self, url):
        raise IntegrationError("Trang bắt giải captcha.")

    monkeypatch.setattr(Mock, "fetch_product", boom)
    c = await _candidate(
        source_platform=SourcePlatform.ALIBABA_1688,
        source_external_id="99887766",
        source_url="https://detail.1688.com/offer/99887766.html",
    )
    g = (await owner_client.post(f"{API}/candidates/{c.id}/fetch-details")).json()
    assert g["detail_fetch"]["status"] == "failed" and g["detail_fetch"]["blocked"] is True
    assert service.detail_state(await _reload(c.id))["blocked"] is True


async def _reload(cid: uuid.UUID) -> Candidate:
    async with SessionLocal() as s:
        return await s.get(Candidate, cid)
