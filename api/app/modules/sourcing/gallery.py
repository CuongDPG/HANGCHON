"""Ảnh nhà cung cấp của ứng viên (chỉ ở desk): lưu bản sao về kho riêng thay vì nhúng thẳng link của sàn.

alicdn / Rakuten / Amazon có thể chặn nhúng ảnh từ trang khác và link ảnh hay chết, nên mỗi ảnh nguồn được tải về
`private/sourcing/candidates/<id>/...` (chỉ người đăng nhập xem được, qua `/api/files/...`). Chưa lưu xong thì desk
hiện link gốc (web đặt `referrerPolicy="no-referrer"`). Không bao giờ dùng ở website cho khách.

Tải an toàn: chỉ http/https, tên miền phải trỏ tới địa chỉ công khai (chặn IP nội bộ, kiểm lại sau mỗi lần chuyển
hướng), có thời hạn, chỉ nhận ảnh JPG/PNG/WEBP/GIF ≤ `MAX_BYTES`, tối đa `MAX_IMAGES` ảnh mỗi ứng viên, ghi link gốc."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.storage import get_storage
from app.core.timeutil import now_utc
from app.modules.sourcing.imagehash import _public_host

if TYPE_CHECKING:
    from app.modules.sourcing.models import Candidate

log = logging.getLogger("app.sourcing.gallery")

MAX_IMAGES = 12
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 60_000_000
TIMEOUT = 10.0
MAX_REDIRECTS = 3
CONCURRENCY = 4
TYPES = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp"),
         "GIF": ("image/gif", "gif")}  # fmt: skip
# một số CDN trả 403 cho trình khách lạ; không gửi Referer (giống referrerPolicy="no-referrer" ở web)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8",
}


class FetchError(Exception):
    """Không tải được một ảnh — câu tiếng Việt ngắn, lưu vào `image_cache[].error`."""


def source_urls(c: Candidate) -> list[str]:
    """Ảnh nguồn của ứng viên theo thứ tự hiển thị: ảnh chính trước, khử trùng, tối đa `MAX_IMAGES`."""
    urls = [c.main_image_url, *[u for u in (c.images or []) if isinstance(u, str)]]
    out = [u for u in dict.fromkeys(u for u in urls if u) if urlparse(u).scheme in ("http", "https")]
    return out[:MAX_IMAGES]


def file_url(key: str) -> str:
    storage = get_storage()
    if storage.name == "local":  # cùng origin với web (Next chuyển tiếp /api/*) để cookie đăng nhập đi kèm
        return f"/api/files/{key}"
    return storage.url(key)


def cache_map(c: Candidate) -> dict[str, dict[str, Any]]:
    return {e["url"]: e for e in (c.image_cache or []) if isinstance(e, dict) and e.get("url")}


def cached(entry: dict[str, Any] | None) -> bool:
    return bool(entry and entry.get("key"))


def display(c: Candidate) -> list[dict[str, Any]]:
    """[{src, source_url, cached, error}] — `src` là bản đã lưu về kho nếu có, không thì link gốc."""
    m = cache_map(c)
    out = []
    for url in source_urls(c):
        e = m.get(url)
        out.append(
            {
                "src": file_url(e["key"]) if cached(e) else url,
                "source_url": url,
                "cached": cached(e),
                "error": (e or {}).get("error"),
            }
        )
    return out


def thumb(c: Candidate) -> str | None:
    g = display(c)
    return g[0]["src"] if g else None


# ---- tải ảnh -----------------------------------------------------------------------------------------------------


def _check_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise FetchError("Link ảnh không phải http/https.")


async def _guard_host(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not await asyncio.to_thread(_public_host, host):
        raise FetchError("Link ảnh trỏ tới địa chỉ nội bộ hoặc không phân giải được.")


def _inspect(data: bytes) -> tuple[str, str, int, int]:
    """(content_type, đuôi, rộng, cao) nếu là ảnh hợp lệ; không thì FetchError."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or ""
            w, h = img.size
            if w * h > MAX_PIXELS:
                raise FetchError("Ảnh có độ phân giải quá lớn.")
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise FetchError("Tệp tải về không phải ảnh đọc được.") from e
    if fmt not in TYPES:
        raise FetchError(f"Định dạng ảnh {fmt or 'lạ'} chưa hỗ trợ (cần JPG, PNG, WEBP, GIF).")
    ctype, ext = TYPES[fmt]
    return ctype, ext, w, h


async def download(url: str, client: httpx.AsyncClient) -> tuple[bytes, str, str, int, int]:
    """Tải một ảnh nguồn an toàn → (bytes, content_type, đuôi, rộng, cao). Lỗi → FetchError."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _check_url(current)
        await _guard_host(current)
        try:
            async with client.stream("GET", current, headers=HEADERS) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code != 200:
                    raise FetchError(f"Máy chủ ảnh trả mã {r.status_code}.")
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype and not ctype.startswith("image/") and ctype != "application/octet-stream":
                    raise FetchError("Link không trả về ảnh.")
                if int(r.headers.get("content-length") or 0) > MAX_BYTES:
                    raise FetchError("Ảnh lớn quá 5 MB.")
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise FetchError("Ảnh lớn quá 5 MB.")
        except httpx.TimeoutException as e:
            raise FetchError("Máy chủ ảnh trả lời quá chậm.") from e
        except httpx.HTTPError as e:
            raise FetchError("Không kết nối được máy chủ ảnh.") from e
        data = bytes(buf)
        return (data, *_inspect(data))
    raise FetchError("Link ảnh chuyển hướng quá nhiều lần.")


def http_client() -> httpx.AsyncClient:
    """Tách riêng để test thay bằng `httpx.MockTransport`. Không tự theo chuyển hướng (kiểm từng bước ở `download`)."""
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)


def caching_enabled() -> bool:
    """Tự lưu ảnh khi có ảnh mới. Tắt trong test (test bật bằng monkeypatch) và khi nguồn là giả lập (ảnh giữ chỗ)."""
    from app.modules.sourcing.service import sources

    return not settings.is_test and sources().name != "mock"


def _key(c: Candidate, url: str, ext: str) -> str:
    return f"private/sourcing/candidates/{c.id}/{hashlib.sha1(url.encode()).hexdigest()[:20]}.{ext}"


async def cache_images(c: Candidate, *, retry_failed: bool = False) -> dict[str, int]:
    """Tải các ảnh nguồn chưa có bản sao về kho riêng; ghi kết quả vào `c.image_cache` (caller commit).

    Ảnh đã lưu không tải lại; ảnh từng lỗi chỉ thử lại khi `retry_failed` (chị bấm «Lấy ảnh và chi tiết»)."""
    m = cache_map(c)
    todo = [u for u in source_urls(c) if not cached(m.get(u)) and (retry_failed or u not in m)]
    if not todo:
        return {"cached": 0, "failed": 0}
    storage = get_storage()
    sem = asyncio.Semaphore(CONCURRENCY)
    results: dict[str, dict[str, Any]] = {}

    async with http_client() as client:

        async def one(url: str) -> None:
            at = now_utc().isoformat()
            async with sem:
                try:
                    data, ctype, ext, w, h = await download(url, client)
                    key = _key(c, url, ext)
                    await storage.put(key, data, ctype)
                    results[url] = {"url": url, "key": key, "type": ctype, "bytes": len(data), "width": w,
                                    "height": h, "at": at}  # fmt: skip
                except FetchError as e:
                    results[url] = {"url": url, "error": str(e), "at": at}
                except Exception as e:  # lỗi lạ một ảnh không làm hỏng cả lượt
                    log.warning("Lưu ảnh %s lỗi: %s", url, e)
                    results[url] = {"url": url, "error": "Lỗi khi lưu ảnh.", "at": at}

        await asyncio.gather(*(one(u) for u in todo))
    keep = [e for u, e in m.items() if u not in results]
    c.image_cache = [*keep, *results.values()]
    ok = sum(1 for e in results.values() if e.get("key"))
    return {"cached": ok, "failed": len(results) - ok}


async def read_cached(c: Candidate, url: str) -> tuple[bytes, str] | None:
    """Bytes + content_type của bản đã lưu (để chị dùng lại ở Hồ sơ bán). Chưa lưu → None."""
    e = cache_map(c).get(url)
    if not cached(e):
        return None
    return await get_storage().get(e["key"]), e.get("type") or "image/jpeg"
