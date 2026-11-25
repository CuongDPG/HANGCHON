"""e6 làm sạch nền: nền sáng đều màu (trắng ngà, xám nhạt) → trắng; nền tối/có màu/lốm đốm giữ nguyên; vùng sáng nằm
trong món không bị đụng; tắt được ở cài đặt; hoàn tác trong nhật ký AI quay về ảnh chưa chỉnh."""

from __future__ import annotations

import io
import uuid

from PIL import Image, ImageDraw
from sqlalchemy import select

from app import control
from app.core.storage import get_storage
from app.modules.catalog import images as lib
from app.modules.catalog.models import ProductImage
from app.modules.catalog.products import CLEAN_BG_SETTING
from app.modules.control.models import AIActivity
from tests.catalog.factories import jpeg, published_product


def _img(bg: tuple[int, int, int], *, size: int = 900) -> Image.Image:
    im = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(im)
    d.rectangle((250, 250, 650, 650), fill=(50, 70, 120))
    d.rectangle((400, 400, 500, 500), fill=bg)  # ô sáng cùng màu nền nằm TRONG món
    return im


def test_light_gray_background_becomes_white_but_subject_untouched():
    out, op = lib.clean_background(_img((228, 228, 224)))
    assert op is not None and op["op"] == "clean_background"
    assert out.getpixel((10, 10)) == (255, 255, 255)
    assert out.getpixel((300, 300)) == (50, 70, 120)  # món giữ nguyên
    assert out.getpixel((450, 450)) == (228, 228, 224)  # vùng sáng trong món không bị làm trắng


def test_skips_when_background_is_not_simple():
    assert lib.clean_background(_img((40, 40, 40)))[1] is None  # nền tối
    assert lib.clean_background(_img((200, 150, 90)))[1] is None  # nền có màu (bàn gỗ)
    assert lib.clean_background(_img((255, 255, 255)))[1] is None  # đã trắng sẵn
    striped = _img((230, 225, 215))
    d = ImageDraw.Draw(striped)
    for x in range(0, 900, 40):
        d.rectangle((x, 0, x + 19, 240), fill=(180, 170, 150))  # mép trên có vân
        d.rectangle((x, 660, x + 19, 900), fill=(180, 170, 150))
    assert lib.clean_background(striped)[1] is None
    close_up = Image.new("RGB", (600, 600), (50, 70, 120))
    ImageDraw.Draw(close_up).rectangle((0, 0, 600, 40), fill=(230, 230, 230))
    assert lib.clean_background(close_up)[1] is None  # ảnh cận, nền quá ít


def test_process_photo_records_op_and_can_skip():
    data = jpeg(1200, 1600)
    assert "clean_background" in [o["op"] for o in lib.process_photo(data).ops]
    assert "clean_background" not in [o["op"] for o in lib.process_photo(data, clean_bg=False).ops]
    assert "clean_background" not in [o["op"] for o in lib.process_photo(data, enhance=False).ops]


async def _corner(img: ProductImage) -> tuple[int, int, int]:
    data = await get_storage().get(lib.pick(lib.rendition_files(img.processing_ops), 400))
    return Image.open(io.BytesIO(data)).convert("RGB").getpixel((3, 3))


async def test_upload_cleans_background_setting_off_and_undo(db, owner_client):
    p = await published_product(db)
    await db.commit()
    url = f"/api/desk/catalog/products/{p.id}/images"
    first = (await owner_client.post(url, files={"file": ("a.jpg", jpeg(1200, 1600), "image/jpeg")})).json()
    row = await db.get(ProductImage, uuid.UUID(first["images"][0]["id"]))
    assert "clean_background" in [o["op"] for o in row.processing_ops]
    assert min(await _corner(row)) >= 250
    act = (await db.execute(select(AIActivity).where(AIActivity.ref_id == row.id))).scalar_one()
    assert "làm sạch nền" in (act.summary or "")

    # hoàn tác → ảnh chỉ xoay + cắt vuông, nền về màu gốc
    row_id, first_id = row.id, first["images"][0]["id"]
    assert (await owner_client.post(f"/api/desk/control/activity/{act.id}/undo")).status_code == 200
    db.expire_all()
    row = await db.get(ProductImage, row_id)
    assert "clean_background" not in [o["op"] for o in row.processing_ops]
    assert max(await _corner(row)) < 245

    # chị tắt làm sạch nền → ảnh mới không làm trắng nền
    r = await owner_client.patch(f"/api/desk/control/settings/{CLEAN_BG_SETTING}", json={"value": False})
    assert r.status_code == 200, r.text
    second = (await owner_client.post(url, files={"file": ("b.jpg", jpeg(1200, 1600), "image/jpeg")})).json()
    new_id = next(i["id"] for i in second["images"] if i["id"] != first_id)
    row2 = await db.get(ProductImage, uuid.UUID(new_id))
    assert "clean_background" not in [o["op"] for o in row2.processing_ops]
    assert await control.get_setting(db, CLEAN_BG_SETTING) is False
