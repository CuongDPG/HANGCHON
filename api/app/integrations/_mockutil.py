"""Tiện ích cho driver mock: dữ liệu giả **xác định** theo hạt giống (cùng đầu vào → cùng kết quả)."""

from __future__ import annotations

import hashlib
import random


def rng(*parts: object) -> random.Random:
    seed = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def short_id(*parts: object, length: int = 10) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:length]


def placeholder_image(text: str, n: int = 0) -> str:
    """Ảnh giữ chỗ cho mock (không phải ảnh sản phẩm thật)."""
    return f"https://placehold.co/800x800/E1E3EC/2E3F8F/png?text={short_id(text, n, length=6)}"
