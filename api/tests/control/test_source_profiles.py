"""Cài đặt → Nguồn hàng → Cấu hình nâng cao: xem hồ sơ (mặc định / đã sửa), sửa có kiểm, khôi phục mặc định,
«Thử với một link» (tại chỗ, không gọi AI). Chỉ chị (owner)."""

from __future__ import annotations

import httpx

from app.integrations import source_profiles as sp

B = "/api/desk/control/sources"


def _prof(data: dict, platform: str) -> dict:
    return next(x for x in data["profiles"] if x["platform"] == platform)


async def test_only_owner(helper_client: httpx.AsyncClient):
    assert (await helper_client.patch(f"{B}/profiles/amazon_jp", json={"fields": {"max_images": 3}})).status_code == 403
    assert (await helper_client.delete(f"{B}/profiles/amazon_jp")).status_code == 403
    r = await helper_client.post(f"{B}/profiles/try", json={"url": "https://www.amazon.co.jp/dp/B08B69661S"})
    assert r.status_code == 403


async def test_overview_has_every_profile(owner_client: httpx.AsyncClient):
    data = (await owner_client.get(B)).json()
    assert [p["platform"] for p in data["profiles"]] == list(sp.DEFAULTS)
    amz = _prof(data, "amazon_jp")
    assert amz["effective"] == amz["defaults"] and amz["overridden"] == []
    assert amz["effective"]["canonical_url"] == "https://www.amazon.co.jp/dp/{id}"
    assert amz["effective"]["image_rewrites"][0]["pattern"]


async def test_save_validate_and_reset(owner_client: httpx.AsyncClient):
    r = await owner_client.patch(
        f"{B}/profiles/amazon_jp",
        json={"fields": {"max_images": 4, "fetch_headers": {"referer": "https://www.amazon.co.jp/"}}},
    )
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["overridden"] == ["fetch_headers", "max_images"] and p["effective"]["max_images"] == 4
    assert p["effective"]["fetch_headers"] == {"Referer": "https://www.amazon.co.jp/"}
    assert p["defaults"]["max_images"] == 12
    assert sp.get("amazon_jp").max_images == 4  # có hiệu lực ngay (bản chụp đọc lại sau khi lưu)

    # sai → 400 câu tiếng Việt, không lưu gì
    bad = await owner_client.patch(f"{B}/profiles/amazon_jp", json={"fields": {"url_patterns": ["amazon/(\\d+)"]}})
    assert bad.status_code == 400 and "(?P<id>" in bad.json()["detail"]
    bad = await owner_client.patch(f"{B}/profiles/amazon_jp", json={"fields": {"canonical_url": "https://x/dp/"}})
    assert bad.status_code == 400 and "{id}" in bad.json()["detail"]
    assert (await owner_client.patch(f"{B}/profiles/nowhere", json={"fields": {}})).status_code == 404

    # null = về mặc định cho ô đó; bằng mặc định cũng không tính là đã sửa
    p = (await owner_client.patch(f"{B}/profiles/amazon_jp", json={"fields": {"max_images": None}})).json()
    assert p["overridden"] == ["fetch_headers"]
    p = (
        await owner_client.patch(
            f"{B}/profiles/amazon_jp", json={"fields": {"fetch_headers": p["defaults"]["fetch_headers"]}}
        )
    ).json()
    assert p["overridden"] == []

    await owner_client.patch(f"{B}/profiles/1688", json={"fields": {"fetch_via": "skip"}})
    assert sp.get("1688").fetch_via == "skip"
    assert (await owner_client.delete(f"{B}/profiles/1688")).status_code == 204
    assert sp.get("1688").fetch_via == "route"
    data = (await owner_client.get(B)).json()
    assert _prof(data, "1688")["overridden"] == []

    # không sửa được qua PATCH /settings chung (bỏ qua bước kiểm) và không hiện ở danh sách cài đặt chung
    r = await owner_client.patch("/api/desk/control/settings/source_profile.1688", json={"value": {"fields": {}}})
    assert r.status_code == 400
    keys = [s["key"] for s in (await owner_client.get("/api/desk/control/settings")).json()]
    assert not any(k.startswith("source_profile.") for k in keys)
    audit = (
        await owner_client.get("/api/desk/control/audit", params={"action": "control.source_profile_saved"})
    ).json()
    assert audit["total"] >= 3


async def test_try_link(owner_client: httpx.AsyncClient):
    url = "https://www.amazon.co.jp/%E3%83%98%E3%82%A2/dp/B0G81HJ712/ref=sr_1_3?qid=1"
    r = await owner_client.post(
        f"{B}/profiles/try",
        json={"url": url, "image_url": "https://m.media-amazon.com/images/I/61SrKBHi8ML._AC_SX300_.jpg"},
    )
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["platform"], t["id"], t["canonical_url"]) == (
        "amazon_jp",
        "B0G81HJ712",
        "https://www.amazon.co.jp/dp/B0G81HJ712",
    )
    assert t["image"]["output"] == "https://m.media-amazon.com/images/I/61SrKBHi8ML.jpg" and t["image"]["allowed"]

    # thử với bản đang sửa (chưa lưu): đổi link chuẩn của Amazon Nhật
    r = await owner_client.post(
        f"{B}/profiles/try",
        json={"url": url, "platform": "amazon_jp", "fields": {"canonical_url": "https://amazon.co.jp/gp/product/{id}"}},
    )
    assert r.json()["canonical_url"] == "https://amazon.co.jp/gp/product/B0G81HJ712"
    assert sp.get("amazon_jp").canonical_url == "https://www.amazon.co.jp/dp/{id}"  # chưa lưu

    t = (await owner_client.post(f"{B}/profiles/try", json={"url": "https://shop.example.vn/p/1?utm_source=x"})).json()
    assert t["platform"] == "web" and t["id"] is None and t["canonical_url"] == "https://shop.example.vn/p/1"
    r = await owner_client.post(f"{B}/profiles/try", json={"url": "amazon.co.jp/dp/B0G81HJ712"})
    assert r.status_code == 400
    r = await owner_client.post(
        f"{B}/profiles/try", json={"url": url, "platform": "amazon_jp", "fields": {"url_patterns": ["("]}}
    )
    assert r.status_code == 400
