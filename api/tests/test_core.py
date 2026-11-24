from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.db import Base
from app.core.money import format_vnd, format_vnd_short, margin_pct, round_vnd, to_vnd
from app.core.pagination import PageParams, paginate
from app.core.storage import get_storage, new_key
from app.core.timeutil import local_day_bounds_utc, local_month_bounds_utc, month_key, to_local, week_start
from app.modules.control.models import AuditLog
from app.modules.control.schemas import AuditOut


def test_money_helpers() -> None:
    assert to_vnd("12.5", "3456.7") == 43209  # 43208.75 → half-up
    assert to_vnd(10, 1) == 10
    assert round_vnd(123_456) == 123_000
    assert round_vnd(123_500) == 124_000
    assert format_vnd(1234567) == "1.234.567 ₫"
    assert format_vnd(-5000) == "-5.000 ₫"
    assert format_vnd_short(1_250_000) == "1,25tr"
    assert format_vnd_short(85_000) == "85k"
    assert margin_pct(200_000, 150_000) == 25.0


def test_time_helpers() -> None:
    dt = datetime(2026, 11, 30, 18, 30, tzinfo=UTC)  # 01:30 ngày 1/12 giờ VN
    assert to_local(dt).day == 1
    assert month_key(dt) == "2026-12"
    start, end = local_month_bounds_utc("2026-12")
    assert start == datetime(2026, 11, 30, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 12, 31, 17, 0, tzinfo=UTC)
    s, e = local_day_bounds_utc(date(2026, 11, 25))
    assert (e - s).total_seconds() == 86400
    assert week_start(date(2026, 11, 26)) == date(2026, 11, 23)


def test_all_module_tables_registered() -> None:
    tables = set(Base.metadata.tables)
    expected = {
        # control
        "users", "autonomy_settings", "approval_items", "ai_runs", "ai_activity", "app_settings", "audit_log",
        # sourcing
        "sourcing_briefs", "sourcing_runs", "candidates", "trend_signals", "demand_signals",
        # assessment
        "assessments", "scoring_profiles", "review_digests", "market_prices", "comparisons",
        # selection
        "trial_notes", "selection_decisions", "selection_principles", "taste_profiles",
        # supply
        "suppliers", "cost_sheets", "price_proposals", "purchase_orders", "purchase_order_lines",
        "supplier_messages", "inbound_shipments", "provenance_documents",
        # catalog
        "categories", "products", "product_images", "drops", "drop_items", "inventory_items", "reviews",
        "find_requests", "find_request_votes",
        # orders
        "customers", "orders", "order_items", "payments", "shipments", "shipment_events", "returns", "notifications",
        # assistant / content / inbox / crm / finance
        "assistant_conversations", "assistant_messages",
        "voice_profiles", "content_drafts", "scheduled_posts", "media_assets", "post_metrics", "livestream_scripts",
        "channel_accounts", "threads", "messages", "reply_drafts",
        "customer_notes", "customer_tags", "broadcasts", "reorder_reminders", "referrals", "tester_invites",
        "ledger_entries", "expenses", "invoices", "weekly_reports", "backups",
    }  # fmt: skip
    assert expected <= tables, expected - tables


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_validation_error_is_vietnamese(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/desk/auth/login", json={"email": "khong-phai-email"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert "Dữ liệu chưa hợp lệ" in body["detail"]
    fields = {e["field"] for e in body["errors"]}
    assert {"email", "password"} <= fields


async def test_not_found_is_vietnamese(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/khong-co")
    assert r.status_code == 404
    assert r.json()["detail"] == "Không tìm thấy trang hoặc dữ liệu."


async def test_paginate(db: AsyncSession) -> None:
    for i in range(25):
        db.add(AuditLog(actor_kind="system", action=f"test.{i:02d}"))
    await db.commit()
    page = await paginate(db, select(AuditLog).order_by(AuditLog.action), PageParams(page=2, size=10), AuditOut)
    assert page.total == 25 and page.pages == 3 and page.page == 2
    assert [i.action for i in page.items][:2] == ["test.10", "test.11"]


async def test_local_storage_roundtrip_and_serving(client: httpx.AsyncClient, owner_client: httpx.AsyncClient) -> None:
    storage = get_storage()
    pub = await storage.put(new_key("public/test", "txt"), b"xin chao", "text/plain")
    priv = await storage.put(new_key("private/test", "txt"), b"bi mat", "text/plain")
    assert await storage.get(pub.key) == b"xin chao"
    r = await client.get(f"/api/files/{pub.key}")
    assert r.status_code == 200 and r.content == b"xin chao" and r.headers["content-type"].startswith("text/plain")
    assert (await client.get(f"/api/files/{priv.key}")).status_code == 401
    assert (await owner_client.get(f"/api/files/{priv.key}")).content == b"bi mat"
    assert (await client.get("/api/files/public/../../etc/passwd")).status_code in (404, 400)
    await storage.delete(pub.key)
    assert not await storage.exists(pub.key)


async def test_jobs_registry_and_eager_enqueue() -> None:
    calls: list[dict] = []

    @jobs.job("test.echo")
    async def echo(ctx: dict, value: int) -> int:
        assert "db" in ctx
        calls.append({"value": value})
        return value * 2

    @jobs.cron("test.nightly", hour={1}, minute={0})
    async def nightly(ctx: dict) -> None: ...

    try:
        assert await jobs.enqueue("test.echo", value=21) == 42
        assert calls == [{"value": 21}]
        assert "test.echo" in {f.name for f in jobs.build_functions()}
        assert "test.nightly" in {c.name for c in jobs.build_cron_jobs()}
    finally:
        jobs.JOBS.pop("test.echo", None)
        jobs.JOBS.pop("test.nightly", None)
        jobs.CRONS.pop("test.nightly", None)
