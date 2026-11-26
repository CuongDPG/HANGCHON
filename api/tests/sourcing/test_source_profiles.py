"""Hồ sơ nguồn (`source_profiles`): link mẫu từng sàn → mã món → link chuẩn, đổi ảnh nhỏ sang ảnh lớn, máy chủ ảnh,
áp ở driver `web` (link ngắn cho web_fetch, ảnh đọc thẳng từ trang, «không đọc trang»), ở lớp bọc driver (kết quả tìm,
khử trùng theo mã) và ở bộ tải ảnh (Referer theo hồ sơ). HTTP luôn giả (httpx.MockTransport)."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image

from app.core.db import SessionLocal
from app.core.enums import SourcePlatform
from app.integrations import IntegrationError, get_driver
from app.integrations import source_profiles as sp
from app.integrations.sources import SourceItem, SourceProduct
from app.integrations.sources import web as web_driver
from app.integrations.sources._profiled import normalize, wrap
from app.modules.sourcing import gallery
from app.modules.sourcing.models import Candidate
from tests.selection.helpers import make_candidate

CASES = [
    # (link, sàn, mã, link chuẩn)
    (
        "https://www.amazon.co.jp/%E3%83%98%E3%82%A2%E3%82%B4%E3%83%A0-%E3%83%99/dp/B0G81HJ712/ref=sr_1_3?qid=1&th=1",
        "amazon_jp", "B0G81HJ712", "https://www.amazon.co.jp/dp/B0G81HJ712",
    ),
    ("https://amazon.co.jp/gp/product/B08B69661S?psc=1", "amazon_jp", "B08B69661S",
     "https://www.amazon.co.jp/dp/B08B69661S"),
    ("https://www.amazon.com/Thing/dp/B07XYZ1234?tag=x-20", "amazon", "B07XYZ1234", "https://www.amazon.com/dp/B07XYZ1234"),
    ("https://detail.1688.com/offer/606408068831.html?spm=a26352.1", "1688", "606408068831",
     "https://detail.1688.com/offer/606408068831.html"),
    ("https://m.1688.com/offer/606408068831.html", "1688", "606408068831",
     "https://detail.1688.com/offer/606408068831.html"),
    ("https://item.taobao.com/item.htm?spm=a1z10&id=6789012345&ns=1", "taobao", "6789012345",
     "https://item.taobao.com/item.htm?id=6789012345"),
    ("https://world.taobao.com/item/6789012345.htm", "taobao", "6789012345",
     "https://item.taobao.com/item.htm?id=6789012345"),
    ("https://detail.tmall.com/item.htm?abbucket=1&id=7123456789", "tmall", "7123456789",
     "https://detail.tmall.com/item.htm?id=7123456789"),
    ("https://mobile.yangkeduo.com/goods2.html?goods_id=123456789&page_from=1", "pinduoduo", "123456789",
     "https://mobile.yangkeduo.com/goods.html?goods_id=123456789"),
    ("https://www.alibaba.com/product-detail/Kids-Hair-Ties_1600123456789.html?spm=a2700", "alibaba", "1600123456789",
     "https://www.alibaba.com/product-detail/Kids-Hair-Ties_1600123456789.html"),
    ("https://item.rakuten.co.jp/careland/bp-hgm/?iasid=07rpp", "rakuten", "careland/bp-hgm",
     "https://item.rakuten.co.jp/careland/bp-hgm/"),
    ("https://www.xiaohongshu.com/explore/64a1b2c3d4e5f60718293a4b?xsec_token=AB&spm=x", "xiaohongshu",
     "64a1b2c3d4e5f60718293a4b", "https://www.xiaohongshu.com/explore/64a1b2c3d4e5f60718293a4b?xsec_token=AB"),
    ("https://shop.example.vn/p/abc?utm_source=fb&color=red&fbclid=zz", "web", None,
     "https://shop.example.vn/p/abc?color=red"),
]  # fmt: skip


@pytest.mark.parametrize(("url", "platform", "pid", "canon"), CASES)
def test_default_profiles_recognise_links(url, platform, pid, canon):
    p = sp.detect(url)
    assert p.platform == platform
    assert sp.extract_id(url, p)[0] == pid
    assert sp.canonical(url) == canon
    assert len(sp.canonical(url)) <= 250  # web_fetch nhận tối đa 250 ký tự


IMAGES = [
    ("amazon_jp", "https://m.media-amazon.com/images/I/61SrKBHi8ML._AC_SX300_SY300_QL70_ML2_.jpg",
     "https://m.media-amazon.com/images/I/61SrKBHi8ML.jpg", True),
    ("amazon_jp", "https://m.media-amazon.com/images/I/41abc+XYZL._SS40_.jpg",
     "https://m.media-amazon.com/images/I/41abc+XYZL.jpg", True),
    ("amazon_jp", "https://m.media-amazon.com/images/G/09/nav/sprite.png", None, False),  # không phải ảnh món
    ("1688", "https://cbu01.alicdn.com/img/ibank/O1CN01a_!!2206.jpg_400x400q90.jpg_.webp",
     "https://cbu01.alicdn.com/img/ibank/O1CN01a_!!2206.jpg", True),
    ("taobao", "https://img.alicdn.com/imgextra/i1/O1CN01x.png_310x310.jpg", "https://img.alicdn.com/imgextra/i1/O1CN01x.png",
     True),
    ("rakuten", "https://thumbnail.image.rakuten.co.jp/@0_mall/careland/cabinet/a/b.jpg?_ex=128x128",
     "https://image.rakuten.co.jp/careland/cabinet/a/b.jpg", True),
    ("rakuten", "https://ads.example.com/x.jpg", None, False),
    ("pinduoduo", "https://img.pddpic.com/m/a.jpeg?imageView2/2/w/300/q/70", "https://img.pddpic.com/m/a.jpeg", True),
    ("xiaohongshu", "https://sns-webpic-qc.xhscdn.com/2023/abc!nd_dft_wlteh_webp_3",
     "https://sns-webpic-qc.xhscdn.com/2023/abc", True),
    ("web", "https://placehold.co/800x800.png", "https://placehold.co/800x800.png", True),
]  # fmt: skip


@pytest.mark.parametrize(("platform", "src", "big", "allowed"), IMAGES)
def test_default_image_rewrites_and_hosts(platform, src, big, allowed):
    p = sp.get(platform)
    out, _ = sp.rewrite_image(src, p)
    assert sp.image_allowed(out, p) is allowed
    if big:
        assert out == big
    assert sp.clean_images([src, src], p) == ([big] if allowed else [])


def test_page_images_from_amazon_html():
    html = (
        '<script>var data = {"colorImages":{"initial":[{"hiRes":"https://m.media-amazon.com/images/I/81TL.'
        '_AC_SL1500_.jpg","large":"https://m.media-amazon.com/images/I/81TL._AC_.jpg"},{"hiRes":null,'
        '"large":"https://m.media-amazon.com/images/I/61Rl._AC_.jpg"}]}}</script>'
        '<img src="https://m.media-amazon.com/images/G/09/logo.png">'
    )
    assert sp.page_images(html, sp.get("amazon_jp")) == [
        "https://m.media-amazon.com/images/I/81TL.jpg",
        "https://m.media-amazon.com/images/I/61Rl.jpg",
    ]


def test_validation_messages():
    ok = sp.clean({"url_patterns": [r"shop\.test/p/(?P<id>\d+)"], "canonical_url": "https://shop.test/p/{id}"})
    assert ok["canonical_url"] == "https://shop.test/p/{id}"
    for bad, msg in [
        ({"url_patterns": ["shop/(\\d+"]}, "sai"),
        ({"url_patterns": [r"shop/(\d+)"]}, "(?P<id>"),
        ({"canonical_url": "https://shop.test/p/"}, "{id}"),
        ({"canonical_url": "https://shop.test/{id}/{x}"}, "chỉ dùng được {id}"),
        ({"canonical_url": "ftp://x/{id}"}, "https://"),
        ({"image_rewrites": [{"pattern": "_x", "replace": r"\2"}]}, "thay bằng"),
        ({"image_rewrites": [{"pattern": "(", "replace": ""}]}, "sai"),
        ({"image_hosts": ["bad host!"]}, "không hợp lệ"),
        ({"fetch_headers": {"Cookie": "a=1"}}, "chỉ dùng được"),
        ({"fetch_headers": {"Referer": "x\r\nX-Evil: 1"}}, "không hợp lệ"),
        ({"fetch_via": "magic"}, "route"),
        ({"page_image_patterns": ["no-group"]}, "nhóm"),
        ({"max_images": 40}, "1 đến 12"),
        ({"domains": ["not a domain"]}, "Tên miền"),
        ({"nope": 1}, "Không có ô"),
    ]:
        with pytest.raises(ValueError, match=__import__("re").escape(msg)):
            sp.clean(bad)


def test_overrides_win_over_defaults():
    try:
        sp._overrides["amazon_jp"] = sp.clean({"canonical_url": "https://www.amazon.co.jp/gp/product/{id}"})
        sp._effective.clear()
        assert (
            sp.canonical("https://www.amazon.co.jp/x/dp/B0G81HJ712") == "https://www.amazon.co.jp/gp/product/B0G81HJ712"
        )
        assert sp.get("amazon_jp").image_hosts == sp.DEFAULTS["amazon_jp"].image_hosts  # ô khác giữ mặc định
    finally:
        sp.reset()
    assert sp.canonical("https://www.amazon.co.jp/x/dp/B0G81HJ712") == "https://www.amazon.co.jp/dp/B0G81HJ712"


# ---- lớp bọc driver: kết quả tìm / hồ sơ ------------------------------------------------------------------------


def test_normalize_search_item():
    item = SourceItem(
        platform=SourcePlatform.WEB,
        external_id="whatever-ai-said",
        url="https://www.amazon.co.jp/%E3%83%98/dp/B08B69661S/ref=sr_1_1?keywords=x",
        title="ヘアゴム",
        price_amount=345,
        currency="JPY",
        image_url="https://m.media-amazon.com/images/I/61SrKBHi8ML._AC_UL320_.jpg",
    )
    out = normalize(item)
    assert out.platform == SourcePlatform.AMAZON_JP and out.external_id == "B08B69661S"
    assert out.url == "https://www.amazon.co.jp/dp/B08B69661S"
    assert out.image_url == "https://m.media-amazon.com/images/I/61SrKBHi8ML.jpg"


async def test_wrapper_passes_canonical_url_and_cleans_product(monkeypatch):
    seen = []

    async def fetch(url):
        seen.append(url)
        return SourceProduct(
            platform=SourcePlatform.AMAZON_JP, external_id="x", url=url, title="t", price_amount=1, currency="JPY",
            images=[f"https://m.media-amazon.com/images/I/a{i}._AC_SX300_.jpg" for i in range(20)]
            + ["https://ads.example.com/b.jpg"],
        )  # fmt: skip

    web = get_driver("sources", "web")
    monkeypatch.setattr(web, "fetch_product", fetch)
    p = await wrap(web).fetch_product("https://www.amazon.co.jp/%E3%83%98%E3%82%A2/dp/B0G81HJ712?th=1")
    assert seen == ["https://www.amazon.co.jp/dp/B0G81HJ712"]
    assert len(p.images) == 12 and p.images[0] == "https://m.media-amazon.com/images/I/a0.jpg"
    assert p.image_url == p.images[0] and all("ads.example" not in u for u in p.images)


async def test_mock_route_keeps_placeholder_images():
    """Giả lập trả ảnh giữ chỗ (placehold.co) cho link Taobao: không bị lọc theo máy chủ ảnh của sàn."""
    p = await wrap(get_driver("sources", "mock")).fetch_product("https://item.taobao.com/item.htm?id=5551234&spm=z")
    assert p.url == "https://item.taobao.com/item.htm?id=5551234" and p.images


# ---- driver web -------------------------------------------------------------------------------------------------


AMAZON_LONG = "https://www.amazon.co.jp/" + "%E3%83%98" * 60 + "/dp/B08RD2X83Z/ref=sr_1_2"


async def test_web_fetch_uses_short_url_and_page_images(fake_ai, monkeypatch):
    got = {}

    def fake(inp):
        got["url"] = inp.url
        return {"platform": "amazon_jp", "url": inp.url, "title": "Kẹp tóc", "price_amount": 998, "currency": "JPY",
                "readable": True, "images": []}  # fmt: skip

    fake_ai["sources.web_fetch_product"] = fake
    html = '"hiRes":"https://m.media-amazon.com/images/I/81TL._AC_SL1500_.jpg"'
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=html, headers={"content-type": "text/html; charset=utf-8"})

    monkeypatch.setattr(web_driver, "page_fetch_enabled", lambda: True)
    monkeypatch.setattr(web_driver, "page_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    p = await get_driver("sources", "web").fetch_product(AMAZON_LONG)
    assert len(AMAZON_LONG) > 250 and got["url"] == "https://www.amazon.co.jp/dp/B08RD2X83Z"
    assert str(calls[0].url) == "https://www.amazon.co.jp/dp/B08RD2X83Z"
    assert calls[0].headers["accept-language"].startswith("ja")  # header theo hồ sơ
    assert p.images == ["https://m.media-amazon.com/images/I/81TL.jpg"]  # ảnh lớn, không tốn AI


async def test_web_fetch_unreadable_but_page_images_found(fake_ai, monkeypatch):
    fake_ai["sources.web_fetch_product"] = lambda inp: {
        "platform": "amazon_jp", "url": inp.url, "title": "Kẹp", "price_amount": 0, "currency": "JPY",
        "readable": False, "note": "chặn", "description": "đoán từ đoạn trích",
    }  # fmt: skip
    monkeypatch.setattr(web_driver, "page_images", _async_return(["https://m.media-amazon.com/images/I/a.jpg"]))
    p = await get_driver("sources", "web").fetch_product("https://www.amazon.co.jp/dp/B08RD2X83Z")
    assert p.images == ["https://m.media-amazon.com/images/I/a.jpg"] and p.description is None and not p.specs


async def test_web_fetch_skip_profile_does_not_call_ai(fake_ai):
    def boom(inp):
        raise AssertionError("không được gọi AI")

    fake_ai["sources.web_fetch_product"] = boom
    try:
        sp._overrides["taobao"] = {"fetch_via": "skip"}
        sp._effective.clear()
        with pytest.raises(IntegrationError, match="không đọc trang"):
            await get_driver("sources", "web").fetch_product("https://item.taobao.com/item.htm?id=6789012345")
    finally:
        sp.reset()


def test_prompt_hints_are_appended():
    s = web_driver._with_hints("BASE", ["amazon_jp", "amazon_jp", "web"])
    assert s.startswith("BASE") and s.count("Amazon Nhật:") == 1 and "m.media-amazon.com" in s
    assert web_driver._with_hints("BASE", ["web"]) == "BASE"


def _async_return(value):
    async def f(*a, **k):
        return value

    return f


# ---- bộ tải ảnh: header + máy chủ ảnh theo hồ sơ ----------------------------------------------------------------


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (1, 2, 3)).save(buf, "JPEG")
    return buf.getvalue()


async def test_gallery_sends_profile_referer_and_rejects_foreign_hosts(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("referer") != "https://detail.1688.com/":
            return httpx.Response(403)
        return httpx.Response(200, content=_jpeg(), headers={"content-type": "image/jpeg"})

    monkeypatch.setattr(gallery, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(gallery, "_public_host", lambda host: True)
    ok, foreign = "https://cbu01.alicdn.com/img/ibank/a.jpg", "https://evil.example.com/a.jpg"
    c = await make_candidate(source_url="https://detail.1688.com/offer/606408068831.html", images=[ok, foreign])
    async with SessionLocal() as s:
        c = await s.get(Candidate, c.id)
        assert await gallery.cache_images(c) == {"cached": 1, "failed": 1}
        await s.commit()
    m = gallery.cache_map(c)
    assert gallery.cached(m[ok]) and "máy chủ ảnh của 1688" in m[foreign]["error"]
    assert [str(r.url) for r in seen] == [ok]  # ảnh lạ bị chặn trước khi gửi request


async def test_pasted_links_with_tracking_dedupe_to_one_candidate(owner_client):
    ids = []
    for spm in ("a1", "b2"):
        url = f"https://detail.1688.com/offer/612233445.html?spm={spm}&tracelog=x"
        r = await owner_client.post("/api/desk/sourcing/import-link", json={"url": url})
        assert r.json()["status"] == "succeeded", r.text
        ids.append(r.json()["progress"]["candidate_ids"][0])
    assert ids[0] == ids[1]
    c = (await owner_client.get(f"/api/desk/sourcing/candidates/{ids[0]}")).json()
    assert c["source_url"] == "https://detail.1688.com/offer/612233445.html"
