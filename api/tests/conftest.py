"""Fixture dùng chung cho mọi test.

- CSDL test thật: `hangchon_test_<thư mục gốc worktree>` (tự tạo nếu chưa có), dựng bảng bằng create_all một lần
  mỗi phiên test, xoá sạch dữ liệu (TRUNCATE) sau mỗi test.
- AI luôn dùng provider `fake`; việc nền chạy ngay trong tiến trình (JOBS_EAGER).
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

# ---- môi trường phải đặt TRƯỚC khi import app --------------------------------------------------------------------
API_DIR = Path(__file__).resolve().parents[1]
WORKTREE = API_DIR.parent.name
TEST_DB = "hangchon_test_" + re.sub(r"[^a-z0-9]+", "_", WORKTREE.lower()).strip("_")
PG_BASE = os.environ.get("TEST_PG_URL", "postgresql+asyncpg://hangchon:hangchon@localhost:5442")
os.environ.update(
    APP_ENV="test",
    DATABASE_URL=f"{PG_BASE}/{TEST_DB}",
    AI_PROVIDER="fake",
    ANTHROPIC_API_KEY="",
    JOBS_EAGER="true",
    CREATE_OWNER_ON_STARTUP="false",
    STORAGE_DRIVER="local",
    STORAGE_LOCAL_DIR=tempfile.mkdtemp(prefix="hangchon-test-storage-"),
    AI_MONTHLY_BUDGET_VND="1500000",
    JWT_SECRET="test-secret-test-secret-test-secret-32",
    SOURCES_DRIVER="mock",
    SOCIAL_DRIVER="mock",
    PAYMENTS_DRIVER="mock",
    SHIPPING_DRIVER="mock",
    NOTIFY_DRIVER="mock",
    MARKETPLACES_DRIVER="mock",
    EINVOICE_DRIVER="mock",
)

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.discovery import discover_modules  # noqa: E402
from app.integrations import reset_drivers  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.modules.control.models import User, UserRole  # noqa: E402

OWNER_EMAIL = "chi@test.local"
OWNER_PASSWORD = "matkhau-chi-123"
HELPER_EMAIL = "phu@test.local"
HELPER_PASSWORD = "matkhau-phu-123"


async def ensure_database(name: str) -> None:
    """Tạo CSDL nếu chưa có (kết nối vào CSDL `postgres`)."""
    dsn = PG_BASE.replace("postgresql+asyncpg://", "postgresql://") + "/postgres"
    conn = await asyncpg.connect(dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def drop_database(name: str) -> None:
    dsn = PG_BASE.replace("postgresql+asyncpg://", "postgresql://") + "/postgres"
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    await ensure_database(TEST_DB)
    discover_modules()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean() -> AsyncIterator[None]:
    reset_drivers()
    yield
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    reset_drivers()


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Phiên CSDL cho test; tự commit khi test xong nếu chưa commit."""
    async with SessionLocal() as session:
        yield session
        await session.commit()


async def _make_user(email: str, password: str, role: UserRole, name: str) -> User:
    from app.core.security import hash_password

    async with SessionLocal() as s:
        user = User(email=email, name=name, password_hash=hash_password(password), role=role)
        s.add(user)
        await s.commit()
        return user


@pytest.fixture
async def owner() -> User:
    return await _make_user(OWNER_EMAIL, OWNER_PASSWORD, UserRole.OWNER, "Chị")


@pytest.fixture
async def helper() -> User:
    return await _make_user(HELPER_EMAIL, HELPER_PASSWORD, UserRole.HELPER, "Người phụ")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Client chưa đăng nhập (khách / webhook)."""
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(email: str, password: str) -> httpx.AsyncClient:
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test")
    r = await c.post("/api/desk/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
async def owner_client(owner: User) -> AsyncIterator[httpx.AsyncClient]:
    """Client đã đăng nhập bằng tài khoản chị (owner)."""
    c = await _login(OWNER_EMAIL, OWNER_PASSWORD)
    yield c
    await c.aclose()


@pytest.fixture
async def helper_client(helper: User) -> AsyncIterator[httpx.AsyncClient]:
    c = await _login(HELPER_EMAIL, HELPER_PASSWORD)
    yield c
    await c.aclose()


@pytest.fixture
def fake_ai() -> Iterator[dict]:
    """Đăng ký hàm giả tạm thời: `fake_ai["module.viec"] = lambda inp: {...}`; tự gỡ sau test."""
    from app.ai.registry import FAKES

    before = dict(FAKES)
    yield FAKES
    FAKES.clear()
    FAKES.update(before)


@pytest.fixture
def temp_registry() -> Iterator[None]:
    """Cho phép test đăng ký action/intent/stat provider/setting tạm thời; khôi phục sổ đăng ký sau test."""
    from app.modules.control import registry as r

    saved = {n: dict(getattr(r, n)) for n in ("ACTIONS", "INTENTS", "STAT_PROVIDERS", "SETTINGS")}
    yield
    for n, v in saved.items():
        getattr(r, n).clear()
        getattr(r, n).update(v)
