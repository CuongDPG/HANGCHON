"""Cấu hình đọc từ biến môi trường (`api/.env`). Mọi biến có mặc định chạy được trên máy không cần khoá."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator
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


# Khoá ký phiên nằm công khai trong repo (mặc định + api/.env.example) → production từ chối khởi động.
INSECURE_JWT_SECRETS = {
    "dev-only-change-me-please-32-bytes-min",
    "doi-chuoi-nay-thanh-chuoi-ngau-nhien-dai-it-nhat-32-ky-tu",
}

# Mật khẩu chị mặc định (config + api/.env.example) nằm công khai trong repo.
INSECURE_OWNER_PASSWORDS = {"doimatkhau"}

# Khoá mã hoá bí mật dùng khi chưa đặt SECRETS_ENCRYPTION_KEY — công khai trong repo, chỉ dùng ở dev/test.
DEV_SECRETS_ENCRYPTION_KEY = "aGFuZ2Nob24tZGV2LW9ubHktc2VjcmV0cy1rZXktMzI="


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

    # AI — chị đổi được ở Cài đặt → «AI và khoá API» (lưu trong CSDL, ghi đè các biến dưới đây)
    ai_provider: str = "fake"  # tên provider trong app/ai/providers: anthropic | openrouter | fake
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Khoá mã hoá (Fernet) cho bí mật lưu trong CSDL; nhiều khoá cách nhau dấu phẩy để xoay khoá (khoá đầu để mã hoá)
    secrets_encryption_key: str | None = None
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
    # Hàng đợi arq. Nhiều bản làm việc dùng chung một Redis → mỗi bản một tên (dev.sh tự đặt theo tên thư mục),
    # để worker của bản này không nhận job của bản khác (rồi chạy trên nhầm CSDL).
    jobs_queue_name: str = "arq:queue"

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

    # chi tiết driver thật (mọi biến môi trường driver đọc qua đây, không đọc thẳng os.environ)
    # Mạng xã hội: driver theo từng kênh, dùng chung cho đăng bài (content) và hộp thư (inbox).
    # "facebook=meta,instagram=meta,threads=meta,zalo_oa=zalo_oa,tiktok=tiktok_draft"; kênh không khai → SOCIAL_DRIVER.
    social_channel_drivers: str = ""
    meta_graph_version: str = "v24.0"
    threads_user_id: str | None = None
    threads_access_token: str | None = None
    tiktok_access_token: str | None = None
    zalo_app_id: str | None = None
    zalo_oa_author: str = "Hàng Chọn"
    zalo_oa_broadcast: bool = False  # True: bài viết OA gửi luôn tới người quan tâm (tốn hạn mức tin)
    onebound_api_secret: str | None = None
    ghn_env: Literal["dev", "prod"] = "prod"
    ghtk_env: Literal["dev", "prod"] = "prod"
    ghtk_pick_name: str | None = None
    ghtk_pick_tel: str | None = None
    ghtk_pick_address: str | None = None
    ghtk_pick_district: str | None = None
    ghtk_pick_ward: str | None = None
    shopee_shop_id: str | None = None
    shopee_access_token: str | None = None
    tiktok_shop_access_token: str | None = None
    tiktok_shop_cipher: str | None = None
    # báo tin cho khách (g5): driver theo kênh, vd "zalo_oa=zalo_zns,email=email"; kênh không khai → NOTIFY_DRIVER
    notify_channel_drivers: str = ""
    smtp_tls: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = 20.0
    # Zalo ZNS / ZBS Template Message: access token OA (dùng chung ZALO_OA_ACCESS_TOKEN) hết hạn sau 25 giờ, làm mới
    # bằng refresh token (dùng một lần, mỗi lần đổi) + khoá bí mật ỨNG DỤNG; token mới lưu ở ZALO_TOKEN_FILE.
    zalo_app_secret: str | None = None
    zalo_oa_refresh_token: str | None = None
    zalo_token_file: str | None = None
    # {"order_received": {"template_id": "123456", "params": {"customer_name": "ten", "order_code": "ma_don"}}}
    zalo_zns_templates: Annotated[dict[str, dict[str, Any]], NoDecode] = Field(default_factory=dict)
    zalo_zns_development: bool = False  # True: gửi `mode=development` (chỉ tới quản trị viên OA/ứng dụng)
    # dựng video (f6)
    content_ffmpeg: bool = True
    content_font_path: str | None = None
    # sao lưu (k4): đường dẫn pg_dump; không có thì thử `docker exec <container> pg_dump`
    pg_dump_path: str | None = None
    pg_dump_docker_container: str | None = "hangchon-postgres-1"

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, v: Any, info: Any) -> Any:
        """Biến môi trường để trống (`KEY=`, hay gặp trong compose `${KEY:-}`): trường tuỳ chọn → None,
        trường khác → giá trị mặc định."""
        if v == "" and info.field_name in cls.model_fields:
            field = cls.model_fields[info.field_name]
            if type(None) in getattr(field.annotation, "__args__", ()):
                return None
            if not field.is_required() and field.annotation is not str:
                return field.get_default(call_default_factory=True)
        return v

    @field_validator("ai_pricing", "zalo_zns_templates", mode="before")
    @classmethod
    def _parse_pricing(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v) if v.strip() else {}
        return v

    @model_validator(mode="after")
    def _refuse_default_secrets_in_prod(self) -> Settings:
        """Production không khởi động với khoá ký phiên mặc định / trong ví dụ / quá ngắn."""
        if self.app_env == "prod" and (self.jwt_secret in INSECURE_JWT_SECRETS or len(self.jwt_secret) < 32):
            raise ValueError(
                "JWT_SECRET còn là giá trị mặc định hoặc ngắn hơn 32 ký tự: đặt chuỗi ngẫu nhiên riêng "
                "(vd `openssl rand -hex 32`) trước khi chạy production."
            )
        if (
            self.app_env == "prod"
            and self.create_owner_on_startup
            and self.owner_password
            and (self.owner_password in INSECURE_OWNER_PASSWORDS or len(self.owner_password) < 12)
        ):
            raise ValueError(
                "OWNER_PASSWORD còn là mật khẩu mẫu hoặc ngắn hơn 12 ký tự: tài khoản chị được tạo bằng mật khẩu này "
                "lúc khởi động, đặt chuỗi ngẫu nhiên riêng trước khi chạy production."
            )
        if self.app_env == "prod" and (
            not self.secrets_encryption_key or DEV_SECRETS_ENCRYPTION_KEY in self.secrets_encryption_key.split(",")
        ):
            raise ValueError(
                "SECRETS_ENCRYPTION_KEY chưa đặt hoặc còn là khoá dev: khoá API lưu trong CSDL được mã hoá bằng biến này. "
                'Sinh khoá bằng `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` '
                "trước khi chạy production."
            )
        return self

    @property
    def pricing(self) -> dict[str, dict[str, float]]:
        return {**DEFAULT_AI_PRICING, **self.ai_pricing}

    @property
    def allows_simulation(self) -> bool:
        """Endpoint giả lập (tiền về giả, tin đến giả, đơn sàn giả, webhook của driver mock, hành động mẫu) chỉ mở ở
        dev/test. Ở production luôn 404 — kể cả khi driver đang là `mock`."""
        return self.app_env in ("dev", "test")

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
