"""Production: mọi đường giả lập (tiền về giả, tin đến giả, đơn sàn giả, webhook driver mock) trả 404 kể cả khi driver
đang là `mock`; khoá ký phiên mặc định thì không khởi động."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.core.config import DEV_SECRETS_ENCRYPTION_KEY, Settings, settings

# khoá Fernet chỉ dùng trong test (base64 của 32 byte cố định)
PROD_FERNET_KEY = "dGVzdC1vbmx5LXByb2QtZmVybmV0LWtleS0zMmJ5dGU="


@pytest.fixture
def prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")


async def test_simulation_endpoints_are_404_in_prod(prod, owner_client: httpx.AsyncClient) -> None:
    assert settings.payments_driver == "mock"  # driver vẫn là mock mà vẫn phải đóng
    calls = [
        ("/api/hooks/payments/mock", {"transfers": []}),
        ("/api/hooks/shipping/mock", {}),
        ("/api/hooks/social/mock", {"events": []}),
        ("/api/desk/orders/payments/simulate", {"amount_vnd": 100000, "content": "HC123"}),
        ("/api/desk/inbox/dev/simulate", {"text": "Còn hàng không?", "channel": "facebook"}),
        ("/api/desk/orders/marketplaces/shopee/simulate", {"product_id": str(uuid.uuid4()), "quantity": 1}),
    ]
    for path, body in calls:
        r = await owner_client.post(path, json=body)
        assert r.status_code == 404, (path, r.status_code, r.text)


async def test_simulation_endpoints_open_in_dev(owner_client: httpx.AsyncClient) -> None:
    r = await owner_client.post("/api/desk/orders/payments/simulate", json={"amount_vnd": 100000, "content": "HCX"})
    assert r.status_code == 200, r.text


def test_prod_refuses_default_jwt_secret() -> None:
    for bad in ("dev-only-change-me-please-32-bytes-min", "doi-chuoi-nay-thanh-chuoi-ngau-nhien-dai-it-nhat-32-ky-tu",
                "ngan"):  # fmt: skip
        with pytest.raises(ValueError, match="JWT_SECRET"):
            Settings(app_env="prod", jwt_secret=bad, _env_file=None)
    ok = Settings(
        app_env="prod", jwt_secret="x" * 40, owner_password="p" * 16, secrets_encryption_key=PROD_FERNET_KEY,
        _env_file=None,
    )  # fmt: skip
    assert ok.jwt_secret == "x" * 40
    assert Settings(app_env="dev", jwt_secret="ngan", _env_file=None).app_env == "dev"


def test_blank_env_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """docker-compose.prod.yml truyền `${KEY:-}` → chuỗi rỗng; không được làm API từ chối khởi động."""
    for k in ("GHN_ENV", "GHTK_ENV", "ZALO_OA_BROADCAST", "CONTENT_FFMPEG", "SMTP_PORT"):
        monkeypatch.setenv(k, "")
    s = Settings(_env_file=None)
    assert (s.ghn_env, s.ghtk_env, s.zalo_oa_broadcast, s.content_ffmpeg, s.smtp_port) == (
        "prod",
        "prod",
        False,
        True,
        587,
    )


def test_prod_refuses_sample_owner_password() -> None:
    """Tài khoản chị được tạo lúc khởi động bằng OWNER_PASSWORD; mật khẩu mẫu trong repo = ai cũng đăng nhập được."""
    for bad in ("doimatkhau", "ngan-qua"):
        with pytest.raises(ValueError, match="OWNER_PASSWORD"):
            Settings(
                app_env="prod", jwt_secret="x" * 40, owner_password=bad, create_owner_on_startup=True, _env_file=None
            )
    ok = Settings(app_env="prod", jwt_secret="x" * 40, owner_password="doimatkhau", create_owner_on_startup=False,
                  secrets_encryption_key=PROD_FERNET_KEY, _env_file=None)  # fmt: skip
    assert ok.app_env == "prod"


def test_prod_refuses_missing_or_dev_secrets_key() -> None:
    """Khoá API lưu trong CSDL được mã hoá bằng SECRETS_ENCRYPTION_KEY: production thiếu biến này (hay dùng khoá dev
    công khai trong repo) thì không khởi động; dev/test thì dùng khoá dev."""
    base = {"app_env": "prod", "jwt_secret": "x" * 40, "owner_password": "p" * 16, "_env_file": None}
    for bad in (None, "", DEV_SECRETS_ENCRYPTION_KEY, f"{PROD_FERNET_KEY},{DEV_SECRETS_ENCRYPTION_KEY}"):
        with pytest.raises(ValueError, match="SECRETS_ENCRYPTION_KEY"):
            Settings(**base, secrets_encryption_key=bad)
    assert Settings(**base, secrets_encryption_key=PROD_FERNET_KEY).app_env == "prod"
    assert Settings(app_env="dev", _env_file=None).secrets_encryption_key is None
