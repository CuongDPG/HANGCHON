"""a2 dán link, lấy hồ sơ · a3 tìm bằng ảnh."""

from __future__ import annotations

import io

from PIL import Image

from app.integrations import IntegrationError, get_driver
from tests.sourcing.util import API, new_brief

TAOBAO = "https://item.taobao.com/item.htm?id=681234567890"


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (46, 63, 143)).save(buf, format="PNG")
    return buf.getvalue()


async def test_import_link_creates_translated_candidate(owner_client):
    r = await owner_client.post(f"{API}/import-link", json={"url": TAOBAO})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["kind"] == "link_import" and run["status"] == "succeeded"
    cid = run["progress"]["candidate_ids"][0]
    c = (await owner_client.get(f"{API}/candidates/{cid}")).json()
    assert c["origin"] == "link" and c["source_platform"] == "taobao" and c["source_url"] == TAOBAO
    assert c["title_vi"] and not any("一" <= ch <= "鿿" for ch in c["title_vi"])  # đã dịch, không còn chữ Hán
    assert c["description_vi"] and c["specs"] and len(c["images"]) == 4
    assert c["raw"]["reviews"] and c["landed_estimate_vnd"] > c["price_vnd_estimate"]
    # dán lại cùng link → không tạo trùng
    run2 = (await owner_client.post(f"{API}/import-link", json={"url": TAOBAO})).json()
    assert run2["progress"]["candidate_ids"] == [cid] and run2["new_count"] == 0


async def test_import_link_into_brief(owner_client):
    b = await new_brief(owner_client)
    run = (await owner_client.post(f"{API}/import-link", json={"url": TAOBAO, "brief_id": b["id"]})).json()
    assert run["brief_id"] == b["id"]
    items = (await owner_client.get(f"{API}/briefs/{b['id']}/candidates")).json()["items"]
    assert [i["id"] for i in items] == run["progress"]["candidate_ids"]


async def test_import_link_validation_and_driver_error(owner_client, monkeypatch):
    r = await owner_client.post(f"{API}/import-link", json={"url": "khong-phai-link"})
    assert r.status_code == 422

    async def broken(url):
        raise IntegrationError("Trang yêu cầu đăng nhập.")

    monkeypatch.setattr(get_driver("sources"), "fetch_product", broken)
    run = (await owner_client.post(f"{API}/import-link", json={"url": TAOBAO})).json()
    assert run["status"] == "failed" and "đăng nhập" in run["error"]


async def test_image_search_creates_brief_and_candidates(owner_client):
    files = {"file": ("anh.png", png(), "image/png")}
    r = await owner_client.post(
        f"{API}/image-search", files=files, data={"note": "giá phơi gấp ngoài ban công nhà bạn"}
    )
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["kind"] == "image_search" and run["status"] == "succeeded", run
    bid = run["progress"]["brief_id"]
    b = (await owner_client.get(f"{API}/briefs/{bid}")).json()
    assert b["input_mode"] == "image" and b["status"] == "active" and b["title"].startswith("Giá phơi")
    assert b["keywords_translated"]["zh"] and b["keywords_translated"]["ja"]
    items = (await owner_client.get(f"{API}/briefs/{bid}/candidates")).json()["items"]
    assert items and all(i["origin"] == "image" for i in items)


async def test_image_search_rejects_bad_files(owner_client, helper_client):
    r = await owner_client.post(f"{API}/image-search", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400
    r = await owner_client.post(f"{API}/image-search", files={"file": ("a.png", b"", "image/png")})
    assert r.status_code == 400
    r = await helper_client.post(f"{API}/image-search", files={"file": ("a.png", png(), "image/png")})
    assert r.status_code == 200  # người phụ được tìm hàng
