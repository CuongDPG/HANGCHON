"""Cài đặt → «AI và khoá API»: phân quyền, mã hoá khoá, thứ tự ưu tiên CSDL > env > mặc định, kiểm tra kết nối,
lệnh nhập khoá từ biến môi trường. Không gọi dịch vụ thật: OpenRouter đi qua httpx.MockTransport."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from sqlalchemy import select, text

from app import ai
from app.ai import config as ai_config
from app.ai.import_env_config import run_import
from app.ai.providers import get_provider
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.secrets import SecretDecryptError, decrypt
from app.modules.control.models import AIProviderConfig, AIRun, AuditLog

BASE = "/api/desk/control/ai/config"
# khoá giả dạng thật (không phải khoá của ai)
ANTHROPIC_KEY = "sk-ant-api03-FAKEFAKEFAKEFAKEFAKEFAKE-test-8AAA"
OPENROUTER_KEY = "sk-or-v1-0123456789abcdef0123456789abcdef-test-9ZZZ"
OTHER_FERNET_KEY = "b3RoZXIta2V5LWZvci10ZXN0cy1vbmx5LTMyYnl0ZXM="


class Echo(BaseModel):
    text: str


def _ok_body(content: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "id": "gen-test-1",
        "model": extra.pop("model", "anthropic/claude-opus-5.5"),
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 8, "cost": 0.0012},
        **extra,
    }


@pytest.fixture
def openrouter() -> Iterator[Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]]:
    """Gắn máy chủ giả cho provider openrouter; trả danh sách request đã nhận."""
    provider = get_provider("openrouter")
    seen: list[httpx.Request] = []

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> list[httpx.Request]:
        def _h(req: httpx.Request) -> httpx.Response:
            seen.append(req)
            return handler(req)

        provider.transport = httpx.MockTransport(_h)  # type: ignore[attr-defined]
        provider.retry_delay = 0  # type: ignore[attr-defined]
        return seen

    yield install
    provider.transport = None  # type: ignore[attr-defined]


async def _rows() -> list[AIProviderConfig]:
    async with SessionLocal() as s:
        return list((await s.execute(select(AIProviderConfig))).scalars())


async def _raw_db_text() -> str:
    """Toàn bộ nội dung các bảng có thể chứa khoá (dạng chữ) — để chứng minh khoá rõ không nằm trong CSDL."""
    async with SessionLocal() as s:
        parts = []
        for table in ("ai_provider_configs", "audit_log", "ai_runs", "app_settings"):
            rows = (await s.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))).scalars()
            parts += list(rows)
    return "\n".join(parts)


# ---- phân quyền --------------------------------------------------------------------------------------------------


async def test_helper_cannot_read_or_change_ai_config(helper_client: httpx.AsyncClient, client: httpx.AsyncClient):
    body = {"provider": "anthropic", "api_key": ANTHROPIC_KEY}
    for method, path, payload in (
        ("GET", BASE, None),
        ("PATCH", BASE, body),
        ("POST", f"{BASE}/test", body),
        ("DELETE", f"{BASE}/anthropic/key", None),
    ):
        r = await helper_client.request(method, path, json=payload)
        assert r.status_code == 403, (method, path, r.text)
        r = await client.request(method, path, json=payload)
        assert r.status_code == 401, (method, path, r.text)
    assert await _rows() == []


# ---- lưu, che khoá, mã hoá ----------------------------------------------------------------------------------------


async def test_default_is_env_config(owner_client: httpx.AsyncClient):
    r = await owner_client.get(BASE)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["provider"] == "fake" and data["source"] == "env"
    names = [p["name"] for p in data["providers"]]
    assert names[-1] == "fake" and {"anthropic", "openrouter"} <= set(names)
    anthropic = next(p for p in data["providers"] if p["name"] == "anthropic")
    assert anthropic["model_suggestions"] == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    assert anthropic["has_key"] is False and anthropic["model_smart"] == settings.ai_model_smart
    openrouter = next(p for p in data["providers"] if p["name"] == "openrouter")
    assert openrouter["needs_base_url"] and openrouter["model_smart"] == ""  # gõ tự do, không mượn tên model Claude
    assert data["monthly_budget_vnd"] == settings.ai_monthly_budget_vnd and data["budget_source"] == "env"


async def test_save_masks_and_encrypts_key(owner_client: httpx.AsyncClient):
    r = await owner_client.patch(
        BASE,
        json={"provider": "anthropic", "api_key": ANTHROPIC_KEY, "model_smart": "claude-sonnet-5-5",
              "model_fast": "claude-haiku-5-5", "effort_smart": "high", "effort_fast": "low",
              "monthly_budget_vnd": 900_000},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    assert ANTHROPIC_KEY not in r.text
    data = r.json()
    assert data["provider"] == "anthropic" and data["source"] == "settings"
    p = next(p for p in data["providers"] if p["name"] == "anthropic")
    assert p["key_hint"] == "sk-ant-…8AAA" and p["key_source"] == "settings" and p["key_updated_by"] == "Chị"
    assert p["model_smart"] == "claude-sonnet-5-5" and p["effort_smart"] == "high"
    assert data["monthly_budget_vnd"] == 900_000 and data["budget_source"] == "settings"
    assert ANTHROPIC_KEY not in (await owner_client.get(BASE)).text

    # CSDL không chứa khoá rõ (kể cả lưu vết), đọc ra đúng sau khi giải mã
    raw = await _raw_db_text()
    assert ANTHROPIC_KEY not in raw and "FAKEFAKEFAKE" not in raw
    (row,) = await _rows()
    assert row.is_active and row.api_key_encrypted and decrypt(row.api_key_encrypted) == ANTHROPIC_KEY

    # lưu vết: ai đổi, lúc nào, đổi gì — không có giá trị khoá
    async with SessionLocal() as s:
        audits = list((await s.execute(select(AuditLog).where(AuditLog.action.like("ai.%")))).scalars())
    assert {a.action for a in audits} == {"ai.key_changed", "ai.config_changed"}
    assert all(a.actor_user_id is not None and a.created_at for a in audits)


async def test_blank_key_keeps_old_and_delete_clears(owner_client: httpx.AsyncClient):
    await owner_client.patch(BASE, json={"provider": "anthropic", "api_key": ANTHROPIC_KEY})
    r = await owner_client.patch(BASE, json={"provider": "anthropic", "api_key": "", "model_smart": "claude-opus-5-5"})
    assert r.status_code == 200, r.text
    (row,) = await _rows()
    assert decrypt(row.api_key_encrypted) == ANTHROPIC_KEY and row.model_smart == "claude-opus-5-5"

    r = await owner_client.delete(f"{BASE}/anthropic/key")
    assert r.status_code == 204, r.text
    (row,) = await _rows()
    assert row.api_key_encrypted is None and row.api_key_hint is None and row.key_updated_at
    p = next(p for p in (await owner_client.get(BASE)).json()["providers"] if p["name"] == "anthropic")
    assert p["has_key"] is False
    assert (await owner_client.delete(f"{BASE}/anthropic/key")).status_code == 404
    async with SessionLocal() as s:
        assert (await s.execute(select(AuditLog).where(AuditLog.action == "ai.key_cleared"))).scalar_one()


async def test_save_without_activating(owner_client: httpx.AsyncClient):
    r = await owner_client.patch(BASE, json={"provider": "anthropic", "api_key": ANTHROPIC_KEY, "activate": False})
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "fake" and r.json()["source"] == "env"  # vẫn chạy như cũ
    (row,) = await _rows()
    assert not row.is_active and decrypt(row.api_key_encrypted) == ANTHROPIC_KEY
    assert (await ai.run("test.inactive", Echo(text="x"), Echo)).provider == "fake"


async def test_validation(owner_client: httpx.AsyncClient):
    r = await owner_client.patch(BASE, json={"provider": "khong-co"})
    assert r.status_code == 400 and "khong-co" in r.json()["detail"]
    r = await owner_client.patch(BASE, json={"provider": "openrouter", "api_key": OPENROUTER_KEY})
    assert r.status_code == 400 and "model" in r.json()["detail"]  # OpenRouter phải tự nhập model
    r = await owner_client.patch(BASE, json={"provider": "anthropic", "api_key": "sk ant co khoang trang"})
    assert r.status_code == 422
    r = await owner_client.patch(BASE, json={"provider": "openrouter", "base_url": "ftp://x", "model_smart": "a/b"})
    assert r.status_code == 422
    assert await _rows() == []


def test_encryption_roundtrip_and_wrong_key(monkeypatch: pytest.MonkeyPatch):
    from app.core.secrets import encrypt, mask, redact

    token = encrypt(ANTHROPIC_KEY)
    assert ANTHROPIC_KEY not in token and decrypt(token) == ANTHROPIC_KEY
    assert encrypt(ANTHROPIC_KEY) != token  # IV ngẫu nhiên
    monkeypatch.setattr(settings, "secrets_encryption_key", OTHER_FERNET_KEY)
    with pytest.raises(SecretDecryptError) as e:
        decrypt(token)
    assert "SECRETS_ENCRYPTION_KEY" in e.value.message
    # xoay khoá: khoá mới đứng đầu, khoá cũ vẫn giải mã được
    from app.core.config import DEV_SECRETS_ENCRYPTION_KEY

    monkeypatch.setattr(settings, "secrets_encryption_key", f"{OTHER_FERNET_KEY},{DEV_SECRETS_ENCRYPTION_KEY}")
    assert decrypt(token) == ANTHROPIC_KEY
    assert mask(OPENROUTER_KEY) == "sk-or-v…9ZZZ" and mask(None) is None
    assert redact(f"lỗi với {OPENROUTER_KEY}", OPENROUTER_KEY) == "lỗi với ***"


async def test_wrong_encryption_key_fails_clearly_in_ai_run(owner_client, monkeypatch: pytest.MonkeyPatch):
    await owner_client.patch(BASE, json={"provider": "anthropic", "api_key": ANTHROPIC_KEY})
    monkeypatch.setattr(settings, "secrets_encryption_key", OTHER_FERNET_KEY)
    ai_config.invalidate()
    with pytest.raises(ai.AIUnavailable) as e:
        await ai.run("test.decrypt", Echo(text="x"), Echo)
    assert e.value.code == "secret_decrypt_failed" and "SECRETS_ENCRYPTION_KEY" in e.value.message
    async with SessionLocal() as s:
        run = (await s.execute(select(AIRun))).scalar_one()
    assert run.status == "error" and run.provider == "anthropic" and run.error_code == "secret_decrypt_failed"
    # GET vẫn chạy (không cần giải mã để hiện dạng che)
    assert (await owner_client.get(BASE)).status_code == 200


# ---- thứ tự ưu tiên + cache ---------------------------------------------------------------------------------------


async def test_db_config_overrides_env_and_applies_immediately(owner_client, openrouter, monkeypatch):
    seen = openrouter(lambda req: httpx.Response(200, json=_ok_body({"text": "xin chào"})))
    res = await ai.run("test.precedence", Echo(text="a"), Echo)
    assert res.provider == "fake"  # chưa cấu hình: chạy như hiện nay (AI_PROVIDER=fake)
    await ai_config.current_config()  # nạp cache

    r = await owner_client.patch(
        BASE, json={"provider": "openrouter", "api_key": OPENROUTER_KEY, "model_smart": "anthropic/claude-opus-5.5",
                    "model_fast": "anthropic/claude-haiku-5.5", "effort_fast": "medium"},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    res = await ai.run("test.precedence", Echo(text="b"), Echo, tier="fast")  # không đợi hết cache
    assert res.provider == "openrouter" and res.output.text == "xin chào"
    body = json.loads(seen[-1].content)
    assert body["model"] == "anthropic/claude-haiku-5.5" and body["reasoning"]["effort"] == "medium"
    assert seen[-1].headers["authorization"] == f"Bearer {OPENROUTER_KEY}"
    assert str(seen[-1].url) == "https://openrouter.ai/api/v1/chat/completions"
    # chi phí: OpenRouter tự báo usage.cost (USD) → dùng số đó
    assert res.cost_vnd == math.ceil(Decimal("0.0012") * settings.ai_usd_vnd_rate)

    # trường để trống trong Cài đặt → lấy biến môi trường
    cfg = await ai_config.load_config()
    assert cfg.smart.effort == settings.ai_effort_smart and cfg.source == "settings"
    # khoá trống ở Cài đặt + có biến môi trường → dùng biến môi trường
    await owner_client.delete(f"{BASE}/openrouter/key")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-v1-from-env-0000000000000000-1111")
    cfg = await ai_config.load_config()
    assert cfg.key_source == "env" and cfg.connection.api_key.endswith("1111")
    assert "1111" not in repr(cfg)  # khoá không lọt vào repr/log

    # chuyển về AI giả ở Cài đặt
    await owner_client.patch(BASE, json={"provider": "fake"})
    assert (await ai.run("test.precedence", Echo(text="c"), Echo)).provider == "fake"
    assert [r.provider for r in await _rows() if r.is_active] == ["fake"]


async def test_cache_is_short_and_invalidated(monkeypatch: pytest.MonkeyPatch):
    first = await ai_config.current_config()
    async with SessionLocal() as s:
        s.add(AIProviderConfig(provider="openrouter", is_active=True, model_smart="x/y", model_fast="x/z"))
        await s.commit()
    assert (await ai_config.current_config()) is first  # còn trong cache
    monkeypatch.setattr(ai_config, "CACHE_SECONDS", 0.0)
    ai_config._cache = (0.0, first)  # hết hạn → đọc lại (tiến trình khác, vd worker)
    assert (await ai_config.current_config()).provider == "openrouter"


async def test_ai_runs_and_errors_never_contain_key(owner_client, openrouter):
    def _leaky(req: httpx.Request) -> httpx.Response:
        # máy chủ giả cố tình nhắc lại khoá trong lời báo lỗi
        return httpx.Response(400, json={"error": {"code": 400, "message": f"bad request for {OPENROUTER_KEY}"}})

    openrouter(_leaky)
    await owner_client.patch(
        BASE, json={"provider": "openrouter", "api_key": OPENROUTER_KEY, "model_smart": "a/b", "model_fast": "a/c"}
    )
    with pytest.raises(ai.AIError) as e:
        await ai.run("test.leak", Echo(text="x"), Echo)
    assert OPENROUTER_KEY not in e.value.message
    r = await owner_client.post(
        f"{BASE}/test", json={"provider": "openrouter", "model_smart": "a/b", "model_fast": "a/c"}
    )
    assert OPENROUTER_KEY not in r.text
    assert OPENROUTER_KEY not in await _raw_db_text()


# ---- kiểm tra kết nối ---------------------------------------------------------------------------------------------


async def test_connection_test_with_fake_records_runs(owner_client: httpx.AsyncClient):
    r = await owner_client.post(f"{BASE}/test", json={"provider": "fake"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["provider"] == "fake"
    assert [x["tier"] for x in data["results"]] == ["fast", "smart"]
    assert all(x["ok"] and x["model"] == "fake" and x["latency_ms"] >= 0 for x in data["results"])
    async with SessionLocal() as s:
        runs = list((await s.execute(select(AIRun))).scalars())
    assert [r.task for r in runs] == ["control.ai_ping", "control.ai_ping"]
    assert await _rows() == []  # kiểm tra không lưu cấu hình


async def test_connection_test_uses_unsaved_input_and_explains_errors(owner_client, openrouter):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        if req.headers["authorization"] != f"Bearer {OPENROUTER_KEY}":
            return httpx.Response(401, json={"error": {"code": 401, "message": "No auth credentials found"}})
        if body["model"] == "a/khong-co":
            return httpx.Response(404, json={"error": {"code": 404, "message": "No endpoints found for a/khong-co"}})
        return httpx.Response(200, json=_ok_body({"reply": "được"}, model=body["model"]))

    seen = openrouter(handler)
    form = {"provider": "openrouter", "model_smart": "a/khong-co", "model_fast": "a/fast"}
    r = await owner_client.post(f"{BASE}/test", json={**form, "api_key": "sk-or-v1-sai-khoa-000000000000"})
    fast, smart = r.json()["results"]
    assert not fast["ok"] and fast["code"] == "ai_auth" and "Khoá" in fast["error"]

    r = await owner_client.post(f"{BASE}/test", json={**form, "api_key": OPENROUTER_KEY})
    fast, smart = r.json()["results"]
    assert fast["ok"] and fast["model"] == "a/fast" and fast["cost_vnd"] > 0
    assert not smart["ok"] and smart["code"] == "ai_model_not_found" and "a/khong-co" in smart["error"]
    assert len(seen) == 4 and await _rows() == []
    async with SessionLocal() as s:
        runs = list((await s.execute(select(AIRun).where(AIRun.task == "control.ai_ping"))).scalars())
    assert len(runs) == 4 and sum(r.cost_vnd for r in runs) > 0  # tính vào sổ chi phí như lượt thường


# ---- lệnh nhập khoá từ biến môi trường -----------------------------------------------------------------------------


async def test_import_env_config_is_idempotent(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", ANTHROPIC_KEY)
    monkeypatch.setattr(settings, "openrouter_api_key", OPENROUTER_KEY)
    lines = await run_import()
    out = "\n".join(lines)
    assert ANTHROPIC_KEY not in out and OPENROUTER_KEY not in out and "sk-ant-…8AAA" in out
    rows = {r.provider: r for r in await _rows()}
    assert set(rows) == {"anthropic", "openrouter"}
    assert rows["anthropic"].is_active and not rows["openrouter"].is_active
    assert decrypt(rows["anthropic"].api_key_encrypted) == ANTHROPIC_KEY
    assert rows["anthropic"].model_smart == settings.ai_model_smart

    again = await run_import()
    assert all("giữ nguyên" in line for line in again)
    assert len(await _rows()) == 2
    assert ANTHROPIC_KEY not in await _raw_db_text()


# ---- bảng giá với model mới -------------------------------------------------------------------------------------


def test_unknown_model_priced_as_smart_with_warning(caplog: pytest.LogCaptureFixture):
    from app.ai.pricing import estimate_cost
    from app.ai.types import Usage

    with caplog.at_level("WARNING", logger="app.ai.pricing"):
        usd, _ = estimate_cost("model-la-hoan-toan", Usage(input_tokens=1_000_000), smart_model="claude-haiku-5-5")
    assert usd == Decimal("0.100000") and "model-la-hoan-toan" in caplog.text
    usd, _ = estimate_cost("x/khong-gia", Usage(input_tokens=1_000_000), smart_model="y/cung-khong-gia")
    assert usd == Decimal("4.000000")  # rơi về giá AI_MODEL_SMART (claude-opus-5-5)
    assert estimate_cost("bat-ky", Usage(input_tokens=10, reported_cost_usd=0.5))[0] == Decimal("0.500000")
