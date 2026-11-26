"""Nguồn hàng chị đặt ở *Cài đặt → Nguồn hàng*: mỗi sàn lấy hàng bằng cách nào + khoá của dịch vụ lấy hàng.

- Cách lấy hàng của từng sàn (`route`): `mock` (giả lập) · `web` (AI tìm trên web) · driver tài khoản (`onebound`,
  `rakuten`). Lưu ở dòng `app_settings` khoá `source_account.routes` = `{"routes": {sàn: driver}}`.
  Sàn chưa đặt thì theo `SOURCES_DRIVER` (nếu driver đó lấy được sàn này; không thì `web` khi driver env là thật).
- Khoá dịch vụ: mỗi tài khoản một dòng `source_account.<tài khoản>` (cùng dạng JSON và cùng mã hoá Fernet với
  `channel_account.*`, xem `channel_config`). Thứ tự **Cài đặt > biến môi trường**.

Bản chụp trong bộ nhớ được đọc lại cùng lúc với cấu hình kênh (`channel_config.refresh` gọi `refresh` ở đây): đầu mỗi
request API (≤ 5 giây), đầu mỗi job worker và ngay sau khi lưu.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import SourcePlatform
from app.integrations.channel_config import FieldSpec, Link, _f

log = logging.getLogger("app.sources")

PREFIX = "source_account."
ROUTES_KEY = "routes"
GENERAL = ("mock", "web")  # mọi sàn đều chọn được


@dataclass(frozen=True)
class AccountSpec:
    """Một dịch vụ lấy hàng cần khoá (OneBound, Rakuten…)."""

    account: str
    label: str
    driver: str
    platforms: tuple[SourcePlatform, ...]
    fields: tuple[FieldSpec, ...]
    needs: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    cost: tuple[str, ...] = ()
    links: tuple[Link, ...] = ()
    verified: bool = False  # đã thử với khoá thật chưa

    def field(self, key: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.key == key), None)


@dataclass(frozen=True)
class PlatformSpec:
    platform: SourcePlatform
    label: str
    accounts: tuple[str, ...] = ()  # tài khoản dịch vụ lấy được sàn này
    notes: tuple[str, ...] = field(default=())  # vì sao không có đường chính thức, AI đọc web được gì


ACCOUNTS: dict[str, AccountSpec] = {
    a.account: a
    for a in (
        AccountSpec(
            account="onebound",
            label="OneBound (1688, Taobao, Tmall)",
            driver="onebound",
            platforms=(SourcePlatform.ALIBABA_1688, SourcePlatform.TAOBAO, SourcePlatform.TMALL),
            fields=(
                _f("api_key", "API key", "onebound_api_key", secret=True),
                _f("api_secret", "API secret", "onebound_api_secret", secret=True),
            ),
            needs=(
                "Một tài khoản trên open.onebound.cn (dịch vụ trung gian của Trung Quốc, không phải Taobao/1688 chính thức).",
                "Đã nạp tiền hoặc mua gói gọi API, và bật các API: tìm theo từ khoá (item_search), chi tiết (item_get), "
                "tìm bằng ảnh (item_search_img, upload_img), đánh giá (item_review) cho taobao và 1688.",
            ),
            steps=(
                "Bước 1: Đăng ký tài khoản trên open.onebound.cn, xác minh email/điện thoại theo hướng dẫn của họ.",
                "Bước 2: Trong trang quản lý, chọn gói gọi API cho Taobao và 1688, nạp tiền; lấy API key và API secret.",
                "Bước 3: Dán key và secret vào đây, bấm «Lưu» rồi «Kiểm tra kết nối» (gọi thử một lần item_get).",
                "Bước 4: Ở thẻ 1688, Taobao, Tmall phía trên, chọn «Qua OneBound».",
            ),
            limits=(
                "Dữ liệu do OneBound lấy hộ, không phải API chính thức của Alibaba: thỉnh thoảng có thể chậm, thiếu trường hoặc đổi tên trường.",
                "Gói của chị có thể không gồm đánh giá (item_review): khi đó hồ sơ vẫn chạy, chỉ thiếu đánh giá.",
                "Xu hướng và giá sàn Việt Nam vẫn do AI tìm trên web.",
            ),
            cost=(
                "Tính tiền theo lần gọi, kể cả lần gọi không có kết quả (mã 2000); lỗi máy chủ của họ (mã 4000) không tính.",
                "Mỗi lần săn một đề tìm: khoảng 1 lần gọi mỗi sàn; mỗi hồ sơ món: 2 lần (chi tiết + đánh giá). "
                "«Kiểm tra kết nối» cũng tốn 1 lần gọi. Giá cụ thể xem bảng giá trên trang OneBound.",
            ),
            links=(
                Link("OneBound: trang chủ và đăng ký", "https://open.onebound.cn/"),
                Link("OneBound: tài liệu item_search", "https://open.onebound.cn/help/api/taobao.item_search.html"),
            ),
        ),
        AccountSpec(
            account="rakuten",
            label="Rakuten Web Service (Rakuten Ichiba)",
            driver="rakuten",
            platforms=(SourcePlatform.RAKUTEN,),
            fields=(
                _f(
                    "application_id",
                    "Application ID",
                    "rakuten_application_id",
                    hint="Dạng UUID, lấy ở Developer Dashboard của Rakuten (mã số kiểu cũ không còn dùng được).",
                ),
                _f(
                    "access_key",
                    "Access key",
                    "rakuten_access_key",
                    secret=True,
                    hint="Bắt đầu bằng «pk_», hiện cạnh Application ID.",
                ),
                _f(
                    "referer",
                    "Địa chỉ trang đã đăng ký",
                    None,
                    required=False,
                    hint="Tên miền chị khai khi tạo ứng dụng (vd https://hangchon.vn). Để trống = địa chỉ website của chị.",
                ),
            ),
            needs=(
                "Một tài khoản thành viên Rakuten (Rakuten ID), miễn phí.",
                "Một ứng dụng tạo trên Rakuten Developers (webservice.rakuten.co.jp → Developer Dashboard).",
            ),
            steps=(
                "Bước 1: Đăng nhập Rakuten Developers bằng Rakuten ID, mở Developer Dashboard, bấm tạo ứng dụng mới.",
                "Bước 2: Khai tên ứng dụng và địa chỉ website của chị (tên miền cho phép gọi); lưu lại.",
                "Bước 3: Chép Application ID và Access key vào đây, «Lưu» rồi «Kiểm tra kết nối» (tìm thử 1 món).",
                "Bước 4: Ở thẻ Rakuten phía trên, chọn «Qua Rakuten API».",
            ),
            limits=(
                "Chỉ lấy được Rakuten Ichiba (tìm theo từ khoá, chi tiết theo link). Tìm bằng ảnh, đánh giá, xu hướng "
                "vẫn do AI tìm trên web.",
                "Rakuten giới hạn tốc độ gọi (khoảng 1 lần/giây); hệ thống gọi lần lượt từng sàn nên ít khi chạm giới hạn.",
                "Năm 2026 Rakuten chuyển sang địa chỉ API mới (openapi.rakuten.co.jp) cần cả Access key; mã cũ dạng số không dùng được.",
            ),
            cost=("Miễn phí.",),
            links=(
                Link("Rakuten Developers", "https://webservice.rakuten.co.jp/"),
                Link(
                    "Rakuten: Ichiba Item Search API",
                    "https://webservice.rakuten.co.jp/documentation/ichiba-item-search",
                ),
            ),
        ),
    )
}

_WEB_LOGIN = (
    "AI tìm trên web đọc được trang công khai; trang sản phẩm Taobao/Tmall thường bắt đăng nhập hoặc giải mã xác minh "
    "nên AI hay chỉ thấy tên và giá trong kết quả tìm kiếm, ít khi đọc được đánh giá."
)

PLATFORMS: dict[SourcePlatform, PlatformSpec] = {
    p.platform: p
    for p in (
        PlatformSpec(
            SourcePlatform.ALIBABA_1688,
            "1688",
            ("onebound",),
            (
                "API chính thức open.1688.com chỉ cấp cho doanh nghiệp Trung Quốc (giấy phép kinh doanh, ngân hàng Trung "
                "Quốc), nên đi qua OneBound.",
                "AI tìm trên web: một số trang 1688 xem được không cần đăng nhập, kết quả không đều.",
            ),
        ),
        PlatformSpec(
            SourcePlatform.TAOBAO,
            "Taobao",
            ("onebound",),
            ("API chính thức open.taobao.com cần xác minh danh tính Trung Quốc và duyệt ứng dụng.", _WEB_LOGIN),
        ),
        PlatformSpec(SourcePlatform.TMALL, "Tmall", ("onebound",), ("Tmall dùng chung kho với Taobao.", _WEB_LOGIN)),
        PlatformSpec(
            SourcePlatform.PINDUODUO,
            "Pinduoduo",
            (),
            (
                "Chưa có đường API phù hợp cho người bán ở Việt Nam (nền tảng mở của Pinduoduo dành cho người bán và "
                "đối tác Trung Quốc).",
                "AI tìm trên web: trang Pinduoduo chủ yếu mở trong app, AI đọc được rất ít.",
            ),
        ),
        PlatformSpec(
            SourcePlatform.ALIBABA,
            "Alibaba.com",
            (),
            (
                "Alibaba.com (bán sỉ quốc tế) không có API tìm hàng công khai cho người mua.",
                "AI tìm trên web: trang sản phẩm Alibaba.com phần lớn xem được công khai (giá sỉ, số lượng tối thiểu).",
            ),
        ),
        PlatformSpec(
            SourcePlatform.RAKUTEN,
            "Rakuten",
            ("rakuten",),
            ("Rakuten có API chính thức miễn phí. AI tìm trên web cũng đọc được trang Rakuten.",),
        ),
        PlatformSpec(
            SourcePlatform.AMAZON_JP,
            "Amazon Nhật",
            (),
            (
                "Amazon đã ngừng PA-API 5 (2026), thay bằng Creators API: cần tài khoản Amazon Associates Nhật đã có "
                "đơn qua link giới thiệu — Hàng Chọn chưa nối.",
                "AI tìm trên web đọc được phần lớn trang Amazon Nhật.",
            ),
        ),
    )
}


def options(platform: SourcePlatform) -> tuple[str, ...]:
    spec = PLATFORMS.get(platform)
    return (*GENERAL, *(ACCOUNTS[a].driver for a in spec.accounts)) if spec else GENERAL


def account_of_driver(driver: str) -> AccountSpec | None:
    return next((a for a in ACCOUNTS.values() if a.driver == driver), None)


# ---- bản chụp trong bộ nhớ ---------------------------------------------------------------------------------------


@dataclass
class _Snapshot:
    raw: dict[str, dict[str, Any]] = field(default_factory=dict)
    plain: dict[str, dict[str, str]] = field(default_factory=dict)
    routes: dict[str, str] = field(default_factory=dict)


_snap = _Snapshot()


def reset() -> None:
    global _snap
    from app.integrations import source_profiles

    _snap = _Snapshot()
    source_profiles.reset()


async def read_all(db: AsyncSession) -> dict[str, dict[str, Any]]:
    from app.modules.control.models import AppSetting

    rows = (await db.execute(select(AppSetting).where(AppSetting.key.startswith(PREFIX)))).scalars()
    return {r.key.removeprefix(PREFIX): dict(r.value or {}) for r in rows}


async def refresh(db: AsyncSession) -> None:
    from app.integrations import source_profiles  # cấu hình nâng cao từng sàn đọc lại cùng nhịp
    from app.integrations.channel_config import _decode

    await source_profiles.refresh(db)
    raw = await read_all(db)
    routes = (raw.pop(ROUTES_KEY, None) or {}).get("routes") or {}
    _snap.raw = {k: v for k, v in raw.items() if k in ACCOUNTS}
    _snap.plain = {k: _decode(v) for k, v in _snap.raw.items()}
    _snap.routes = {
        p: d for p, d in routes.items() if p in {x.value for x in PLATFORMS} and d in options(SourcePlatform(p))
    }


def value(account: str, key: str) -> str | None:
    """Giá trị hiệu lực: Cài đặt > biến môi trường > None."""
    v = (_snap.plain.get(account) or {}).get(key)
    if v:
        return v
    spec = ACCOUNTS.get(account)
    f = spec.field(key) if spec else None
    env = getattr(settings, f.env, None) if f and f.env else None
    return str(env) if env not in (None, "") else None


def source(account: str, key: str) -> Literal["settings", "env"] | None:
    if (_snap.plain.get(account) or {}).get(key):
        return "settings"
    return "env" if value(account, key) else None


def ready(account: str) -> bool:
    return all(value(account, f.key) for f in ACCOUNTS[account].fields if f.required)


def has_routes() -> bool:
    return bool(_snap.routes)


def db_route(platform: SourcePlatform) -> str | None:
    return _snap.routes.get(platform.value)


def env_route(platform: SourcePlatform) -> str:
    env = str(settings.sources_driver or "mock")
    if env in options(platform):
        return env
    return "mock" if env == "mock" else "web"


def route(platform: SourcePlatform) -> str:
    """Driver lấy hàng của một sàn: Cài đặt > SOURCES_DRIVER. Sàn không có thẻ (Amazon Mỹ, Tiểu Hồng Thư…) → `general`."""
    if platform not in PLATFORMS:
        return general()
    return db_route(platform) or env_route(platform)


def general() -> str:
    """Việc không gắn với một sàn (xu hướng, giá sàn Việt Nam, link trang lạ): có sàn nào chạy thật thì AI tìm trên web."""
    if _snap.routes:
        return "web" if any(route(p) != "mock" for p in PLATFORMS) else "mock"
    env = str(settings.sources_driver or "mock")
    return env if env in GENERAL else "web"


def drivers_in_use() -> list[str]:
    return list(dict.fromkeys(route(p) for p in PLATFORMS))


# ---- ghi ---------------------------------------------------------------------------------------------------------


async def load_raw(db: AsyncSession, key: str) -> dict[str, Any]:
    from app.modules.control.models import AppSetting

    row = await db.get(AppSetting, PREFIX + key)
    return dict(row.value or {}) if row else {}


async def write_raw(db: AsyncSession, key: str, raw: dict[str, Any], user_id: Any = None) -> None:
    from app.core.timeutil import now_utc
    from app.modules.control.models import AppSetting

    row = await db.get(AppSetting, PREFIX + key)
    if row is None:
        row = AppSetting(key=PREFIX + key, value=raw)
        db.add(row)
    row.value = raw
    row.updated_at = now_utc()
    row.updated_by_id = user_id
    await db.flush()
