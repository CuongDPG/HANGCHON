"""Tải link lấy từ dữ liệu bên ngoài (ảnh nhà cung cấp, trang sản phẩm) mà không để bị dắt vào mạng nội bộ.

Chống «DNS rebinding»: kiểm tên miền rồi mới kết nối thì kẻ xấu có thể cho lần phân giải đầu trả IP công khai, lần
sau trả 127.0.0.1. Ở đây việc phân giải + kiểm IP diễn ra **ngay lúc mở kết nối TCP** (`_PinnedBackend.connect_tcp`)
và kết nối đi thẳng tới đúng IP vừa kiểm; TLS vẫn dùng tên miền gốc (SNI + kiểm chứng chỉ do httpcore làm theo tên
miền trong URL). Mỗi kết nối mới (kể cả sau chuyển hướng) đều qua bước này; chuyển hướng do người gọi tự theo từng
bước (`follow_redirects=False`) và kiểm lại.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Callable, Iterable
from typing import Any

import httpcore
import httpx


class BlockedAddress(Exception):
    """Tên miền trỏ tới địa chỉ nội bộ hoặc không phân giải được."""


def is_public_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified)


def _getaddrinfo(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(i[4][0]) for i in infos))


Resolver = Callable[[str, int], list[str]]


def resolve_public(host: str, port: int, resolver: Resolver = _getaddrinfo) -> list[str]:
    """Các IP để kết nối: mọi địa chỉ của tên miền phải công khai (không thì BlockedAddress)."""
    try:
        ips = resolver(host, port)
    except OSError as e:
        raise BlockedAddress(f"Không phân giải được {host}.") from e
    if not ips or not all(is_public_ip(ip) for ip in ips):
        raise BlockedAddress(f"{host} trỏ tới địa chỉ nội bộ.")
    return ips


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, resolver: Resolver | None = None, inner: httpcore.AsyncNetworkBackend | None = None) -> None:
        self.resolver = resolver or _getaddrinfo
        self.inner = inner or httpcore.AnyIOBackend()
        self.connected: list[tuple[str, str]] = []  # (tên miền, IP) — cho test

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 — chữ ký của httpcore
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        ips = await asyncio.to_thread(resolve_public, host, port, self.resolver)
        error: Exception | None = None
        for ip in ips:  # thử lần lượt (vd IPv6 không đi được thì sang IPv4), chỉ trong các IP đã kiểm
            try:
                stream = await self.inner.connect_tcp(
                    ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as e:
                error = e
                continue
            self.connected.append((host, ip))
            return stream
        raise error or httpcore.ConnectError(f"Không kết nối được {host}.")

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        raise BlockedAddress("Không dùng unix socket.")

    async def sleep(self, seconds: float) -> None:
        await self.inner.sleep(seconds)


class PinnedTransport(httpx.AsyncHTTPTransport):
    """Transport httpx mở kết nối qua `_PinnedBackend` (không proxy, không unix socket)."""

    def __init__(self, resolver: Resolver | None = None, inner: httpcore.AsyncNetworkBackend | None = None) -> None:
        super().__init__(trust_env=False)
        self.backend = _PinnedBackend(resolver, inner)
        ssl_context = self._pool._ssl_context  # type: ignore[attr-defined]
        self._pool = httpcore.AsyncConnectionPool(ssl_context=ssl_context, network_backend=self.backend)


def client(timeout: float = 10.0, *, resolver: Resolver | None = None) -> httpx.AsyncClient:
    """AsyncClient an toàn: kết nối ghim IP đã kiểm, không theo chuyển hướng (người gọi tự kiểm từng bước)."""
    return httpx.AsyncClient(
        transport=PinnedTransport(resolver), timeout=timeout, follow_redirects=False, trust_env=False
    )
