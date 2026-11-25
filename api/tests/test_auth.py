from __future__ import annotations

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.control.models import AuditLog, User, UserRole
from app.modules.control.service import ensure_owner
from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD


async def test_login_sets_httponly_cookie_and_me(client: httpx.AsyncClient, owner: User) -> None:
    r = await client.post("/api/desk/auth/login", json={"email": OWNER_EMAIL.upper(), "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "owner"
    cookie = r.headers["set-cookie"]
    assert settings.cookie_name in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    me = await client.get("/api/desk/auth/me")
    assert me.status_code == 200 and me.json()["email"] == OWNER_EMAIL
    async with SessionLocal() as s:
        assert (await s.execute(select(AuditLog).where(AuditLog.action == "auth.login"))).scalar_one()


async def test_login_wrong_password(client: httpx.AsyncClient, owner: User) -> None:
    r = await client.post("/api/desk/auth/login", json={"email": OWNER_EMAIL, "password": "sai"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Email hoặc mật khẩu chưa đúng.", "code": "invalid_credentials"}


async def test_desk_requires_login(client: httpx.AsyncClient) -> None:
    for path in ("/api/desk/auth/me", "/api/desk/control/today", "/api/desk/bat-ky-module-nao/x"):
        r = await client.get(path)
        assert r.status_code == 401, path
        assert r.json()["code"] == "unauthorized"


async def test_logout_clears_cookie(owner_client: httpx.AsyncClient) -> None:
    r = await owner_client.post("/api/desk/auth/logout")
    assert r.status_code == 204
    assert (await owner_client.get("/api/desk/auth/me")).status_code == 401


async def test_bearer_token_also_works(client: httpx.AsyncClient, owner: User) -> None:
    from app.core.security import create_access_token

    token = create_access_token(owner.id, "owner", owner.password_hash)
    r = await client.get("/api/desk/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def test_inactive_user_rejected(owner_client: httpx.AsyncClient, owner: User) -> None:
    async with SessionLocal() as s:
        u = await s.get(User, owner.id)
        u.is_active = False
        await s.commit()
    assert (await owner_client.get("/api/desk/auth/me")).status_code == 401


async def test_require_owner(helper_client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    assert (await helper_client.get("/api/desk/control/today")).status_code == 200
    r = await helper_client.get("/api/desk/users")
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    assert (await owner_client.get("/api/desk/users")).status_code == 200


async def test_owner_creates_helper_account(owner_client: httpx.AsyncClient, client: httpx.AsyncClient) -> None:
    r = await owner_client.post(
        "/api/desk/users", json={"email": "moi@test.local", "name": "Bạn phụ", "password": "12345678"}
    )
    assert r.status_code == 201 and r.json()["role"] == "helper"
    dup = await owner_client.post(
        "/api/desk/users", json={"email": "moi@test.local", "name": "X", "password": "12345678"}
    )
    assert dup.status_code == 409
    login = await client.post("/api/desk/auth/login", json={"email": "moi@test.local", "password": "12345678"})
    assert login.status_code == 200
    uid = r.json()["id"]
    r = await owner_client.patch(f"/api/desk/users/{uid}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False


async def test_change_password(owner_client: httpx.AsyncClient, client: httpx.AsyncClient) -> None:
    r = await owner_client.post(
        "/api/desk/auth/password", json={"current_password": OWNER_PASSWORD, "new_password": "matkhau-moi-456"}
    )
    assert r.status_code == 204
    ok = await client.post("/api/desk/auth/login", json={"email": OWNER_EMAIL, "password": "matkhau-moi-456"})
    assert ok.status_code == 200


async def test_ensure_owner_is_idempotent() -> None:
    async with SessionLocal() as s:
        a = await ensure_owner(s, "Chu@Test.Local", "12345678")
        b = await ensure_owner(s, "chu@test.local", "khac-han")
        await s.commit()
    assert a is not None and b is not None and a.id == b.id and a.role == UserRole.OWNER
