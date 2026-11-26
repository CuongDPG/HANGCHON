"""Hồ sơ bán: chị chọn dùng lại ảnh nhà cung cấp từ hồ sơ ứng viên. Không tự chép; ảnh đi đường xử lý như ảnh chị
tải lên, đánh dấu nguồn ở desk, website không lộ link/tên nhà cung cấp (cả trong alt, tên tệp, EXIF)."""

from __future__ import annotations

import io
import json

from PIL import Image
from sqlalchemy import select

from app.core.storage import get_storage
from app.modules.catalog.models import ImageKind, ProductImage
from app.modules.sourcing.models import Candidate
from tests.catalog.factories import published_product

SUPPLIER_HOST = "img.supplier-shop.example"
URLS = [f"https://{SUPPLIER_HOST}/item/{i}.jpg" for i in range(3)]


def _supplier_jpeg() -> bytes:
    """Ảnh nhà cung cấp mang EXIF/XMP/chú thích có tên shop."""
    img = Image.new("RGB", (700, 500), (235, 235, 230))
    img.paste(Image.new("RGB", (300, 260), (90, 110, 140)), (200, 120))
    exif = Image.Exif()
    exif[0x013B] = "TaobaoShopBiMat"  # Artist
    exif[0x8298] = "(c) TaobaoShopBiMat"  # Copyright
    buf = io.BytesIO()
    img.save(
        buf, "JPEG", exif=exif.tobytes(), xmp=b"<x:xmpmeta>TaobaoShopBiMat</x:xmpmeta>", comment=b"TaobaoShopBiMat"
    )
    return buf.getvalue()


async def _product_with_supplier_images(db, *, cache: int = 2):
    p = await published_product(db)
    c = await db.get(Candidate, p.candidate_id)
    c.images, c.main_image_url, c.seller_name = URLS, URLS[0], "TaobaoShopBiMat"
    c.source_url = f"https://{SUPPLIER_HOST}/item.html"
    entries = []
    for i, url in enumerate(URLS[:cache]):
        key = f"private/sourcing/candidates/{c.id}/img{i}.jpg"
        await get_storage().put(key, _supplier_jpeg(), "image/jpeg")
        entries.append({"url": url, "key": key, "type": "image/jpeg", "bytes": 1})
    c.image_cache = entries
    await db.commit()
    return p


async def test_owner_picks_supplier_images_and_they_become_product_images(db, owner_client):
    p = await _product_with_supplier_images(db)
    base = f"/api/desk/catalog/products/{p.id}"
    opts = (await owner_client.get(f"{base}/supplier-images")).json()
    assert [o["source_url"] for o in opts] == URLS
    assert [o["cached"] for o in opts] == [True, True, False] and not any(o["used"] for o in opts)

    r = await owner_client.post(f"{base}/supplier-images", json={"urls": URLS[:2]})
    assert r.status_code == 201, r.text
    imgs = r.json()["images"]
    assert len(imgs) == 2 and all(i["source"] == "supplier" and i["status"] == "processed" for i in imgs)
    assert imgs[0]["is_primary"] and all(i["alt"] == p.name for i in imgs)
    rows = (await db.execute(select(ProductImage).where(ProductImage.product_id == p.id))).scalars().all()
    assert {r.kind for r in rows} == {ImageKind.SUPPLIER} and {r.source_url for r in rows} == set(URLS[:2])
    assert all(r.original_key.startswith("private/products/originals/") for r in rows)

    # đã dùng thì đánh dấu, chọn lại không sinh trùng; ảnh chị tải lên vẫn là «own»
    assert [o["used"] for o in (await owner_client.get(f"{base}/supplier-images")).json()] == [True, True, False]
    r = await owner_client.post(f"{base}/supplier-images", json={"urls": URLS[:1]})
    assert len(r.json()["images"]) == 2
    buf = io.BytesIO()
    Image.new("RGB", (500, 500), (120, 90, 60)).save(buf, "JPEG")
    r = await owner_client.post(f"{base}/images", files={"file": ("own.jpg", buf.getvalue(), "image/jpeg")})
    assert [i["source"] for i in r.json()["images"]] == ["supplier", "supplier", "own"]


async def test_reuse_only_images_of_the_dossier_that_are_cached(db, owner_client):
    p = await _product_with_supplier_images(db)
    base = f"/api/desk/catalog/products/{p.id}/supplier-images"
    r = await owner_client.post(base, json={"urls": ["https://evil.example/x.jpg"]})
    assert r.status_code == 400 and r.json()["code"] == "not_in_dossier"
    r = await owner_client.post(base, json={"urls": [URLS[2]]})  # chưa lưu về kho
    assert r.status_code == 400 and r.json()["code"] == "image_not_cached"
    r = await owner_client.post(base, json={"urls": []})
    assert r.status_code == 422


async def test_website_does_not_reveal_the_supplier(db, owner_client, client):
    p = await _product_with_supplier_images(db)
    await owner_client.post(f"/api/desk/catalog/products/{p.id}/supplier-images", json={"urls": URLS[:2]})
    pub = (await client.get(f"/api/store/catalog/products/{p.slug}")).json()
    text = json.dumps(pub, ensure_ascii=False)
    assert len(pub["images"]) == 2
    assert SUPPLIER_HOST not in text and "TaobaoShopBiMat" not in text and "supplier" not in text.lower()
    assert "source" not in pub["images"][0]
    shelf = json.dumps((await client.get("/api/store/catalog/products")).json(), ensure_ascii=False)
    assert SUPPLIER_HOST not in shelf
    # các cỡ ảnh công khai: tên tệp ngẫu nhiên, không còn EXIF/XMP/chú thích của nhà cung cấp
    for img in pub["images"]:
        for url in [img["src"], img["src_large"], img["src_small"], *img["webp"].values()]:
            key = url.split("/api/files/", 1)[1]
            assert key.startswith(f"public/products/{p.id}/")
            data = await get_storage().get(key)
            assert b"TaobaoShopBiMat" not in data and b"Exif" not in data


async def test_channel_posts_use_supplier_origin_images(db, owner_client):
    """Bài các kênh lấy ảnh sản phẩm (gồm ảnh nhà cung cấp chị đã chọn), bản đã xử lý ở kho công khai."""
    from app.modules.catalog.models import Product
    from app.modules.content.facts import image_keys

    p = await _product_with_supplier_images(db)
    pid = p.id
    await owner_client.post(f"/api/desk/catalog/products/{pid}/supplier-images", json={"urls": URLS[:2]})
    db.expire_all()
    prod = await db.get(Product, pid)
    await db.refresh(prod, ["images"])
    keys = image_keys(prod)
    assert len(keys) == 2 and all(k.startswith("public/products/") for k in keys)
