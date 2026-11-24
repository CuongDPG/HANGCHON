"""e6 xử lý ảnh: xoay theo EXIF, cân sáng, cắt vuông giữ chủ thể, các cỡ webp/jpg, bỏ EXIF; sắp thứ tự, ảnh bìa."""

from __future__ import annotations

import io
import uuid

from PIL import Image
from sqlalchemy import select

from app import control
from app.core.storage import get_storage
from app.modules.catalog import images as lib
from app.modules.catalog.models import ImageStatus, ProductImage
from app.modules.control.models import AIActivity, AutonomyLevel
from tests.catalog.factories import jpeg, published_product


def test_process_photo_rotates_crops_and_strips_exif():
    # ảnh ngang 800x400, EXIF orientation 6 (xoay 90°) → sau khi xoay thành ảnh đứng 400x800
    data = jpeg(800, 400, orientation=6)
    out = lib.process_photo(data)
    ops = [o["op"] for o in out.ops]
    assert ops[0] == "exif_transpose" and "crop" in ops and "autocontrast" in ops
    assert out.width == out.height == 400
    assert set(out.renditions) == {400}
    small = Image.open(io.BytesIO(out.renditions[400]["jpg"]))
    assert small.size == (400, 400) and not small.getexif()
    assert out.renditions[400]["webp"][:4] == b"RIFF"


def test_crop_follows_subject():
    # chủ thể nằm sát mép phải của ảnh ngang → khung cắt dịch sang phải, không cắt giữa
    data = jpeg(1200, 600, subject=(900, 200, 1150, 450))
    out = lib.process_photo(data)
    crop = next(o for o in out.ops if o["op"] == "crop")
    assert crop["box"][0] == 600 and crop["subject"] is not None
    plain = lib.process_photo(data, enhance=False)
    assert next(o for o in plain.ops if o["op"] == "crop")["box"][0] == 300
    big = lib.process_photo(jpeg(2000, 2400))
    assert sorted(big.renditions) == [400, 800, 1600]


def test_dark_photo_is_brightened_gently():
    img = Image.new("RGB", (400, 400), (30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    out = lib.process_photo(buf.getvalue())
    bright = next(o for o in out.ops if o["op"] == "brightness")
    assert 1.0 < bright["factor"] <= 1.25


async def test_upload_reorder_primary_delete_and_undo(db, owner_client):
    p = await published_product(db)
    await db.commit()
    r = await owner_client.post(
        f"/api/desk/catalog/products/{p.id}/images", files={"file": ("a.jpg", jpeg(), "image/jpeg")}
    )
    assert r.status_code == 201, r.text
    r = await owner_client.post(
        f"/api/desk/catalog/products/{p.id}/images", files={"file": ("b.jpg", jpeg(color=(200, 90, 80)), "image/jpeg")}
    )
    imgs = r.json()["images"]
    assert len(imgs) == 2 and imgs[0]["is_primary"] and not imgs[1]["is_primary"]
    assert all(i["status"] == "processed" and i["src"] and i["webp"] for i in imgs)
    first, second = imgs[0]["id"], imgs[1]["id"]
    row = await db.get(ProductImage, uuid.UUID(first))
    assert row.original_key.startswith("private/") and await get_storage().exists(row.original_key)

    r = await owner_client.put(f"/api/desk/catalog/products/{p.id}/images/order", json={"ids": [second, first]})
    assert [i["id"] for i in r.json()["images"]] == [second, first]
    r = await owner_client.post(f"/api/desk/catalog/products/{p.id}/images/{second}/primary")
    assert next(i for i in r.json()["images"] if i["id"] == second)["is_primary"]
    pub = (await owner_client.get(f"/api/store/catalog/products/{p.slug}")).json()
    assert pub["images"][0]["id"] == second and pub["image"]["id"] == second

    # hoàn tác bước chỉnh ảnh trong nhật ký AI → ảnh chỉ còn cắt vuông, không chỉnh sáng
    act = (await db.execute(select(AIActivity).where(AIActivity.action == "catalog.process_image"))).scalars().first()
    r = await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")
    assert r.status_code == 200, r.text
    ref_id, pid = act.ref_id, p.id
    db.expire_all()
    undone = await db.get(ProductImage, ref_id)
    assert not undone.ai_processed and all(o["op"] != "autocontrast" for o in undone.processing_ops)

    r = await owner_client.delete(f"/api/desk/catalog/products/{pid}/images/{second}")
    assert r.status_code == 204
    left = (await owner_client.get(f"/api/desk/catalog/products/{pid}")).json()["images"]
    assert [i["id"] for i in left] == [first] and left[0]["is_primary"]


async def test_upload_rejects_non_image(db, owner_client):
    p = await published_product(db)
    await db.commit()
    r = await owner_client.post(
        f"/api/desk/catalog/products/{p.id}/images", files={"file": ("a.txt", b"hello", "text/plain")}
    )
    assert r.status_code == 400 and r.json()["code"] == "bad_image"


async def test_image_processing_waits_when_level_ask(db, owner_client):
    await control.set_level(db, "catalog.process_image", AutonomyLevel.ASK, None)
    p = await published_product(db)
    await db.commit()
    r = await owner_client.post(
        f"/api/desk/catalog/products/{p.id}/images", files={"file": ("a.jpg", jpeg(), "image/jpeg")}
    )
    img = r.json()["images"][0]
    assert img["status"] == ImageStatus.PROCESSING.value and img["src"] is None
