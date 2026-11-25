"""Chép cấu hình AI đang có trong biến môi trường vào CSDL (đã mã hoá) — chạy một lần khi chuyển sang Cài đặt.

    cd api && uv run python -m app.ai.import_env_config [--overwrite]

- Mỗi provider có khoá trong biến môi trường (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`…) → lưu khoá mã hoá vào dòng
  của provider đó; dòng đã có khoá thì giữ nguyên (trừ khi `--overwrite`).
- Provider của `AI_PROVIDER` → điền model / effort còn trống từ `AI_MODEL_*` / `AI_EFFORT_*`, và chuyển sang dùng
  nếu Cài đặt chưa chọn provider nào.
- Chạy lại không sinh trùng (mỗi provider một dòng). Không in khoá, chỉ in dạng che.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.ai import config as ai_config
from app.ai.providers import provider_classes
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.discovery import discover_modules
from app.core.secrets import SecretDecryptError, decrypt, mask


async def run_import(*, overwrite: bool = False) -> list[str]:
    from app.modules.control import service
    from app.modules.control.models import AIProviderConfig

    lines: list[str] = []
    async with SessionLocal() as db:
        has_active = (
            await db.execute(select(AIProviderConfig).where(AIProviderConfig.is_active))
        ).scalar_one_or_none() is not None
        for name, cls in provider_classes().items():
            key = ai_config.env_key(name)
            is_env_provider = name == settings.ai_provider
            if not key and (not is_env_provider or name == "fake"):
                continue
            row = await ai_config.get_row(db, name)
            created = row is None
            row = await ai_config.upsert_row(db, name, None)
            if key and cls.needs_key:
                same = False
                if row.api_key_encrypted:
                    try:
                        same = decrypt(row.api_key_encrypted) == key
                    except SecretDecryptError:
                        same = False
                if row.api_key_encrypted and (same or not overwrite):
                    lines.append(f"{name}: đã có khoá trong CSDL ({row.api_key_hint}), giữ nguyên.")
                else:
                    ai_config.set_key(row, key, None)
                    await service.audit(
                        db, "ai.key_changed", entity_type="ai_provider", entity_id=name,
                        summary=f"Nhập khoá API {cls.label} từ biến môi trường",
                    )  # fmt: skip
                    lines.append(f"{name}: đã lưu khoá {mask(key)} (mã hoá).")
            if is_env_provider:
                for f, v in (
                    ("model_smart", settings.ai_model_smart),
                    ("model_fast", settings.ai_model_fast),
                    ("effort_smart", settings.ai_effort_smart),
                    ("effort_fast", settings.ai_effort_fast),
                ):
                    if not getattr(row, f):
                        setattr(row, f, v)
                if cls.base_url_env and not row.base_url:
                    row.base_url = getattr(settings, cls.base_url_env, None)
            await db.flush()
            if is_env_provider and not has_active:
                await ai_config.activate(db, name)
                has_active = True
                await service.audit(
                    db, "ai.config_changed", entity_type="ai_provider", entity_id=name,
                    summary=f"Nhập cấu hình AI từ biến môi trường: dùng {cls.label}",
                    data={"changed": ["provider"], "activated": True},
                )  # fmt: skip
                lines.append(f"{name}: chuyển sang dùng (AI_PROVIDER).")
            elif created and not key:
                lines.append(f"{name}: tạo cấu hình (chưa có khoá).")
        await db.commit()
    if not lines:
        lines.append("Không có gì để nhập (biến môi trường không có khoá AI).")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--overwrite", action="store_true", help="Thay khoá đã lưu bằng khoá trong biến môi trường")
    args = parser.parse_args()
    discover_modules()
    for line in asyncio.run(run_import(overwrite=args.overwrite)):
        print(line)


if __name__ == "__main__":
    main()
