"""Xử lý ảnh sản phẩm (e6) bằng Pillow — chỉ chỉnh ảnh thật chị chụp, không tạo ảnh giả.

Các bước: xoay theo EXIF → cân sáng nhẹ → làm sạch nền (chỉ khi nền sáng, đều màu; tắt được) → cắt vuông giữ chủ thể ở
giữa → các cỡ 1600/800/400 dạng webp + jpg.
Bản xử lý không mang EXIF (bỏ toạ độ GPS trong ảnh gốc). Ảnh gốc lưu ở `private/`, bản xử lý ở `public/`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
    ImageStat,
    UnidentifiedImageError,
)

from app.core.errors import BadRequest
from app.core.storage import get_storage, new_key

SIZES = (1600, 800, 400)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000  # chặn ảnh «bom giải nén»


@dataclass
class ProcessedImage:
    width: int
    height: int
    ops: list[dict[str, Any]] = field(default_factory=list)
    renditions: dict[int, dict[str, bytes]] = field(default_factory=dict)  # cỡ → {"webp": bytes, "jpg": bytes}


def open_image(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD_BYTES:
        raise BadRequest("Ảnh lớn quá 15 MB, chị chọn ảnh nhỏ hơn.", code="image_too_large")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise BadRequest("Ảnh có độ phân giải quá lớn.", code="image_too_large")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise BadRequest(
            "Không đọc được tệp ảnh (cần JPG, PNG, WEBP hoặc HEIC đã đổi sang JPG).", code="bad_image"
        ) from e
    return img


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB")


def balance_light(img: Image.Image) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Cân sáng nhẹ, không đổi màu: kéo giãn tương phản theo ĐỘ SÁNG (cùng một phép cho cả ba kênh, nên không ám màu),
    tối đa 15%; rồi chỉnh độ sáng về khoảng trung tính (giới hạn ±25%)."""
    ops: list[dict[str, Any]] = []
    out = img
    hist = img.convert("L").histogram()
    total = sum(hist)
    cut = total * 0.005
    lo = next(i for i in range(256) if sum(hist[: i + 1]) > cut)
    hi = next(i for i in range(255, -1, -1) if sum(hist[i:]) > cut)
    if hi - lo > 32:
        gain = min(1.15, 255 / (hi - lo))
        if gain > 1.01:
            mid = ImageStat.Stat(img.convert("L")).mean[0]  # giữ nguyên độ sáng trung bình
            lut = [max(0, min(255, round(mid + (v - mid) * gain))) for v in range(256)]
            out = img.point(lut * len(img.getbands()))
            ops.append({"op": "autocontrast", "gain": round(gain, 3)})
    mean = ImageStat.Stat(out.convert("L")).mean[0]
    if mean < 115 or mean > 232:  # ảnh nền trắng sáng là bình thường, chỉ hạ khi gần như cháy sáng
        target = 150 if mean < 115 else 215
        factor = round(max(0.8, min(1.25, target / max(mean, 1))), 3)
        out = ImageEnhance.Brightness(out).enhance(factor)
        ops.append({"op": "brightness", "factor": factor, "mean_before": round(mean, 1)})
    return out, ops


def subject_box(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Ước lượng khung chủ thể: điểm ảnh khác hẳn màu nền (trung vị viền ảnh). None = không tách được."""
    small = img.copy()
    small.thumbnail((160, 160))
    w, h = small.size
    px = small.load()
    border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)]
    border += [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    diff = ImageChops.difference(small, Image.new("RGB", small.size, bg)).convert("L")
    mask = diff.point(lambda v: 255 if v > 30 else 0)
    box = mask.getbbox()
    if not box:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw * bh < 0.01 * w * h or bw * bh > 0.97 * w * h:  # quá nhỏ (nhiễu) hoặc kín cả ảnh: không tin được
        return None
    sx, sy = img.width / w, img.height / h
    return (int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy))


def clean_background(img: Image.Image) -> tuple[Image.Image, dict[str, Any] | None]:
    """Làm sạch nền đơn giản (e6): nền sáng gần trắng hoặc xám nhạt, đều màu → đưa về trắng. Chỉ làm trắng vùng nền
    LIỀN với mép ảnh và gần màu nền (loang từ mép), nên không đụng vào món hàng ở giữa; không tách vật thể bằng AI,
    không vẽ thêm gì. Nền không đủ đơn giản (tối, có màu, lốm đốm) hoặc tách không chắc → giữ nguyên, trả None."""
    small = img.copy()
    small.thumbnail((240, 240))
    w, h = small.size
    if w < 16 or h < 16:
        return img, None
    px = small.load()
    border = [px[x, y] for x in range(w) for y in (0, 1, h - 2, h - 1)]
    border += [px[x, y] for y in range(2, h - 2) for x in (0, 1, w - 2, w - 1)]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    if lum < 175 or max(bg) - min(bg) > 24:  # nền tối hoặc có màu: không phải nền trắng/xám
        return img, None
    if lum >= 250 and max(bg) - min(bg) <= 3:  # đã trắng sẵn
        return img, None
    near = sum(max(abs(c[i] - bg[i]) for i in range(3)) <= 22 for c in border)
    if near < 0.85 * len(border):  # mép ảnh lốm đốm (bàn gỗ, vải hoa...): không đủ đơn giản
        return img, None
    diff = ImageChops.difference(small, Image.new("RGB", small.size, bg)).convert("L")
    flood = diff.point(lambda v: 255 if v <= 26 else 0)  # 255 = gần màu nền
    fpx = flood.load()
    seeds = [(x, 0) for x in range(0, w, 4)] + [(x, h - 1) for x in range(0, w, 4)]
    seeds += [(0, y) for y in range(0, h, 4)] + [(w - 1, y) for y in range(0, h, 4)]
    for x, y in seeds:  # loang từ mép: chỉ lấy nền liền với mép ảnh
        if fpx[x, y] == 255:
            ImageDraw.floodfill(flood, (x, y), 128)
    mask_small = flood.point(lambda v: 255 if v == 128 else 0)
    share = mask_small.histogram()[255] / (w * h)
    if share < 0.25 or share > 0.95:  # nền quá ít (ảnh cận) hoặc gần như cả ảnh (không thấy món): không chắc
        return img, None
    mask = mask_small.resize(img.size, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(2))
    out = Image.composite(Image.new("RGB", img.size, (255, 255, 255)), img, mask)
    return out, {"op": "clean_background", "background": list(bg), "share": round(share, 3)}


def square_crop(img: Image.Image, *, follow_subject: bool = True) -> tuple[Image.Image, dict[str, Any]]:
    w, h = img.size
    side = min(w, h)
    cx, cy = w / 2, h / 2
    box = subject_box(img) if follow_subject else None
    if box:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    left = int(max(0, min(w - side, cx - side / 2)))
    top = int(max(0, min(h - side, cy - side / 2)))
    crop = (left, top, left + side, top + side)
    return img.crop(crop), {"op": "crop", "box": list(crop), "subject": list(box) if box else None}


def process_photo(data: bytes, *, enhance: bool = True, clean_bg: bool = True) -> ProcessedImage:
    """`enhance=False` = chỉ xoay đúng chiều + cắt vuông chính giữa + đổi cỡ (dùng khi chị hoàn tác phần chỉnh).
    `clean_bg=False` = không làm sạch nền (chị tắt ở cài đặt)."""
    src = open_image(data)
    ops: list[dict[str, Any]] = []
    orientation = src.getexif().get(0x0112, 1)
    img = ImageOps.exif_transpose(src) or src
    if orientation not in (1, None):
        ops.append({"op": "exif_transpose", "orientation": orientation})
    img = _to_rgb(img)
    if enhance:
        img, light_ops = balance_light(img)
        ops += light_ops
        if clean_bg:
            img, bg_op = clean_background(img)
            if bg_op:
                ops.append(bg_op)
    img, crop_op = square_crop(img, follow_subject=enhance)
    ops.append(crop_op)
    img.info = {}  # bỏ mọi siêu dữ liệu của ảnh gốc (EXIF, XMP, chú thích JPEG — ảnh nhà cung cấp hay ghi tên shop)
    side = img.width
    out = ProcessedImage(width=side, height=side, ops=ops)
    for size in SIZES:
        if size > side and size != SIZES[-1]:
            continue
        r = img if side <= size else img.resize((size, size), Image.Resampling.LANCZOS)
        webp, jpg = io.BytesIO(), io.BytesIO()
        r.save(webp, "WEBP", quality=82, method=4)
        r.save(jpg, "JPEG", quality=85, optimize=True, progressive=True)
        out.renditions[min(size, side)] = {"webp": webp.getvalue(), "jpg": jpg.getvalue()}
    return out


async def store_renditions(prefix: str, processed: ProcessedImage) -> dict[str, dict[str, str]]:
    """Lưu các cỡ vào kho công khai. Trả {"800": {"webp": key, "jpg": key}, ...}."""
    storage = get_storage()
    files: dict[str, dict[str, str]] = {}
    for size, blobs in sorted(processed.renditions.items(), reverse=True):
        entry: dict[str, str] = {}
        for fmt, blob in blobs.items():
            key = new_key(f"{prefix}/{size}", fmt)
            await storage.put(key, blob, "image/webp" if fmt == "webp" else "image/jpeg")
            entry[fmt] = key
        files[str(size)] = entry
    return files


def rendition_files(ops: list[Any]) -> dict[str, dict[str, str]]:
    for op in ops or []:
        if isinstance(op, dict) and op.get("op") == "renditions":
            return op.get("files") or {}
    return {}


def pick(files: dict[str, dict[str, str]], size: int, fmt: str = "jpg") -> str | None:
    """Khoá của cỡ gần nhất ≥ `size` (không có thì cỡ lớn nhất)."""
    sizes = sorted(int(s) for s in files)
    if not sizes:
        return None
    best = next((s for s in sizes if s >= size), sizes[-1])
    return files[str(best)].get(fmt)


# ---- ảnh mẫu cho dữ liệu demo (không tải ảnh từ mạng) ------------------------------------------------------------

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
)


def _font(size: int) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, bool]:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size), True
    return ImageFont.load_default(size=size), False


def sample_photo(label: str, color: tuple[int, int, int], *, size: int = 1200, note: str = "Ảnh mẫu") -> bytes:
    """Ảnh mẫu: nền trung tính, một khối màu ở giữa (chủ thể) và tên món. Chỉ dùng cho dữ liệu demo."""
    from app.modules.catalog.textutil import normalize_vi

    img = Image.new("RGB", (size, int(size * 1.25)), (236, 235, 229))
    d = ImageDraw.Draw(img)
    w, h = img.size
    d.rounded_rectangle((w * 0.2, h * 0.16, w * 0.8, h * 0.7), radius=18, fill=color)
    font, unicode_ok = _font(int(size * 0.055))
    small, _ = _font(int(size * 0.032))
    text = label if unicode_ok else normalize_vi(label)
    tw = d.textlength(text, font=font)
    d.text(((w - tw) / 2, h * 0.76), text, fill=(28, 29, 34), font=font)
    nt = note if unicode_ok else normalize_vi(note)
    nw = d.textlength(nt, font=small)
    d.text(((w - nw) / 2, h * 0.84), nt, fill=(110, 112, 120), font=small)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()
