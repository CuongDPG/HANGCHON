"""g5 với driver thật trên máy chủ giả: ZNS lỗi → email dự phòng; lỗi tạm thời được cron gửi lại, lỗi vĩnh viễn thì
không; thiếu cấu hình không làm hỏng luồng đặt hàng."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app import control
from app.core.config import settings
from app.core.db import SessionLocal
from app.integrations import base
from app.integrations._zalo_token import ZaloTokenStore
from app.integrations.notify.zalo_zns import Driver as ZnsDriver
from app.modules.orders import jobs, notify
from app.modules.orders.models import Customer, Notification, Order
from tests.orders.conftest import cart, make_drop, make_product, place
from tests.test_notify_drivers import TEMPLATES, FakeSMTP, FakeZalo


@pytest.fixture
def real_drivers(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "notify_channel_drivers", "zalo_oa=zalo_zns,email=email")
    monkeypatch.setattr(settings, "zalo_zns_templates", TEMPLATES)
    monkeypatch.setattr(settings, "zalo_oa_access_token", "AT")

    def install(fake: FakeZalo) -> None:
        t = httpx.MockTransport(fake.handler)
        base._instances[("notify", "zalo_zns")] = ZnsDriver(
            transport=t, tokens=ZaloTokenStore(transport=t, path=str(tmp_path / "z.json"))
        )

    return install


async def _with_email(email: str | None) -> None:
    async with SessionLocal() as s:
        for c in (await s.execute(select(Customer))).scalars():
            c.email = email
        await s.commit()


async def test_zns_rejected_falls_back_to_email(client, owner_client, real_drivers, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeZalo(errors=[-108, -108])
    real_drivers(fake)
    async with SessionLocal() as s:
        await control.set_setting(s, "orders.notify_fallback_channels", ["email"])
        await s.commit()
    p = await make_product()
    d = await make_drop([(p, 100_000, None)])
    async with FakeSMTP() as smtp:
        monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
        monkeypatch.setattr(settings, "smtp_port", smtp.port)
        monkeypatch.setattr(settings, "smtp_tls", "none")
        o = await place(client, cart((p, 1, d)))  # khách chưa có email → chỉ thử ZNS
        await _with_email("lan@example.com")
        async with SessionLocal() as s:
            order = (await s.execute(select(Order).where(Order.code == o["code"]))).scalar_one()
            n2 = await notify.notify_order(s, order, "delivered")
            await s.commit()
        assert len(smtp.messages) == 1 and b"lan@example.com" in smtp.messages[0]
    async with SessionLocal() as s:
        first = (
            await s.execute(select(Notification).where(Notification.dedupe_key == f"order:{order.id}:order_received"))
        ).scalar_one()
    # mốc đầu: ZNS từ chối số (vĩnh viễn), chưa có email → lỗi, không gửi lại
    assert first.status == "failed" and "Zalo" in (first.error or "") and first.attempts == notify.MAX_ATTEMPTS
    # mốc sau: ZNS không có mẫu cho «delivered» → email; ghi lại lỗi kênh trước
    assert n2.status == "sent" and n2.channel == "email" and n2.recipient == "lan@example.com"
    assert "Chưa có mẫu ZNS" in (n2.error or "")
    assert len(fake.sent) == 1  # «delivered» không gọi Zalo vì thiếu mẫu


async def test_temporary_failure_is_retried_by_cron(client, real_drivers) -> None:  # type: ignore[no-untyped-def]
    fake = FakeZalo(errors=[-133, 0])  # 22h–7h: Zalo chặn, lần sau gửi được
    real_drivers(fake)
    p = await make_product()
    d = await make_drop([(p, 100_000, None)])
    await place(client, cart((p, 1, d)))
    async with SessionLocal() as s:
        n = (await s.execute(select(Notification))).scalar_one()
        assert n.status == "failed" and n.attempts == 1 and "22h" in (n.error or "")
    assert await jobs.retry_notifications({"db": SessionLocal}) == 1
    async with SessionLocal() as s:
        n = (await s.execute(select(Notification))).scalar_one()
        assert n.status == "sent" and n.attempts == 2 and n.external_id == "m-1"
    body = fake.sent[1].content.decode()
    assert '"template_id":"T100"' in body.replace(" ", "")  # gửi lại dựng ô mẫu từ đơn
    assert await jobs.retry_notifications({"db": SessionLocal}) == 0


async def test_unconfigured_driver_does_not_break_checkout(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "notify_channel_drivers", "zalo_oa=zalo_zns")
    monkeypatch.setattr(settings, "zalo_zns_templates", {})
    p = await make_product()
    d = await make_drop([(p, 100_000, None)])
    o = await place(client, cart((p, 1, d)))
    assert o["code"]
    async with SessionLocal() as s:
        n = (await s.execute(select(Notification))).scalar_one()
    assert n.status == "failed" and "ZALO_ZNS_TEMPLATES" in (n.error or "") and n.attempts == notify.MAX_ATTEMPTS


async def test_templates_screen_shows_channels_and_failures(client, owner_client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "notify_channel_drivers", "zalo_oa=zalo_zns,email=email")
    monkeypatch.setattr(settings, "zalo_zns_templates", {})
    monkeypatch.setattr(settings, "smtp_host", None)
    await owner_client.patch("/api/desk/control/settings/orders.notify_fallback_channels", json={"value": ["email"]})
    p = await make_product()
    d = await make_drop([(p, 100_000, None)])
    o = await place(client, cart((p, 1, d)))
    t = (await owner_client.get("/api/desk/orders/templates")).json()
    assert [(c["channel"], c["role"], c["driver"], c["ready"]) for c in t["channels"]] == [
        ("zalo_oa", "primary", "zalo_zns", False),
        ("email", "fallback", "email", False),
    ]
    assert "ZALO_ZNS_TEMPLATES" in t["channels"][0]["note"] and "SMTP_HOST" in t["channels"][1]["note"]
    (f,) = t["failed"]
    assert f["order_code"] == o["code"] and f["event_label"] == "Đã nhận đơn" and not f["will_retry"]
