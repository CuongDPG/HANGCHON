"""Tự khám phá module nghiệp vụ trong `app/modules/*`.

Mỗi thư mục con là một module. Các tệp sau được nạp tự động nếu có (theo thứ tự):

    models.py    bảng SQLAlchemy (kế thừa app.core.db.Base)
    actions.py   khai báo hành động, handler, stat provider, lệnh bằng lời (control)
    ai_tasks.py  khai báo tác vụ AI và hàm giả (app.ai)
    jobs.py      việc nền / lịch (app.core.jobs)
    router.py    biến `router` (APIRouter) hoặc `routers` (list[APIRouter])

Thêm module = thêm thư mục; không sửa tệp dùng chung.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from dataclasses import dataclass, field
from types import ModuleType

from fastapi import APIRouter

log = logging.getLogger("app.discovery")

MODULE_PARTS = ("models", "actions", "ai_tasks", "jobs", "router")


@dataclass
class DiscoveredModule:
    name: str
    package: str
    parts: dict[str, ModuleType] = field(default_factory=dict)

    @property
    def routers(self) -> list[APIRouter]:
        mod = self.parts.get("router")
        if mod is None:
            return []
        if isinstance(getattr(mod, "routers", None), list | tuple):
            return list(mod.routers)
        r = getattr(mod, "router", None)
        return [r] if isinstance(r, APIRouter) else []


_cache: dict[str, list[DiscoveredModule]] = {}


def module_names(package: str = "app.modules") -> list[str]:
    pkg = importlib.import_module(package)
    return sorted(m.name for m in pkgutil.iter_modules(pkg.__path__) if m.ispkg and not m.name.startswith("_"))


def discover_modules(package: str = "app.modules", *, refresh: bool = False) -> list[DiscoveredModule]:
    """Nạp mọi module (một lần cho mỗi package; `refresh=True` quét lại). Trả về danh sách theo tên."""
    if package in _cache and not refresh:
        return _cache[package]
    found: list[DiscoveredModule] = []
    names = module_names(package)
    # nạp models của mọi module trước để quan hệ chéo module (theo tên lớp) phân giải được
    for part in MODULE_PARTS:
        for name in names:
            full = f"{package}.{name}.{part}"
            if importlib.util.find_spec(full) is None:
                continue
            mod = importlib.import_module(full)
            entry = next((m for m in found if m.name == name), None)
            if entry is None:
                entry = DiscoveredModule(name=name, package=f"{package}.{name}")
                found.append(entry)
            entry.parts[part] = mod
    found.sort(key=lambda m: m.name)
    _cache[package] = found
    log.debug("Đã nạp %d module: %s", len(found), ", ".join(m.name for m in found))
    return found


def load_all_models() -> None:
    """Nạp mọi models (cho Alembic và create_all)."""
    discover_modules()
