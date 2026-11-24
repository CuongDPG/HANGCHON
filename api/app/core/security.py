"""Mật khẩu (argon2) và phiên đăng nhập (JWT trong cookie httpOnly)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings
from app.core.timeutil import now_utc

_hasher = PasswordHasher()
JWT_ALG = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, role: str, *, minutes: int | None = None) -> str:
    now = now_utc()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes or settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


def random_token(nbytes: int = 24) -> str:
    """Mã ngẫu nhiên an toàn cho đường link (mời đánh giá, mời thử hàng...)."""
    return secrets.token_urlsafe(nbytes)


def hmac_sha256(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_hmac_sha256(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(hmac_sha256(secret, body), signature.removeprefix("sha256="))
