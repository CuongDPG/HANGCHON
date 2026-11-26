"""Ứng dụng FastAPI. Tự nạp mọi module trong app/modules (router + models + actions + ai_tasks + jobs)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.deps import current_user
from app.core.discovery import discover_modules
from app.core.errors import Forbidden, Unauthorized, install_error_handlers
from app.core.jobs import close_pool
from app.core.security import decode_access_token
from app.core.storage import get_storage, is_public_key
from app.integrations.channel_config import RefreshMiddleware as ChannelConfigRefresh
from app.modules.control.models import UserRole

log = logging.getLogger("app")

# Đường dẫn dưới /api/desk không cần đăng nhập
DESK_PUBLIC_PATHS = {"/api/desk/auth/login", "/api/desk/auth/logout"}


class DeskAuthGuard:
    """Lưới an toàn: mọi /api/desk/** phải có phiên hợp lệ, kể cả khi module quên khai báo Depends(current_user)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] != "OPTIONS":
            path: str = scope["path"]
            if path.startswith("/api/desk/") and path not in DESK_PUBLIC_PATHS:
                request = Request(scope)
                token = request.cookies.get(settings.cookie_name)
                if not token:
                    auth = request.headers.get("authorization", "")
                    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
                if not token or decode_access_token(token) is None:
                    resp = JSONResponse({"detail": Unauthorized.message, "code": Unauthorized.code}, status_code=401)
                    await resp(scope, receive, send)
                    return
        await self.app(scope, receive, send)


# Kiểu tệp được mở ngay trong trình duyệt. Kiểu khác (html, svg, js, xml...) do người tải lên tự khai → chạy được
# script trên cùng tên miền với bàn làm việc; luôn trả về dạng tải xuống.
INLINE_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif", "image/heic",
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-m4a", "audio/aac",
    "video/mp4", "video/quicktime", "video/webm", "video/x-m4v", "application/pdf",
    "text/plain",  # nosniff + sandbox: không bị đoán thành HTML
}  # fmt: skip


def file_headers(content_type: str, *, public: bool) -> dict[str, str]:
    ctype = (content_type or "").split(";")[0].strip().lower()
    # sandbox: lỡ có tệp lọt qua cũng không chạy script, không đọc cookie; PDF bỏ sandbox vì trình xem PDF của
    # trình duyệt không mở được trong khung sandbox.
    csp = "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'"
    headers = {
        "Cache-Control": "public, max-age=86400" if public else "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": csp if ctype == "application/pdf" else csp + "; sandbox",
    }
    if not public:
        headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if ctype in INLINE_TYPES:
        headers["Content-Type"] = ctype
    else:
        headers["Content-Type"] = "application/octet-stream"
        headers["Content-Disposition"] = "attachment"
    return headers


async def _bootstrap_owner() -> None:
    if not (settings.create_owner_on_startup and settings.owner_email and settings.owner_password):
        return
    from app.modules.control.service import ensure_owner

    try:
        async with SessionLocal() as db:
            await ensure_owner(db, settings.owner_email, settings.owner_password, settings.owner_name)
            await db.commit()
    except Exception as e:  # CSDL chưa migrate: vẫn cho API chạy, báo trong log
        log.warning("Chưa tạo được tài khoản chị lúc khởi động: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await _bootstrap_owner()
    yield
    await close_pool()


def create_app() -> FastAPI:
    logging.basicConfig(level=settings.log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # URL gọi Meta/Shopee có access_token: không ghi log
    app = FastAPI(
        title="Hàng Chọn API",
        version="0.1.0",
        lifespan=lifespan,
        # production không mở trang thử API (bớt bề mặt tấn công; danh sách route vẫn đọc được trong repo)
        docs_url=None if settings.app_env == "prod" else "/docs",
        redoc_url=None if settings.app_env == "prod" else "/redoc",
        openapi_url=None if settings.app_env == "prod" else "/openapi.json",
    )
    install_error_handlers(app)
    app.add_middleware(ChannelConfigRefresh)  # tài khoản kênh lưu ở Cài đặt: driver thấy thay đổi ≤ 5 giây
    app.add_middleware(DeskAuthGuard)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/files/{key:path}", tags=["files"], include_in_schema=False)
    async def serve_file(key: str, request: Request) -> Response:
        """Phục vụ tệp của driver `local`. `public/...` ai cũng xem được; còn lại cần tài khoản còn hoạt động,
        bản sao lưu (toàn bộ dữ liệu khách) chỉ chị tải được."""
        if not is_public_key(key):
            async with SessionLocal() as db:
                user = await current_user(request, db)
            if key.lstrip("/").startswith("private/backups/") and user.role != UserRole.OWNER:
                raise Forbidden("Chỉ chị (chủ cửa hàng) tải được bản sao lưu.")
        storage = get_storage()
        try:
            data = await storage.get(key)
        except (FileNotFoundError, ValueError):
            return JSONResponse({"detail": "Không tìm thấy tệp.", "code": "not_found"}, status_code=404)
        ctype = getattr(storage, "content_type", lambda _k: "application/octet-stream")(key)
        return Response(data, headers=file_headers(ctype, public=is_public_key(key)))

    for module in discover_modules():
        for r in module.routers:
            app.include_router(r)
    return app


app = create_app()
