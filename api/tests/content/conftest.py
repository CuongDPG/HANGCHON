"""Dữ liệu dựng nhanh cho test module content (tên món là ví dụ)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.db import SessionLocal
from app.core.timeutil import now_utc
from app.modules.catalog.models import Drop, DropItem, DropStatus, Product, ProductImage, ProductStatus


async def make_product(**kw) -> Product:
    async with SessionLocal() as db:
        n = uuid.uuid4().hex[:6]
        p = Product(
            slug=kw.pop("slug", f"binh-giu-nhiet-{n}"),
            name=kw.pop("name", "Bình giữ nhiệt 480 ml"),
            subtitle="Inox 304, nắp tháo rời",
            status=kw.pop("status", ProductStatus.PUBLISHED),
            published_at=now_utc(),
            price_vnd=kw.pop("price_vnd", 385_000),
            compare_at_price_vnd=kw.pop("compare_at_price_vnd", None),
            trial_days=kw.pop("trial_days", 21),
            considered_count=kw.pop("considered_count", 5),
            reason_selected=kw.pop(
                "reason_selected", "Sáng pha trà, 5 giờ chiều vẫn còn nóng. Nắp tháo rời nên rửa xong không còn mùi."
            ),
            not_satisfied=kw.pop("not_satisfied", "Hơi nặng khi bỏ túi xách nhỏ."),
            specs=[{"label": "Dung tích", "value": "480 ml"}, {"label": "Chất liệu", "value": "Inox 304"}],
            **kw,
        )
        db.add(p)
        await db.flush()
        for i in range(3):
            db.add(
                ProductImage(product_id=p.id, original_key=f"public/test/{n}-{i}.jpg", position=i, is_primary=i == 0)
            )
        await db.commit()
        return p


async def make_drop(products: list[Product]) -> Drop:
    async with SessionLocal() as db:
        n = uuid.uuid4().hex[:4]
        d = Drop(
            code=f"D{n}",
            slug=f"dot-{n}",
            title="Đợt 12: đồ bếp đã thử",
            status=DropStatus.OPEN,
            opens_at=now_utc(),
            closes_at=now_utc() + timedelta(days=3),
            deposit_pct=30,
        )
        db.add(d)
        await db.flush()
        for i, p in enumerate(products):
            db.add(DropItem(drop_id=d.id, product_id=p.id, price_vnd=p.price_vnd, slots_total=40, position=i))
        await db.commit()
        return d


@pytest.fixture
def product_factory():
    return make_product


@pytest.fixture
def drop_factory():
    return make_drop
