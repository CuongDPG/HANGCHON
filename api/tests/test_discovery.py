"""Chứng minh quy ước tự khám phá: thêm MỘT THƯ MỤC module là có router + bảng + action + job + tác vụ AI,
không sửa tệp dùng chung nào."""

from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import httpx
import pytest

import app.modules as modules_pkg
from app.ai.registry import FAKES, TASKS
from app.core import jobs
from app.core.db import Base, SessionLocal, engine
from app.core.discovery import discover_modules
from app.main import create_app
from app.modules.control.registry import ACTIONS, STAT_PROVIDERS
from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD

FILES = {
    "__init__.py": "",
    "models.py": """
        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column

        from app.core.db import Base, Timestamps, UUIDPk


        class Widget(UUIDPk, Timestamps, Base):
            __tablename__ = "zz_test_widgets"
            name: Mapped[str] = mapped_column(String(50))
    """,
    "router.py": """
        import uuid

        from fastapi import APIRouter, status
        from pydantic import BaseModel, ConfigDict
        from sqlalchemy import select

        from app.core.db import DbSession
        from app.core.deps import CurrentUser
        from app.core.pagination import Page, Paginated, paginate

        from .models import Widget

        router = APIRouter(prefix="/api/desk/widgets", tags=["widgets"])


        class WidgetIn(BaseModel):
            name: str


        class WidgetOut(BaseModel):
            model_config = ConfigDict(from_attributes=True)
            id: uuid.UUID
            name: str


        @router.post("", response_model=WidgetOut, status_code=status.HTTP_201_CREATED)
        async def create(body: WidgetIn, _: CurrentUser, db: DbSession) -> Widget:
            w = Widget(name=body.name)
            db.add(w)
            await db.flush()
            return w


        @router.get("", response_model=Paginated[WidgetOut])
        async def list_(_: CurrentUser, db: DbSession, page: Page) -> Paginated[WidgetOut]:
            return await paginate(db, select(Widget).order_by(Widget.name), page, WidgetOut)
    """,
    "actions.py": """
        from app import control


        control.register_action("widgets.tidy", "Dọn widget", "Thử", default="auto")


        @control.handler("widgets.tidy")
        async def _tidy(ctx):
            return {"tidied": ctx.payload["n"]}


        @control.stat_provider("widgets.count")
        async def _count(db):
            return control.Stat(key="widgets.count", label="Số widget", value=7)
    """,
    "jobs.py": """
        from app.core.jobs import job


        @job("widgets.rebuild")
        async def rebuild(ctx, n: int) -> int:
            return n + 1
    """,
    "ai_tasks.py": """
        from pydantic import BaseModel

        from app import ai


        class NameOut(BaseModel):
            name: str


        ai.task("widgets.name_it", system="Đặt tên widget.")


        @ai.fake("widgets.name_it")
        def _fake(inp):
            return NameOut(name="Widget " + inp["hint"])
    """,
}


@pytest.fixture
def widgets_module(tmp_path: Path, temp_registry: None):
    pkg = tmp_path / "widgets"
    pkg.mkdir()
    for name, body in FILES.items():
        (pkg / name).write_text(textwrap.dedent(body))
    modules_pkg.__path__.append(str(tmp_path))
    importlib.invalidate_caches()
    try:
        yield discover_modules(refresh=True)
    finally:
        modules_pkg.__path__.remove(str(tmp_path))
        table = Base.metadata.tables.get("zz_test_widgets")
        if table is not None:
            Base.metadata.remove(table)
        for mod in [m for m in sys.modules if m.startswith("app.modules.widgets")]:
            del sys.modules[mod]
        jobs.JOBS.pop("widgets.rebuild", None)
        TASKS.pop("widgets.name_it", None)
        FAKES.pop("widgets.name_it", None)
        discover_modules(refresh=True)


async def test_new_module_folder_is_wired_automatically(widgets_module, owner) -> None:
    widget = next(m for m in widgets_module if m.name == "widgets")
    assert set(widget.parts) == {"models", "actions", "ai_tasks", "jobs", "router"}
    assert "zz_test_widgets" in Base.metadata.tables
    assert "widgets.tidy" in ACTIONS and "widgets.count" in STAT_PROVIDERS
    assert "widgets.rebuild" in jobs.JOBS and "widgets.name_it" in TASKS

    table = Base.metadata.tables["zz_test_widgets"]
    async with engine.begin() as conn:
        await conn.run_sync(table.create)
    try:
        app = create_app()
        assert "/api/desk/widgets" in app.openapi()["paths"]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/api/desk/widgets")).status_code == 401  # lưới an toàn /api/desk
            await c.post("/api/desk/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
            assert (await c.post("/api/desk/widgets", json={"name": "B"})).status_code == 201
            assert (await c.post("/api/desk/widgets", json={"name": "A"})).status_code == 201
            page = (await c.get("/api/desk/widgets")).json()
            assert page["total"] == 2 and [w["name"] for w in page["items"]] == ["A", "B"]
            today = (await c.get("/api/desk/control/today")).json()
            assert any(s["key"] == "widgets.count" and s["value"] == 7 for s in today["stats"])

        from app import ai, control

        async with SessionLocal() as db:
            out = await control.propose("widgets.tidy", "Dọn", {"n": 3}, db=db)
            await db.commit()
        assert out.status == "applied" and out.result == {"tidied": 3}
        assert await jobs.enqueue("widgets.rebuild", n=1) == 2
        from pydantic import BaseModel

        class NameOut(BaseModel):
            name: str

        assert (await ai.run("widgets.name_it", {"hint": "xanh"}, NameOut)).output.name == "Widget xanh"
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(table.drop)
