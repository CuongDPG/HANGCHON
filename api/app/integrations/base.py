"""Khung tích hợp ngoài: mỗi loại (`kind`) là một interface, mỗi driver là một tệp `app/integrations/<kind>/<driver>.py`
có lớp `Driver`. Chọn driver bằng biến môi trường `<KIND>_DRIVER` (mặc định `mock`).

    from app.integrations import get_driver
    payments = get_driver("payments")            # theo env PAYMENTS_DRIVER
    shipping = get_driver("shipping", "ghn")     # chọn tường minh
"""

from __future__ import annotations

import importlib
from typing import Any

from app.core.config import settings
from app.core.errors import AppError

KINDS = ("sources", "social", "payments", "shipping", "notify", "marketplaces", "einvoice", "storage")

_instances: dict[tuple[str, str], Any] = {}


class IntegrationError(AppError):
    status_code = 502
    code = "integration_error"
    message = "Dịch vụ bên ngoài báo lỗi, chị thử lại sau."


class IntegrationNotConfigured(AppError):
    status_code = 503
    code = "integration_not_configured"
    message = "Tích hợp này chưa được cấu hình (thiếu khoá hoặc chưa có driver)."


def driver_name(kind: str) -> str:
    return str(getattr(settings, f"{kind}_driver", "mock") or "mock")


def get_driver(kind: str, name: str | None = None) -> Any:
    if kind not in KINDS:
        raise ValueError(f"Loại tích hợp không tồn tại: {kind}")
    name = name or driver_name(kind)
    key = (kind, name)
    if key not in _instances:
        try:
            mod = importlib.import_module(f"app.integrations.{kind}.{name}")
        except ModuleNotFoundError as e:
            raise IntegrationNotConfigured(f"Chưa có driver «{name}» cho tích hợp «{kind}».") from e
        _instances[key] = mod.Driver()
    return _instances[key]


def reset_drivers() -> None:
    """Xoá bộ nhớ đệm driver (test)."""
    _instances.clear()
