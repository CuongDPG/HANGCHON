"""Thẻ «tích hợp thật / giả lập» và cảnh báo khởi động ở production khi còn driver `mock`."""

from __future__ import annotations

import logging

import httpx
import pytest

from app.core.config import Settings, settings

PROD_FERNET_KEY = "dGVzdC1vbmx5LXByb2QtZmVybmV0LWtleS0zMmJ5dGU="


def _prod(**kw) -> Settings:
    return Settings(app_env="prod", jwt_secret="x" * 40, owner_password="p" * 16,
                    secrets_encryption_key=PROD_FERNET_KEY, _env_file=None, **kw)  # fmt: skip


def test_prod_with_mock_starts_but_warns_each_integration(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s = _prod(payments_driver="sepay", notify_channel_drivers="zalo_oa=zalo_zns")
    assert s.app_env == "prod"  # không chặn khởi động
    text = caplog.text
    for kind in ("SOURCES", "SOCIAL", "SHIPPING", "NOTIFY", "MARKETPLACES", "EINVOICE"):
        assert f"{kind}_DRIVER=mock" in text
    assert "PAYMENTS_DRIVER" not in text  # đã nối thật
    assert "không tới khách" in text and "AI_PROVIDER=fake" in text


def test_no_warning_outside_prod(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.config"):
        Settings(app_env="dev", _env_file=None)
    assert "giả lập" not in caplog.text


def test_mock_integrations_counts_channel_drivers() -> None:
    s = Settings(_env_file=None, notify_driver="mock", notify_channel_drivers="zalo_oa=zalo_zns")
    assert s.integration_drivers("notify") == ["mock", "zalo_zns"]
    assert "notify" in s.mock_integrations()  # kênh chưa khai (sms, email) vẫn còn giả lập
    s = Settings(_env_file=None, notify_driver="email", notify_channel_drivers="zalo_oa=zalo_zns")
    assert "notify" not in s.mock_integrations()


async def test_integrations_endpoint_marks_mock_real_partial(
    owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "payments_driver", "sepay")
    monkeypatch.setattr(settings, "notify_channel_drivers", "zalo_oa=zalo_zns")
    rows = {i["kind"]: i for i in (await owner_client.get("/api/desk/control/integrations")).json()}
    assert rows["payments"]["is_mock"] is False and rows["payments"]["mock_effect"] is None
    assert rows["notify"]["partly_mock"] is True and rows["notify"]["drivers"] == ["mock", "zalo_zns"]
    assert rows["shipping"]["is_mock"] is True and "giả" in rows["shipping"]["mock_effect"]
    assert rows["storage"]["is_mock"] is False
    assert rows["einvoice"]["blocked_in_prod"] is False
    monkeypatch.setattr(settings, "app_env", "prod")
    rows = {i["kind"]: i for i in (await owner_client.get("/api/desk/control/integrations")).json()}
    assert rows["einvoice"]["blocked_in_prod"] is True
