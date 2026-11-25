"""Sổ provider AI. Thêm provider = thêm một tệp `app/ai/providers/<ten>.py` có lớp kế thừa `BaseProvider` gắn
`@register` — không cần sửa chỗ nào khác (cấu hình, màn Cài đặt, lệnh nhập khoá đều đọc từ sổ này)."""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import ClassVar

from app.ai.types import AIRequest, ProviderResponse


@dataclass(frozen=True)
class Connection:
    """Thông tin kết nối đã giải mã cho một lần gọi. `api_key` không in ra repr/log."""

    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None


class BaseProvider:
    name: ClassVar[str]
    label: ClassVar[str]
    needs_key: ClassVar[bool] = True
    key_env: ClassVar[str | None] = None  # tên trường Settings chứa khoá (vd "anthropic_api_key")
    base_url_env: ClassVar[str | None] = None  # tên trường Settings chứa base URL; None = provider không cần base URL
    supports_web: ClassVar[bool] = True
    model_suggestions: ClassVar[tuple[str, ...]] = ()  # gợi ý ở màn Cài đặt; rỗng = gõ tự do
    key_placeholder: ClassVar[str] = ""

    async def complete(self, req: AIRequest, conn: Connection) -> ProviderResponse:
        raise NotImplementedError


PROVIDERS: dict[str, type[BaseProvider]] = {}
_instances: dict[str, BaseProvider] = {}
_loaded = False


def register[P: type[BaseProvider]](cls: P) -> P:
    PROVIDERS[cls.name] = cls
    return cls


def provider_classes() -> dict[str, type[BaseProvider]]:
    global _loaded
    if not _loaded:
        for m in pkgutil.iter_modules(__path__):
            if not m.name.startswith("_"):
                importlib.import_module(f"{__name__}.{m.name}")
        _loaded = True
    return PROVIDERS


def get_provider(name: str) -> BaseProvider:
    if name not in _instances:
        cls = provider_classes().get(name)
        if cls is None:
            raise ValueError(f"AI_PROVIDER không hợp lệ: {name}")
        _instances[name] = cls()
    return _instances[name]


def reset_providers() -> None:
    _instances.clear()
