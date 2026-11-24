"""Cấu hình đọc từ biến môi trường (`api/.env`). Mọi biến có mặc định chạy được trên máy không cần khoá."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[2]

# Bảng giá mặc định (USD / 1 triệu token), theo tài liệu Claude API 11/2026. Đổi bằng AI_PRICING (JSON).
DEFAULT_AI_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.2, "cache_write": 5.0},
    "claude-opus-5": {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_write": 2.5},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "fake": {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # ứng dụng
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_name: str = "Hàng Chọn"
    web_base_url: str = "http://localhost:3010"
    api_base_url: str = "http://localhost:8010"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3010"])
    log_level: str = "INFO"
    timezone: str = "Asia/Ho_Chi_Minh"

    # dữ liệu
    database_url: str = "postgresql+asyncpg://hangchon:hangchon@localhost:5442/hangchon"
    database_echo: bool = False
    redis_url: str = "redis://localhost:6382/0"

    # xác thực
    jwt_secret: str = "dev-only-change-me-please-32-bytes-min"
    jwt_expire_minutes: int = 60 * 24 * 14
    cookie_name: str = "hc_session"
    cookie_secure: bool = False
    cookie_domain: str | None = None
    owner_email: str | None = "chi@hangchon.local"
    owner_password: str | None = "doimatkhau"
    owner_name: str = "Chị"
    create_owner_on_startup: bool = True

    # AI
    ai_provider: Literal["anthropic", "fake"] = "fake"
    anthropic_api_key: str | None = None
    ai_model_smart: str = "claude-opus-5-5"
    ai_model_fast: str = "claude-haiku-5-5"
    ai_effort_smart: str = "medium"
    ai_effort_fast: str = "low"
    ai_max_tokens: int = 16000
    ai_timeout_seconds: float = 300.0
    ai_max_retries: int = 2
    # "default" = bật server-side fallbacks khi model từ chối (chỉ áp cho model hỗ trợ); "" = tắt
    ai_fallbacks: str = "default"
    ai_fallback_models: list[str] = Field(default_factory=lambda: ["claude-opus-5-5", "claude-opus-5"])
    ai_monthly_budget_vnd: int = 1_500_000
    ai_usd_vnd_rate: int = 26_000
    ai_web_search_usd_per_1k: float = 10.0
    ai_pricing: Annotated[dict[str, dict[str, float]], NoDecode] = Field(default_factory=dict)

    # việc nền
    jobs_eager: bool = False  # True: enqueue chạy luôn trong tiến trình (test)

    # lưu trữ tệp
    storage_driver: str = "local"
    storage_local_dir: str = str(API_DIR / "storage")
    storage_public_base_url: str = "http://localhost:8010/api/files"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "auto"

    # tích hợp ngoài — driver mặc định là mock
    sources_driver: str = "mock"
    social_driver: str = "mock"
    payments_driver: str = "mock"
    shipping_driver: str = "mock"
    notify_driver: str = "mock"
    marketplaces_driver: str = "mock"
    einvoice_driver: str = "mock"

    onebound_api_key: str | None = None
    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_page_id: str | None = None
    meta_page_token: str | None = None
    meta_ig_user_id: str | None = None
    meta_webhook_verify_token: str | None = None
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    zalo_oa_id: str | None = None
    zalo_oa_access_token: str | None = None
    zalo_oa_secret: str | None = None
    sepay_api_key: str | None = None
    sepay_webhook_secret: str | None = None
    bank_code: str = "MOCKBANK"
    bank_account_no: str = "0000000000"
    bank_account_name: str = "HANG CHON"
    payment_code_prefix: str = "HC"
    ghn_token: str | None = None
    ghn_shop_id: str | None = None
    ghtk_token: str | None = None
    shipping_from_province: str = "Hà Nội"
    mock_shipping_step_seconds: int = 3600
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "Hàng Chọn <no-reply@hangchon.local>"
    shopee_partner_id: str | None = None
    shopee_partner_key: str | None = None
    tiktok_shop_app_key: str | None = None
    tiktok_shop_app_secret: str | None = None
    hooks_mock_secret: str = "mock-webhook-secret"

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, v: Any, info: Any) -> Any:
        """Biến môi trường để trống (`KEY=`) với trường tuỳ chọn → None."""
        if v == "" and info.field_name in cls.model_fields:
            ann = cls.model_fields[info.field_name].annotation
            if type(None) in getattr(ann, "__args__", ()):
                return None
        return v

    @field_validator("ai_pricing", mode="before")
    @classmethod
    def _parse_pricing(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v) if v.strip() else {}
        return v

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        return {**DEFAULT_AI_PRICING, **self.ai_pricing}

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
