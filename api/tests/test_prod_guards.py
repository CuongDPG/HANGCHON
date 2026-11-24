"""Production: mọi đường giả lập (tiền về giả, tin đến giả, đơn sàn giả, webhook driver mock) trả 404 kể cả khi driver
đang là `mock`; khoá ký phiên mặc định thì không khởi động."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.core.config import Settings, settings


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
    assert Settings(app_env="prod", jwt_secret="x" * 40, _env_file=None).jwt_secret == "x" * 40
    assert Settings(app_env="dev", jwt_secret="ngan", _env_file=None).app_env == "dev"
