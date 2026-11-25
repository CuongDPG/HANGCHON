"""Băm ảnh theo hình (difference hash, tự viết bằng Pillow) để nhận ra cùng một ảnh ở nhiều shop (b7, a3).

Khác băm theo byte: ảnh nén lại, đổi cỡ, đổi định dạng vẫn ra băm gần nhau. Hai ảnh coi là «cùng ảnh» khi khoảng
cách Hamming giữa hai băm 64 bit ≤ `SAME_IMAGE_DISTANCE`."""

from __future__ import annotations

import asyncio
import io
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from PIL import Image, UnidentifiedImageError

log = logging.getLogger("app.sourcing.imagehash")

HASH_SIZE = 8  # 8×8 = 64 bit → 16 ký tự hex
SAME_IMAGE_DISTANCE = 6
MAX_BYTES = 6 * 1024 * 1024
TIMEOUT = 6.0
MAX_IMAGES = 40
CONCURRENCY = 6


def dhash(data: bytes) -> str | None:
    """Difference hash: thu ảnh xám về 9×8, mỗi bit = điểm ảnh bên trái sáng hơn bên phải. Ảnh hỏng → None."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.draft("L", (HASH_SIZE * 8, HASH_SIZE * 8))  # JPEG giải mã nhỏ cho nhanh
            small = img.convert("L").resize((HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    px = small.tobytes()  # ảnh xám: mỗi điểm ảnh một byte
    bits = 0
    for row in range(HASH_SIZE):
        for col in range(HASH_SIZE):
            left = px[row * (HASH_SIZE + 1) + col]
            right = px[row * (HASH_SIZE + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:0{HASH_SIZE * HASH_SIZE // 4}x}"


def distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def same_image(a: str | None, b: str | None) -> bool:
    return bool(a and b and len(a) == len(b) and distance(a, b) <= SAME_IMAGE_DISTANCE)


def _public_host(host: str) -> bool:
    """Chặn tải ảnh từ địa chỉ nội bộ (URL ảnh đến từ dữ liệu nguồn, không tin được)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


async def fetch_image(url: str, client: httpx.AsyncClient) -> bytes | None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    if not await asyncio.to_thread(_public_host, u.hostname):
        return None
    try:
        async with client.stream("GET", url) as r:
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                return None
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf += chunk
                if len(buf) > MAX_BYTES:
                    return None
            return bytes(buf)
    except httpx.HTTPError:
        return None


async def hash_urls(urls: list[str]) -> dict[str, str]:
    """URL → băm cho những ảnh tải được (tối đa `MAX_IMAGES`, lỗi thì bỏ qua)."""
    todo = list(dict.fromkeys(u for u in urls if u))[:MAX_IMAGES]
    if not todo:
        return {}
    sem = asyncio.Semaphore(CONCURRENCY)
    out: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:

        async def one(url: str) -> None:
            async with sem:
                data = await fetch_image(url, client)
            h = dhash(data) if data else None
            if h:
                out[url] = h

        await asyncio.gather(*(one(u) for u in todo))
    return out
