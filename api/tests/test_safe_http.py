"""Tải link bên ngoài an toàn (`app.integrations.safe_http`): IP được kiểm ngay lúc mở kết nối và kết nối đi đúng IP
đó (chống DNS rebinding); tên miền trỏ vào mạng nội bộ bị chặn trước khi gửi request. Không gọi mạng ngoài."""

from __future__ import annotations

import asyncio

import httpcore
import httpx
import pytest

from app.integrations import safe_http
from app.modules.sourcing import gallery


def test_is_public_ip():
    for ip in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1", "169.254.169.254", "::1", "0.0.0.0", "fd00::1",
               "::ffff:127.0.0.1", "224.0.0.1"):  # fmt: skip
        assert not safe_http.is_public_ip(ip), ip
    assert safe_http.is_public_ip("93.184.216.34") and safe_http.is_public_ip("2606:4700::1")


def test_resolve_public_needs_every_address_public():
    assert safe_http.resolve_public("a.test", 443, lambda h, p: ["93.184.216.34"]) == ["93.184.216.34"]
    with pytest.raises(safe_http.BlockedAddress):
        safe_http.resolve_public("a.test", 443, lambda h, p: ["93.184.216.34", "10.0.0.5"])
    with pytest.raises(safe_http.BlockedAddress):
        safe_http.resolve_public("a.test", 443, lambda h, p: [])

    def fail(h, p):
        raise OSError("nxdomain")

    with pytest.raises(safe_http.BlockedAddress):
        safe_http.resolve_public("a.test", 443, fail)


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self):
        self.calls: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # noqa: ASYNC109
        self.calls.append(host)
        raise httpcore.ConnectError("không có mạng trong test")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


async def test_rebinding_connection_uses_the_vetted_ip():
    """Lần phân giải lúc kiểm trả IP công khai, lần sau trả IP nội bộ: kết nối vẫn chỉ đi tới IP đã kiểm ở bước kết nối
    — và nếu chính bước kết nối nhận IP nội bộ thì bị chặn, không mở socket."""
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])
    inner = _RecordingBackend()
    backend = safe_http._PinnedBackend(lambda h, p: next(answers), inner)
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("img.test", 443)
    assert inner.calls == ["93.184.216.34"]  # kết nối tới IP, không đưa tên miền cho hệ điều hành phân giải lại
    with pytest.raises(safe_http.BlockedAddress):
        await backend.connect_tcp("img.test", 443)
    assert inner.calls == ["93.184.216.34"]


async def test_tries_next_vetted_ip():
    inner = _RecordingBackend()
    backend = safe_http._PinnedBackend(lambda h, p: ["2606:4700::1", "93.184.216.34"], inner)
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("img.test", 443)
    assert inner.calls == ["2606:4700::1", "93.184.216.34"]


async def test_real_client_blocks_loopback_before_sending():
    async with safe_http.client(2) as c:
        with pytest.raises(safe_http.BlockedAddress):
            await c.get("http://127.0.0.1:9/x.jpg")
        with pytest.raises(safe_http.BlockedAddress):
            await c.get("http://localhost:9/x.jpg")


async def test_pinned_client_keeps_host_header_and_path():
    """Máy chủ HTTP thật trên máy (127.0.0.1), resolver giả trả đúng IP đó và coi là công khai: request đi tới IP đã
    kiểm nhưng vẫn mang Host của tên miền gốc."""
    seen: list[bytes] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        seen.append(head)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        transport = safe_http.PinnedTransport(resolver=lambda h, p: ["127.0.0.1"])
        orig = safe_http.is_public_ip
        safe_http.is_public_ip = lambda ip: True  # chỉ trong test: coi 127.0.0.1 là công khai
        try:
            async with httpx.AsyncClient(transport=transport, trust_env=False) as c:
                r = await c.get(f"http://img.test:{port}/a.jpg")
        finally:
            safe_http.is_public_ip = orig
    finally:
        server.close()
        await server.wait_closed()
    assert r.text == "ok" and transport.backend.connected == [("img.test", "127.0.0.1")]
    assert seen[0].startswith(b"GET /a.jpg HTTP/1.1") and f"Host: img.test:{port}".encode() in seen[0]


async def test_gallery_reports_rebinding_block(monkeypatch):
    """Kiểm trước (DNS lần 1) cho qua, lúc kết nối (DNS lần 2) trỏ vào nội bộ → lỗi «nội bộ», không tải."""
    monkeypatch.setattr(gallery, "_public_host", lambda host: True)
    transport = safe_http.PinnedTransport(resolver=lambda h, p: ["127.0.0.1"])
    async with httpx.AsyncClient(transport=transport, trust_env=False) as c:
        with pytest.raises(gallery.FetchError, match="nội bộ"):
            await gallery.download("http://img.test/a.jpg", c)
