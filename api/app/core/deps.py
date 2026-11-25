"""Phụ thuộc xác thực cho route.

from app.core.deps import CurrentUser, OwnerUser

@router.get("/x")
async def x(user: CurrentUser): ...        # owner hoặc helper
@router.post("/y")
async def y(user: OwnerUser): ...          # chỉ chị
"""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.core.db import DbSession
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token, password_stamp
from app.modules.control.models import User, UserRole


async def current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    claims = decode_access_token(token) if token else None
    if not claims:
        raise Unauthorized()
    try:
        user = await db.get(User, uuid.UUID(claims["sub"]))
    except (KeyError, ValueError) as e:
        raise Unauthorized() from e
    if user is None or not user.is_active:
        raise Unauthorized("Tài khoản không còn hoạt động.")
    if not hmac.compare_digest(str(claims.get("pws", "")), password_stamp(user.password_hash)):
        raise Unauthorized("Mật khẩu đã đổi, chị đăng nhập lại nhé.")
    return user


async def require_owner(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != UserRole.OWNER:
        raise Forbidden("Chỉ chị (chủ cửa hàng) làm được việc này.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OwnerUser = Annotated[User, Depends(require_owner)]
