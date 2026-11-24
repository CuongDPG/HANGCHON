"""Tiện ích dùng chung cho test sourcing/assessment."""

from __future__ import annotations

import httpx

BRIEF = (
    "Tìm giá phơi đồ gấp gọn cho ban công nhỏ, inox không gỉ, dưới 300k, ưu tiên hàng Nhật hoặc xưởng Trung Quốc "
    "có đánh giá tốt"
)
API = "/api/desk/sourcing"


async def new_brief(client: httpx.AsyncClient, text: str = BRIEF) -> dict:
    r = await client.post(f"{API}/briefs", json={"text": text})
    assert r.status_code == 201, r.text
    return r.json()


async def scanned_brief(client: httpx.AsyncClient, text: str = BRIEF) -> tuple[dict, list[dict]]:
    b = await new_brief(client, text)
    r = await client.post(f"{API}/briefs/{b['id']}/run")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "succeeded", r.json()
    r = await client.get(f"{API}/briefs/{b['id']}/candidates", params={"size": 50})
    return b, r.json()["items"]


async def set_level(client: httpx.AsyncClient, action: str, level: str) -> None:
    r = await client.patch(f"/api/desk/control/autonomy/{action}", json={"level": level})
    assert r.status_code == 200, r.text
