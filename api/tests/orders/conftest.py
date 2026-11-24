"""Fixture riêng cho test orders: tạo nhanh sản phẩm / đợt / tồn kho (bảng catalog — chỉ để dựng dữ liệu thử),
bắt sự kiện đã phát, giỏ hàng mẫu."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.db import SessionLocal
from app.core.timeutil import local_today, now_utc
from app.integrations import get_driver
from app.modules.catalog.models import Drop, DropItem, DropStatus, InventoryItem, Product, ProductStatus, SaleMode

ADDRESS = {"address_line": "12 Ngõ Mẫu", "ward": "Phường Ví Dụ", "province": "Hà Nội"}
PHONE = "0900000101"


async def make_product(
    *, name: str = "Bình giữ nhiệt 480 ml", price: int = 385_000, mode: SaleMode = SaleMode.DROP, weight: int = 400,
    status: ProductStatus = ProductStatus.PUBLISHED,
) -> Product:  # fmt: skip
    async with SessionLocal() as s:
        p = Product(
            slug=f"sp-{uuid.uuid4().hex[:8]}", name=name, price_vnd=price, sale_mode=mode, weight_grams=weight,
            status=status, sku=f"SKU-{uuid.uuid4().hex[:6].upper()}", landed_cost_vnd=price // 2,
        )  # fmt: skip
        s.add(p)
        await s.commit()
        return p


async def make_drop(
    items: list[tuple[Product, int, int | None]], *, status: DropStatus = DropStatus.OPEN, deposit_pct: int | None = None,
    closes_in: timedelta = timedelta(days=2), arrival_in_days: int = 14, max_per_order: int | None = None,
) -> Drop:  # fmt: skip
    """items: (sản phẩm, giá trong đợt, số suất | None)."""
    async with SessionLocal() as s:
        d = Drop(
            code=f"DOT-{uuid.uuid4().hex[:4].upper()}", slug=f"dot-{uuid.uuid4().hex[:8]}", title="Đợt thử",
            status=status, opens_at=now_utc() - timedelta(days=1), closes_at=now_utc() + closes_in,
            expected_arrival_date=local_today() + timedelta(days=arrival_in_days), deposit_pct=deposit_pct,
        )  # fmt: skip
        d.items = [
            DropItem(product_id=p.id, price_vnd=price, slots_total=slots, position=i, max_per_order=max_per_order)
            for i, (p, price, slots) in enumerate(items)
        ]
        s.add(d)
        await s.commit()
        return d


async def make_inventory(product: Product, on_hand: int, *, threshold: int | None = 2) -> InventoryItem:
    async with SessionLocal() as s:
        inv = InventoryItem(product_id=product.id, on_hand=on_hand, low_stock_threshold=threshold)
        s.add(inv)
        await s.commit()
        return inv


def cart(*lines: tuple[Product, int, Drop | None]) -> list[dict[str, Any]]:
    return [{"product_id": str(p.id), "drop_id": str(d.id) if d else None, "quantity": q} for p, q, d in lines]


def checkout_body(items: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    return {
        "items": items,
        "name": "Nguyễn Thị Lan",
        "phone": PHONE,
        "payment_method": "bank_transfer",
        **ADDRESS,
        **kw,
    }


async def place(client: httpx.AsyncClient, items: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    r = await client.post("/api/store/orders", json=checkout_body(items, **kw))
    assert r.status_code == 201, r.text
    return r.json()


async def send_transfer(
    client: httpx.AsyncClient, amount: int, content: str, external_id: str | None = None
) -> httpx.Response:
    """Giả lập webhook chuyển khoản của driver mock (ký HMAC)."""
    pay = get_driver("payments")
    t = pay.simulate_transfer(amount, content)
    if external_id:
        t = t.model_copy(update={"external_id": external_id})
    body = json.dumps({"transfers": [t.model_dump(mode="json")]}).encode()
    return await client.post(
        "/api/hooks/payments/mock",
        content=body,
        headers={"X-Mock-Signature": pay.sign(body), "content-type": "application/json"},
    )


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, dict[str, Any]]]]:
    """Ghi lại mọi sự kiện được phát (vẫn chạy người nghe thật)."""
    seen: list[tuple[str, dict[str, Any]]] = []
    original = events.emit

    async def spy(name: str, payload: dict[str, Any], *, db: AsyncSession) -> int:
        seen.append((name, payload))
        return await original(name, payload, db=db)

    monkeypatch.setattr(events, "emit", spy)
    yield seen


def names(seen: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [n for n, _ in seen]
