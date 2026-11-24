from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.db import SessionLocal
from app.seed import seed


async def test_seed_is_idempotent_and_owner_can_login(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "owner_email", "seed@test.local")
    monkeypatch.setattr(settings, "owner_password", "seed-pass-123")
    async with SessionLocal() as db:
        first = await seed(db)
        await db.commit()
    async with SessionLocal() as db:
        second = await seed(db)
        await db.commit()
    assert first["owner"] == 1 and first["categories"] == 5 and first["scoring_profiles"] == 1
    assert all(v == 0 for v in second.values())
    r = await client.post("/api/desk/auth/login", json={"email": "seed@test.local", "password": "seed-pass-123"})
    assert r.status_code == 200 and r.json()["role"] == "owner"
