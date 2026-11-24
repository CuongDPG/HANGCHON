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
from app.core.discovery import discover_modules
from app.core.errors import Unauthorized, install_error_handlers
from app.core.jobs import close_pool
from app.core.security import decode_access_token
from app.core.storage import get_storage, is_public_key

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
    app = FastAPI(
        title="Hàng Chọn API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    install_error_handlers(app)
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
        """Phục vụ tệp của driver `local`. `public/...` ai cũng xem được; còn lại cần đăng nhập."""
        if not is_public_key(key):
            token = request.cookies.get(settings.cookie_name)
            if not token or decode_access_token(token) is None:
                raise Unauthorized()
        storage = get_storage()
        try:
            data = await storage.get(key)
        except (FileNotFoundError, ValueError):
            return JSONResponse({"detail": "Không tìm thấy tệp.", "code": "not_found"}, status_code=404)
        ctype = getattr(storage, "content_type", lambda _k: "application/octet-stream")(key)
        headers = {"Cache-Control": "public, max-age=86400" if is_public_key(key) else "private, no-store"}
        return Response(data, media_type=ctype, headers=headers)

    for module in discover_modules():
        for r in module.routers:
            app.include_router(r)
    return app


app = create_app()
