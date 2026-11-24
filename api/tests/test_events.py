"""Kênh sự kiện giữa các module."""

import pytest
from sqlalchemy import text

from app.core import events


@pytest.fixture(autouse=True)
def _clean():
    events.clear("test.ping")
    yield
    events.clear("test.ping")


async def test_emit_runs_subscribers_in_order(db):
    seen: list[str] = []

    @events.on("test.ping")
    async def first(db, payload):
        seen.append(f"first:{payload['n']}")

    @events.on("test.ping")
    async def second(db, payload):
        seen.append(f"second:{payload['n']}")

    assert await events.emit("test.ping", {"n": 1}, db=db) == 2
    assert seen == ["first:1", "second:1"]


async def test_failing_subscriber_does_not_break_emitter(db):
    @events.on("test.ping")
    async def boom(db, payload):
        await db.execute(text("select 1/0"))

    @events.on("test.ping")
    async def fine(db, payload):
        await db.execute(text("select 1"))

    assert await events.emit("test.ping", {}, db=db) == 1
    # phiên của người phát vẫn dùng được sau khi một người nghe lỗi
    assert (await db.execute(text("select 41 + 1"))).scalar_one() == 42


async def test_emit_without_subscribers(db):
    assert await events.emit("test.nobody", {}, db=db) == 0
