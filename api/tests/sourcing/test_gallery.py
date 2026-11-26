"""Ảnh nhà cung cấp của ứng viên (chỉ desk): lưu bản sao về kho riêng an toàn (chặn IP nội bộ, giới hạn cỡ/loại/số
ảnh), «Lấy ảnh và chi tiết», ảnh từ bước thẩm định, ảnh thu nhỏ ở danh sách. HTTP luôn giả (httpx.MockTransport)."""

from __future__ import annotations

import io
import uuid

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.core import events
from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.integrations import IntegrationError
from app.modules.control.models import AIActivity
from app.modules.sourcing import gallery
from app.modules.sourcing.imagehash import _public_host
from app.modules.sourcing.models import Candidate
from tests.selection.helpers import make_candidate
from tests.sourcing.util import API, scanned_brief


def _jpeg(w: int = 120, h: int = 90) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 110, 140)).save(buf, "JPEG")
    return buf.getvalue()


JPEG = _jpeg()


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.url.host == "cdn.example.com":
        if path.startswith("/ok"):
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        if path == "/missing.jpg":
            return httpx.Response(404)
        if path == "/page.html":
            return httpx.Response(200, content=b"<html>captcha</html>", headers={"content-type": "text/html"})
        if path == "/fake.jpg":  # nói là ảnh nhưng không phải
            return httpx.Response(200, content=b"not an image", headers={"content-type": "image/jpeg"})
        if path == "/huge.jpg":
            return httpx.Response(
                200, content=b"\xff" * (gallery.MAX_BYTES + 10), headers={"content-type": "image/jpeg"}
            )
        if path == "/to-internal.jpg":  # chuyển hướng sang địa chỉ nội bộ
            return httpx.Response(302, headers={"location": "http://internal.test/secret.jpg"})
        if path == "/to-ok.jpg":
            return httpx.Response(301, headers={"location": "/ok-after-redirect.jpg"})
        if path == "/loop.jpg":
            return httpx.Response(302, headers={"location": "/loop.jpg"})
    raise AssertionError(f"Không được gọi tới {request.url}")  # vd internal.test: phải bị chặn trước khi gửi


@pytest.fixture
def fake_net(monkeypatch):
    """HTTP giả + DNS giả: `internal.test` coi như trỏ vào mạng nội bộ."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _handler(request)

    monkeypatch.setattr(
        gallery, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    )
    monkeypatch.setattr(gallery, "_public_host", lambda host: host != "internal.test")
    return seen


def test_public_host_blocks_private_ranges():
    for ip in ("127.0.0.1", "10.1.2.3", "192.168.1.1", "169.254.169.254", "::1", "0.0.0.0"):
        assert not _public_host(ip), ip
    assert _public_host("8.8.8.8")


async def test_cache_images_keeps_good_images_and_records_why_others_failed(fake_net):
    urls = [
        "https://cdn.example.com/ok-1.jpg",
        "https://cdn.example.com/missing.jpg",
        "https://cdn.example.com/page.html",
        "https://cdn.example.com/fake.jpg",
        "https://cdn.example.com/huge.jpg",
        "https://cdn.example.com/to-internal.jpg",
        "http://internal.test/direct.jpg",
        "https://cdn.example.com/to-ok.jpg",
        "https://cdn.example.com/loop.jpg",
        "ftp://cdn.example.com/x.jpg",  # không phải http(s): bỏ qua hẳn
    ]
    c = await make_candidate(main_image_url=urls[0], images=urls)
    async with SessionLocal() as s:
        c = await s.get(Candidate, c.id)
        res = await gallery.cache_images(c)
        await s.commit()
    assert res == {"cached": 2, "failed": 7}
    m = gallery.cache_map(c)
    assert "ftp://cdn.example.com/x.jpg" not in m
    ok = m["https://cdn.example.com/ok-1.jpg"]
    assert ok["key"].startswith(f"private/sourcing/candidates/{c.id}/") and ok["type"] == "image/jpeg"
    assert await get_storage().get(ok["key"]) == JPEG
    assert gallery.cached(m["https://cdn.example.com/to-ok.jpg"])  # chuyển hướng hợp lệ thì theo
    assert "404" in m["https://cdn.example.com/missing.jpg"]["error"]
    assert "không trả về ảnh" in m["https://cdn.example.com/page.html"]["error"]
    assert "không phải ảnh" in m["https://cdn.example.com/fake.jpg"]["error"]
    assert "5 MB" in m["https://cdn.example.com/huge.jpg"]["error"]
    assert "nội bộ" in m["https://cdn.example.com/to-internal.jpg"]["error"]
    assert "nội bộ" in m["http://internal.test/direct.jpg"]["error"]
    assert "chuyển hướng" in m["https://cdn.example.com/loop.jpg"]["error"]
    assert not any("internal.test" in u for u in fake_net)  # chặn trước khi gửi request

    # hiển thị: bản đã lưu qua /api/files (cùng origin), chưa lưu thì link gốc
    shown = {g["source_url"]: g for g in gallery.display(c)}
    assert shown[urls[0]]["src"] == f"/api/files/{ok['key']}" and shown[urls[0]]["cached"]
    assert shown[urls[1]]["src"] == urls[1] and not shown[urls[1]]["cached"]

    # chạy lại không tải lại ảnh đã lưu, không thử lại ảnh lỗi (trừ khi chị bấm lấy lại)
    fake_net.clear()
    async with SessionLocal() as s:
        c = await s.get(Candidate, c.id)
        assert await gallery.cache_images(c) == {"cached": 0, "failed": 0}
        assert fake_net == []
        await gallery.cache_images(c, retry_failed=True)
        assert "https://cdn.example.com/ok-1.jpg" not in fake_net and "https://cdn.example.com/missing.jpg" in fake_net


async def test_at_most_twelve_images_per_candidate(fake_net):
    urls = [f"https://cdn.example.com/ok-{i}.jpg" for i in range(15)]
    c = await make_candidate(images=urls)
    async with SessionLocal() as s:
        c = await s.get(Candidate, c.id)
        assert (await gallery.cache_images(c))["cached"] == gallery.MAX_IMAGES == 12
    assert len(fake_net) == 12 and len(gallery.display(c)) == 12


async def test_fetch_details_button_gets_images_and_caches_them(owner_client, fake_net, monkeypatch):
    from app.integrations.sources.mock import Driver as Mock

    real = Mock.fetch_product

    async def fetch(self, url):
        p = await real(self, url)
        return p.model_copy(update={"images": [f"https://cdn.example.com/ok-{i}.jpg" for i in range(3)]})

    monkeypatch.setattr(Mock, "fetch_product", fetch)
    c = await make_candidate(source_url="https://item.rakuten.co.jp/shop/item-1/")
    g = (await owner_client.get(f"{API}/candidates/{c.id}/gallery")).json()
    assert g["images"] == [] and g["detail_fetch"] is None

    r = await owner_client.post(f"{API}/candidates/{c.id}/fetch-details")
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["detail_fetch"]["status"] == "done" and g["detail_fetch"]["cached"] == 3
    assert len(g["images"]) == 3 and all(
        i["cached"] and i["src"].startswith("/api/files/private/") for i in g["images"]
    )
    async with SessionLocal() as s:
        row = await s.get(Candidate, c.id)
        assert row.main_image_url == "https://cdn.example.com/ok-0.jpg"
        assert row.raw.get("reviews") and row.raw["detail"]["fetched_at"]
        act = (await s.execute(select(AIActivity).where(AIActivity.action == "sourcing.fetch_details"))).scalars()
        assert len(list(act)) == 1

    # danh sách ứng viên + hồ sơ: ảnh thu nhỏ là bản đã lưu; bản lưu ở kho riêng cần đăng nhập
    detail = (await owner_client.get(f"{API}/candidates/{c.id}")).json()
    assert detail["thumb_url"] == g["images"][0]["src"] and len(detail["gallery"]) == 3
    key = g["images"][0]["src"].removeprefix("/api/files/")
    assert (await owner_client.get(f"/api/files/{key}")).content == JPEG


async def test_cached_files_need_login(client, fake_net):
    c = await make_candidate(images=["https://cdn.example.com/ok-x.jpg"])
    async with SessionLocal() as s:
        c = await s.get(Candidate, c.id)
        await gallery.cache_images(c)
        await s.commit()
    key = gallery.cache_map(c)["https://cdn.example.com/ok-x.jpg"]["key"]
    assert (await client.get(f"/api/files/{key}")).status_code == 401


async def test_fetch_details_failure_is_reported(owner_client, monkeypatch):
    from app.integrations.sources.mock import Driver as Mock

    async def boom(self, url):
        raise IntegrationError("Trang yêu cầu xác minh (captcha).")

    monkeypatch.setattr(Mock, "fetch_product", boom)
    c = await make_candidate(source_url="https://detail.1688.com/offer/123.html")
    g = (await owner_client.post(f"{API}/candidates/{c.id}/fetch-details")).json()
    assert g["detail_fetch"]["status"] == "failed" and "captcha" in g["detail_fetch"]["error"]

    no_url = await make_candidate(source_url=None)
    r = await owner_client.post(f"{API}/candidates/{no_url.id}/fetch-details")
    assert r.status_code == 400 and r.json()["code"] == "no_source_url"


async def test_assessment_detail_images_reach_the_candidate(owner_client, fake_net, monkeypatch):
    """Thẩm định đọc trang chi tiết → `candidate.details_fetched` → sourcing ghi ảnh và lưu bản sao."""
    monkeypatch.setattr(gallery, "caching_enabled", lambda: True)
    c = await make_candidate()
    imgs = ["https://cdn.example.com/ok-a.jpg", "https://cdn.example.com/ok-b.jpg"]
    async with SessionLocal() as s:
        await events.emit("candidate.details_fetched", {"candidate_id": str(c.id), "images": imgs}, db=s)
        await events.emit("candidate.details_fetched", {"candidate_id": str(c.id), "images": imgs}, db=s)  # lặp lại
        await s.commit()
        row = await s.get(Candidate, c.id)
        assert row.images == imgs and row.main_image_url == imgs[0]
        assert all(g["cached"] for g in gallery.display(row))


async def test_assessment_reads_detail_page_when_images_are_missing(owner_client):
    """Ứng viên chỉ có 0–1 ảnh: bước thẩm định đọc trang chi tiết (driver mock trả 4 ảnh) và ảnh về ứng viên."""
    c = await make_candidate(specs={"Chất liệu": "Inox"})
    r = await owner_client.post(f"/api/desk/assessment/candidates/{c.id}/run", json={})
    assert r.status_code in (200, 201), r.text
    async with SessionLocal() as s:
        row = await s.get(Candidate, c.id)
        assert len(row.images) >= 2 and row.main_image_url


async def test_scan_cards_have_thumbnails_and_auto_details_pick_top_ranked(owner_client):
    _, items = await scanned_brief(owner_client)
    assert items and all(i["thumb_url"] == i["main_image_url"] for i in items)  # chưa lưu bản sao → link gốc
    from app.modules.sourcing import service

    async with SessionLocal() as s:
        ids = await service.auto_detail_ids(s, [i["id"] for i in items])
    # driver mock trả 1 ảnh mỗi tin rao → mọi món đều thiếu ảnh; lấy 5 món điểm cao nhất
    assert len(ids) == service.DEFAULT_AUTO_DETAIL_TOP_N
    score = {i["id"]: i["ai_score"] or 0 for i in items}
    top = sorted(score.values(), reverse=True)[:5]
    assert sorted((score[str(i)] for i in ids), reverse=True) == top


async def test_candidate_gallery_404(owner_client):
    r = await owner_client.get(f"{API}/candidates/{uuid.uuid4()}/gallery")
    assert r.status_code == 404
