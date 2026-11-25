"""Driver báo tin thật (g5) bằng máy chủ giả — không gọi Zalo / máy chủ email thật.

Zalo ZNS (ZBS Template Message): HTTP giả (`httpx.MockTransport`). Email: máy chủ SMTP giả tối thiểu chạy trên
127.0.0.1 (asyncio), driver dùng `smtplib` thật nói chuyện với nó."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import settings
from app.core.enums import Channel
from app.integrations import notify as notify_api
from app.integrations._zalo_token import ZaloTokenStore
from app.integrations.notify import OutboundNotification
from app.integrations.notify.email import Driver as EmailDriver
from app.integrations.notify.zalo_zns import Driver as ZnsDriver
from app.integrations.notify.zalo_zns import normalize_phone

TEMPLATES = {"order_received": {"template_id": "T100", "params": {"customer_name": "ten", "order_code": "ma_don"}}}


def _msg(**kw: object) -> OutboundNotification:
    base: dict[str, object] = {
        "channel": Channel.ZALO_OA, "to": "0912345678", "text": "Đã nhận đơn HC-1", "kind": "order_received",
        "data": {"ten": "Lan", "ma_don": "HC-1"},
    }  # fmt: skip
    return OutboundNotification(**{**base, **kw})


class FakeZalo:
    """Máy chủ Zalo giả: trả lần lượt các mã lỗi trong `errors` cho API gửi tin; OAuth trả token mới."""

    def __init__(self, errors: list[int] | None = None, oauth_ok: bool = True) -> None:
        self.errors = list(errors or [0])
        self.oauth_ok = oauth_ok
        self.sent: list[httpx.Request] = []
        self.oauth: list[httpx.Request] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        if "oauth.zaloapp.com" in str(req.url):
            self.oauth.append(req)
            if not self.oauth_ok:
                return httpx.Response(200, json={"error": -14014, "error_description": "Invalid refresh token"})
            return httpx.Response(
                200, json={"access_token": "AT-NEW", "refresh_token": "RT-NEW", "expires_in": "90000"}
            )
        self.sent.append(req)
        code = self.errors.pop(0) if self.errors else 0
        if code == 0:
            return httpx.Response(200, json={"error": 0, "message": "Success", "data": {"msg_id": "m-1"}})
        return httpx.Response(200, json={"error": code, "message": "fail"})


@pytest.fixture
def zns(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "zalo_zns_templates", TEMPLATES)
    monkeypatch.setattr(settings, "zalo_oa_access_token", "AT-OLD")
    monkeypatch.setattr(settings, "zalo_oa_refresh_token", "RT-OLD")
    monkeypatch.setattr(settings, "zalo_app_id", "123")
    monkeypatch.setattr(settings, "zalo_app_secret", "app-secret")

    def make(fake: FakeZalo) -> ZnsDriver:
        t = httpx.MockTransport(fake.handler)
        return ZnsDriver(transport=t, tokens=ZaloTokenStore(transport=t, path=str(tmp_path / "zalo.json")))

    return make


def test_normalize_phone() -> None:
    assert normalize_phone("0912 345 678") == normalize_phone("+84912345678") == "84912345678"
    assert normalize_phone("12345") is None and normalize_phone("zalo-user") is None


async def test_zns_sends_template_by_phone(zns) -> None:  # type: ignore[no-untyped-def]
    fake = FakeZalo()
    res = await zns(fake).send(_msg())
    assert res.status == "sent" and res.external_id == "m-1"
    req = fake.sent[0]
    assert str(req.url) == "https://business.openapi.zalo.me/message/template"
    assert req.headers["access_token"] == "AT-OLD"
    body = json.loads(req.content)
    assert body["phone"] == "84912345678" and body["template_id"] == "T100"
    assert body["template_data"] == {"customer_name": "Lan", "order_code": "HC-1"}
    assert body["tracking_id"].isalnum() and len(body["tracking_id"]) <= 48 and "mode" not in body


async def test_zns_sends_by_oa_user_id_when_no_phone(zns) -> None:  # type: ignore[no-untyped-def]
    fake = FakeZalo()
    res = await zns(fake).send(_msg(to="3485904339058348590"))
    assert res.status == "sent"
    assert str(fake.sent[0].url) == "https://openapi.zalo.me/v3.0/oa/message/template"
    assert json.loads(fake.sent[0].content)["user_id"] == "3485904339058348590"


async def test_zns_refreshes_expired_token_and_persists(zns, tmp_path) -> None:  # type: ignore[no-untyped-def]
    fake = FakeZalo(errors=[-124, 0])
    driver = zns(fake)
    res = await driver.send(_msg())
    assert res.status == "sent" and [r.headers["access_token"] for r in fake.sent] == ["AT-OLD", "AT-NEW"]
    form = {k: v[0] for k, v in parse_qs(fake.oauth[0].content.decode()).items()}
    assert form == {"refresh_token": "RT-OLD", "app_id": "123", "grant_type": "refresh_token"}
    assert fake.oauth[0].headers["secret_key"] == "app-secret"
    saved = json.loads((tmp_path / "zalo.json").read_text())
    assert saved["access_token"] == "AT-NEW" and saved["refresh_token"] == "RT-NEW"
    assert oct(os.stat(tmp_path / "zalo.json").st_mode & 0o777) == "0o600"
    # tiến trình khác đọc lại tệp: dùng token mới, không làm mới lần nữa
    other = ZaloTokenStore(transport=httpx.MockTransport(fake.handler), path=str(tmp_path / "zalo.json"))
    assert await other.access_token() == "AT-NEW" and len(fake.oauth) == 1


async def test_zns_refresh_rejected_is_clear_config_error(zns, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "notify_channel_drivers", "zalo_oa=zalo_zns")
    fake = FakeZalo(errors=[-124], oauth_ok=False)
    notify_api_driver = zns(fake)
    from app.integrations import base

    base._instances[("notify", "zalo_zns")] = notify_api_driver
    res = await notify_api.send(_msg())
    assert res.status == "failed" and not res.retryable
    assert "refresh token" in (res.error or "") and "ZALO_OA_REFRESH_TOKEN" in (res.error or "")


@pytest.mark.parametrize(
    ("code", "retryable", "phrase"),
    [
        (-133, True, "22h"),
        (-144, True, "hạn mức"),
        (-108, False, "Số điện thoại"),
        (-131, False, "chưa được Zalo duyệt"),
    ],
)
async def test_zns_error_classification(zns, code: int, retryable: bool, phrase: str) -> None:  # type: ignore[no-untyped-def]
    res = await zns(FakeZalo(errors=[code])).send(_msg())
    assert res.status == "failed" and res.retryable is retryable and phrase in (res.error or "")


async def test_zns_missing_config_and_params(zns, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    fake = FakeZalo()
    d = zns(fake)
    res = await d.send(_msg(kind="delivered"))
    assert res.status == "failed" and not res.retryable and "Chưa có mẫu ZNS" in (res.error or "")
    res = await d.send(_msg(data={"ten": "Lan"}))
    assert not res.retryable and "Thiếu giá trị «ma_don»" in (res.error or "")
    res = await d.send(_msg(to="khong-phai-so"))
    assert not res.retryable and "số điện thoại" in (res.error or "")
    assert fake.sent == []
    monkeypatch.setattr(settings, "zalo_zns_templates", {})
    assert "ZALO_ZNS_TEMPLATES" in (d.missing_config() or "")


async def test_send_routes_by_channel_and_reports_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "notify_channel_drivers", "email=email,zalo_oa=khong_co")
    monkeypatch.setattr(settings, "smtp_host", None)
    res = await notify_api.send(OutboundNotification(channel=Channel.EMAIL, to="a@example.com", text="x"))
    assert res.status == "failed" and not res.retryable and "SMTP_HOST" in (res.error or "")
    res = await notify_api.send(_msg())
    assert res.status == "failed" and not res.retryable and "khong_co" in (res.error or "")
    # kênh không khai → NOTIFY_DRIVER (mock)
    assert notify_api.driver_name_for(Channel.SMS) == "mock"


# ---- email ---------------------------------------------------------------------------------------------------------


class FakeSMTP:
    """Máy chủ SMTP giả: người nhận chứa «busy» → 451 (tạm thời), «nouser» → 550 (vĩnh viễn)."""

    def __init__(self) -> None:
        self.messages: list[bytes] = []
        self.server: asyncio.base_events.Server | None = None
        self.port = 0

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        def say(line: str) -> None:
            writer.write(f"{line}\r\n".encode())

        say("220 fake ESMTP")
        await writer.drain()
        data_mode, buf = False, b""
        while line := await reader.readline():
            if data_mode:
                if line in (b".\r\n", b".\n"):
                    self.messages.append(buf)
                    data_mode, buf = False, b""
                    say("250 2.0.0 queued")
                else:
                    buf += line
            else:
                cmd = line.decode(errors="replace").strip()
                up = cmd.upper()
                if up.startswith(("EHLO", "HELO")):
                    say("250 fake")
                elif up.startswith("MAIL FROM"):
                    say("250 ok")
                elif up.startswith("RCPT TO"):
                    if "busy" in cmd:
                        say("451 4.3.0 try again later")
                    elif "nouser" in cmd:
                        say("550 5.1.1 no such user")
                    else:
                        say("250 ok")
                elif up == "DATA":
                    data_mode = True
                    say("354 go ahead")
                elif up == "QUIT":
                    say("221 bye")
                    await writer.drain()
                    break
                else:
                    say("250 ok")
            await writer.drain()
        writer.close()

    async def __aenter__(self) -> FakeSMTP:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()


@pytest.fixture
async def smtp(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeSMTP]:
    async with FakeSMTP() as server:
        monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
        monkeypatch.setattr(settings, "smtp_port", server.port)
        monkeypatch.setattr(settings, "smtp_tls", "none")
        monkeypatch.setattr(settings, "smtp_user", None)
        monkeypatch.setattr(settings, "smtp_from", "Hàng Chọn <shop@example.com>")
        yield server


async def test_email_sends_text_and_html(smtp: FakeSMTP) -> None:
    msg = OutboundNotification(
        channel=Channel.EMAIL, to="lan@example.com", text="Đơn HC-1 đã giao xong.\nCảm ơn bạn!",
        subject="Hàng Chọn: Đã giao xong", link_url="https://shop.example/don/HC-1",
    )  # fmt: skip
    res = await EmailDriver().send(msg)
    assert res.status == "sent" and res.external_id
    raw = smtp.messages[0].decode()
    assert "lan@example.com" in raw and "multipart/alternative" in raw and "text/html" in raw
    from email import message_from_string, policy

    parsed = message_from_string(raw, policy=policy.default)
    assert parsed["Subject"] == "Hàng Chọn: Đã giao xong"
    plain = parsed.get_body(("plain",)).get_content()
    html = parsed.get_body(("html",)).get_content()
    assert "Cảm ơn bạn!" in plain and "https://shop.example/don/HC-1" in plain and "Hàng Chọn" in plain
    assert "<p>Cảm ơn bạn!</p>" in html and "<img" not in html


async def test_email_temporary_and_permanent_errors(smtp: FakeSMTP) -> None:
    busy = await EmailDriver().send(OutboundNotification(channel=Channel.EMAIL, to="busy@example.com", text="x"))
    assert busy.status == "failed" and busy.retryable and "451" in (busy.error or "")
    bad = await EmailDriver().send(OutboundNotification(channel=Channel.EMAIL, to="nouser@example.com", text="x"))
    assert bad.status == "failed" and not bad.retryable and "550" in (bad.error or "")
    nope = await EmailDriver().send(OutboundNotification(channel=Channel.EMAIL, to="0900", text="x"))
    assert not nope.retryable and smtp.messages == []


async def test_email_server_down_is_temporary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "127.0.0.1")
    monkeypatch.setattr(settings, "smtp_port", 1)  # không ai nghe
    monkeypatch.setattr(settings, "smtp_tls", "none")
    monkeypatch.setattr(settings, "smtp_timeout_seconds", 2.0)
    res = await EmailDriver().send(OutboundNotification(channel=Channel.EMAIL, to="a@example.com", text="x"))
    assert res.status == "failed" and res.retryable and "thử lại" in (res.error or "")
