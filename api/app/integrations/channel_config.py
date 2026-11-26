"""Tài khoản kênh chị nối ở *Cài đặt → Mạng xã hội*: thông tin từng kênh + công tắc giả lập ↔ thật.

Thứ tự lấy giá trị: **Cài đặt (CSDL) > biến môi trường > trống**. Công tắc chạy thật/giả lập của một kênh trong CSDL thắng
`SOCIAL_CHANNEL_DRIVERS` / `SOCIAL_DRIVER` / `MARKETPLACES_DRIVER`; kênh chưa đặt công tắc thì theo biến môi trường.

Lưu ở bảng `app_settings`, mỗi kênh một dòng khoá `channel_account.<kênh>` (JSON):
`{"mode", "values": {không bí mật}, "secrets": {khoá: Fernet}, "hints": {khoá: dạng che}, "meta": {tên tài khoản, hạn
token…}, "check": {kết quả «Kiểm tra kết nối»}, "oauth": {state đang chờ}}`. Bí mật chỉ lưu dạng mã hoá
(`app.core.secrets`, cùng cơ chế với khoá AI) và không bao giờ trả ra trình duyệt (chỉ dạng che 4 ký tự cuối).
Dòng này không hiện trong `GET /settings` (lọc theo tiền tố) và không sửa được qua `PATCH /settings`.

Driver đọc đồng bộ (`value()`, `mode()`) từ một bản chụp trong bộ nhớ; bản chụp được đọc lại tối đa mỗi
`CACHE_SECONDS` giây ở đầu mỗi request API (`RefreshMiddleware`) và đầu mỗi job worker (`app/worker.py`), và đọc lại ngay
sau khi lưu ở tiến trình đang lưu — giống cách cấu hình AI có hiệu lực ngay, kể cả worker.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.secrets import decrypt, encrypt, mask
from app.core.timeutil import now_utc

log = logging.getLogger("app.channels")

PREFIX = "channel_account."
CACHE_SECONDS = 5.0
Mode = Literal["mock", "real"]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    env: str | None = None  # tên thuộc tính trong `settings` (biến môi trường) dùng khi Cài đặt để trống
    secret: bool = False
    required: bool = True
    oauth: bool = False  # do nút «Kết nối» điền, chị không gõ tay
    hint: str = ""


@dataclass(frozen=True)
class Link:
    label: str
    url: str


@dataclass(frozen=True)
class ChannelSpec:
    channel: str
    label: str
    kind: Literal["social", "marketplaces", "manual"]
    driver: str  # driver thật của kênh
    fields: tuple[FieldSpec, ...] = ()
    oauth: bool = False  # có nút «Kết nối» (chuyển sang trang của nền tảng để cấp quyền)
    needs: tuple[str, ...] = ()  # «Chị cần chuẩn bị»
    steps: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    links: tuple[Link, ...] = ()
    uses: tuple[tuple[str, str], ...] = field(default=())  # (kênh, khoá) dùng chung từ thẻ khác

    def field(self, key: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.key == key), None)


def _f(key: str, label: str, env: str | None = None, **kw: Any) -> FieldSpec:
    return FieldSpec(key=key, label=label, env=env, **kw)


META_DOCS = Link("Meta: Bắt đầu với API Trang", "https://developers.facebook.com/docs/pages-api/getting-started")
META_TOKEN_DOCS = Link(
    "Meta: Mã truy cập dài hạn",
    "https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived",
)

SPECS: dict[str, ChannelSpec] = {
    s.channel: s
    for s in (
        ChannelSpec(
            channel="facebook",
            label="Trang Facebook",
            kind="social",
            driver="meta",
            fields=(
                _f("page_id", "ID Trang", "meta_page_id", hint="Dãy số, lấy từ /me/accounts trong Graph API Explorer."),
                _f(
                    "page_token",
                    "Mã truy cập Trang (dài hạn)",
                    "meta_page_token",
                    secret=True,
                    hint="Mã Trang lấy từ mã người dùng dài hạn thì không hết hạn.",
                ),
                _f(
                    "app_secret",
                    "Khoá bí mật ứng dụng Meta",
                    "meta_app_secret",
                    secret=True,
                    required=False,
                    hint="Chỉ cần khi nhận tin nhắn/bình luận qua webhook (kiểm chữ ký).",
                ),
                _f(
                    "webhook_verify_token",
                    "Mã xác minh webhook",
                    "meta_webhook_verify_token",
                    secret=True,
                    required=False,
                    hint="Chuỗi chị tự đặt, nhập giống hệt ở mục Webhooks của ứng dụng Meta.",
                ),
            ),
            needs=(
                "Một Trang Facebook chị có quyền tạo nội dung (không đăng được lên trang cá nhân hay nhóm qua API).",
                "Một ứng dụng trên developers.facebook.com (loại Doanh nghiệp) do chị làm quản trị.",
                "Quyền pages_show_list, pages_manage_posts, pages_manage_read_engagement, pages_manage_metadata.",
            ),
            steps=(
                "Bước 1: Mở Graph API Explorer, chọn ứng dụng của chị, tick 4 quyền trên rồi bấm «Generate Access Token».",
                "Bước 2: Đổi mã người dùng ngắn hạn sang dài hạn (Access Token Debugger → «Extend Access Token»).",
                "Bước 3: Với mã dài hạn đó, gọi GET /me/accounts: chép «id» (ID Trang) và «access_token» (mã Trang) vào đây.",
                "Bước 4: Bấm «Lưu», rồi «Kiểm tra kết nối» — đúng thì hiện tên Trang. Bật «Chạy thật» khi muốn đăng thật.",
            ),
            limits=(
                "Ứng dụng chưa qua Xét duyệt ứng dụng (App Review) chỉ dùng được với Trang của người có vai trò trong ứng dụng — đủ cho Trang của chị.",
                "Mã Trang mất hiệu lực khi chị đổi mật khẩu Facebook, gỡ quyền ứng dụng hoặc mất vai trò trên Trang: khi đó lấy lại mã.",
            ),
            links=(
                META_DOCS,
                META_TOKEN_DOCS,
                Link("Graph API Explorer", "https://developers.facebook.com/tools/explorer/"),
            ),
        ),
        ChannelSpec(
            channel="instagram",
            label="Instagram",
            kind="social",
            driver="meta",
            fields=(
                _f(
                    "ig_user_id",
                    "ID tài khoản Instagram công việc",
                    "meta_ig_user_id",
                    hint="Lấy bằng GET /{ID Trang}?fields=instagram_business_account.",
                ),
            ),
            uses=(("facebook", "page_token"),),
            needs=(
                "Tài khoản Instagram chuyên nghiệp (doanh nghiệp hoặc nhà sáng tạo) đã liên kết với Trang Facebook ở thẻ trên.",
                "Thẻ Trang Facebook đã có mã Trang — Instagram dùng chung mã đó.",
                "Quyền instagram_basic, instagram_content_publish, pages_read_engagement trong ứng dụng Meta.",
            ),
            steps=(
                "Bước 1: Trong Graph API Explorer (mã Trang ở thẻ Facebook, thêm 3 quyền trên), gọi GET /{ID Trang}?fields=instagram_business_account.",
                "Bước 2: Chép «id» trong instagram_business_account vào ô dưới, bấm «Lưu» rồi «Kiểm tra kết nối» (hiện @tên tài khoản).",
            ),
            limits=(
                "Ảnh/video phải ở địa chỉ công khai lúc đăng (website của chị phục vụ được).",
                "Nếu Trang yêu cầu «Ủy quyền đăng trên Trang» (PPA), chị phải hoàn tất trên Facebook trước khi đăng được.",
            ),
            links=(
                Link(
                    "Meta: Đăng nội dung lên Instagram",
                    "https://developers.facebook.com/docs/instagram-platform/content-publishing",
                ),
                Link(
                    "Meta: Người dùng Instagram (IG User)",
                    "https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user",
                ),
            ),
        ),
        ChannelSpec(
            channel="threads",
            label="Threads",
            kind="social",
            driver="meta",
            fields=(
                _f("user_id", "ID người dùng Threads", "threads_user_id"),
                _f(
                    "access_token",
                    "Mã truy cập Threads (dài hạn)",
                    "threads_access_token",
                    secret=True,
                    hint="Hiệu lực 60 ngày; hệ thống tự làm mới hằng tuần.",
                ),
            ),
            needs=(
                "Một ứng dụng Meta tạo với trường hợp sử dụng «Threads» (dùng ID và khoá bí mật ứng dụng Threads riêng).",
                "Tài khoản Threads của chị được mời làm «Người dùng thử Threads» của ứng dụng và đã chấp nhận.",
                "Quyền threads_basic, threads_content_publish (và threads_manage_insights để xem số liệu).",
            ),
            steps=(
                "Bước 1: Trong bảng điều khiển ứng dụng → Vai trò, mời tài khoản Threads của chị; chấp nhận trong Cài đặt Threads → Quyền.",
                "Bước 2: Tạo mã người dùng bằng Graph API Explorer (máy chủ graph.threads.net), đổi sang mã dài hạn (GET /access_token).",
                "Bước 3: Chép ID người dùng (GET /me?fields=id,username) và mã dài hạn vào đây, «Lưu» rồi «Kiểm tra kết nối».",
            ),
            limits=(
                "Mã dài hạn hết hạn sau 60 ngày nếu không làm mới; hệ thống tự làm mới (GET /refresh_access_token) khi mã đã cũ hơn 7 ngày.",
                "Quyền chị cấp có hiệu lực 90 ngày, chỉ tự gia hạn khi trang cá nhân Threads để công khai.",
            ),
            links=(
                Link("Meta: Bắt đầu với API Threads", "https://developers.facebook.com/docs/threads/get-started"),
                Link(
                    "Meta: Mã dài hạn Threads",
                    "https://developers.facebook.com/docs/threads/get-started/long-lived-tokens",
                ),
            ),
        ),
        ChannelSpec(
            channel="tiktok",
            label="TikTok",
            kind="social",
            driver="tiktok_draft",
            oauth=True,
            fields=(
                _f("client_key", "Client key", "tiktok_client_key"),
                _f("client_secret", "Client secret", "tiktok_client_secret", secret=True),
                _f("access_token", "Access token", "tiktok_access_token", secret=True, oauth=True),
                _f("refresh_token", "Refresh token", None, secret=True, required=False, oauth=True),
                _f("open_id", "Open ID", None, required=False, oauth=True),
            ),
            needs=(
                "Một ứng dụng trên developers.tiktok.com có Login Kit và Content Posting API.",
                "Ứng dụng được duyệt scope user.info.basic, video.upload (và video.list để xem số liệu).",
                "Địa chỉ chuyển hướng (Redirect URI) bên dưới đăng ký trong Login Kit; tên miền ảnh/video đã xác minh với TikTok.",
            ),
            steps=(
                "Bước 1: Tạo ứng dụng, thêm Login Kit + Content Posting API, dán Redirect URI bên dưới vào Login Kit (phải là https).",
                "Bước 2: Chép Client key và Client secret (mục Credentials) vào đây rồi bấm «Lưu».",
                "Bước 3: Bấm «Kết nối TikTok», đăng nhập TikTok và đồng ý. Hệ thống nhận token và tự làm mới (token chỉ sống 2 giờ).",
            ),
            limits=(
                "Hàng Chọn chỉ ĐẨY BẢN NHÁP vào hộp thư TikTok; chị mở app TikTok bấm đăng.",
                "Access token hiệu lực 2 giờ, refresh token 180 ngày và đổi mới mỗi lần làm mới — không dán tay được, phải bấm «Kết nối».",
                "Ứng dụng chưa qua kiểm duyệt (audit) chỉ đăng được ở chế độ riêng tư.",
            ),
            links=(
                Link("TikTok: Login Kit cho web", "https://developers.tiktok.com/doc/login-kit-web"),
                Link(
                    "TikTok: Đẩy nội dung (Upload)",
                    "https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content",
                ),
                Link(
                    "TikTok: Quản lý access token",
                    "https://developers.tiktok.com/doc/oauth-user-access-token-management",
                ),
            ),
        ),
        ChannelSpec(
            channel="zalo_oa",
            label="Zalo OA",
            kind="social",
            driver="zalo_oa",
            fields=(
                _f("oa_id", "OA ID", "zalo_oa_id"),
                _f("app_id", "ID ứng dụng Zalo", "zalo_app_id"),
                _f(
                    "app_secret",
                    "Khoá bí mật ứng dụng",
                    "zalo_app_secret",
                    secret=True,
                    hint="Dùng để tự làm mới token.",
                ),
                _f(
                    "oa_secret",
                    "Khoá bí mật OA (webhook)",
                    "zalo_oa_secret",
                    secret=True,
                    required=False,
                    hint="Chỉ cần khi nhận tin nhắn qua webhook (kiểm chữ ký).",
                ),
                _f("access_token", "Access token OA", "zalo_oa_access_token", secret=True),
                _f(
                    "refresh_token",
                    "Refresh token OA",
                    "zalo_oa_refresh_token",
                    secret=True,
                    hint="Dùng một lần; hệ thống tự lưu refresh token mới sau mỗi lần làm mới.",
                ),
            ),
            needs=(
                "Một Zalo Official Account (OA) chị là quản trị viên.",
                "Một ứng dụng trên developers.zalo.me liên kết với OA, đã bật nhóm quyền cần dùng (tin nhắn, bài viết).",
            ),
            steps=(
                "Bước 1: Trong ứng dụng Zalo → Official Account, liên kết OA của chị; chép ID ứng dụng và khoá bí mật ứng dụng vào đây.",
                "Bước 2: Mở «API Explorer» của Zalo for Developers, chọn ứng dụng + OA, lấy access token và refresh token của OA.",
                "Bước 3: Dán vào đây, «Lưu» rồi «Kiểm tra kết nối» (hệ thống làm mới token một lần để chắc khoá đúng).",
            ),
            limits=(
                "Access token OA sống 25 giờ, refresh token 3 tháng và chỉ dùng một lần: hệ thống tự làm mới và lưu lại.",
                "Bỏ quá 3 tháng không dùng thì refresh token hết hạn — chị lấy lại ở API Explorer.",
                "Nhóm Zalo không gửi được qua API: xem thẻ «Nhóm Zalo».",
            ),
            links=(
                Link(
                    "Zalo: Xác thực và ủy quyền cho ứng dụng",
                    "https://developers.zalo.me/docs/official-account/bat-dau/xac-thuc-va-uy-quyen-cho-ung-dung-new",
                ),
                Link("Zalo: API Explorer", "https://developers.zalo.me/tools/explorer"),
            ),
        ),
        ChannelSpec(
            channel="zalo_group",
            label="Nhóm Zalo",
            kind="manual",
            driver="manual",
            needs=("Không cần khoá gì.",),
            steps=(
                "Zalo không có API đăng vào nhóm: Hàng Chọn soạn bài, chị bấm «Sao chép» ở mục Nội dung rồi dán vào nhóm.",
            ),
        ),
        ChannelSpec(
            channel="shopee",
            label="Shopee",
            kind="marketplaces",
            driver="shopee",
            oauth=True,
            fields=(
                _f("partner_id", "Partner ID", "shopee_partner_id"),
                _f("partner_key", "Partner key", "shopee_partner_key", secret=True),
                _f("shop_id", "Shop ID", "shopee_shop_id", oauth=True),
                _f("access_token", "Access token", "shopee_access_token", secret=True, oauth=True),
                _f("refresh_token", "Refresh token", None, secret=True, required=False, oauth=True),
            ),
            needs=(
                "Tài khoản nhà phát triển trên open.shopee.com và một ứng dụng (App) đã được duyệt, có Partner ID + Partner key.",
                "Tên miền của Redirect URI bên dưới khai trong mục «Redirect URL Domain» của App.",
                "Tài khoản người bán Shopee (shop) của chị để cấp quyền.",
            ),
            steps=(
                "Bước 1: Trên Console của Shopee Open Platform, mở App, khai tên miền Redirect URL; chép Partner ID và Partner key vào đây, «Lưu».",
                "Bước 2: Bấm «Kết nối Shopee», đăng nhập tài khoản shop, nhập mã OTP và đồng ý cấp quyền.",
                "Bước 3: Hệ thống nhận Shop ID + token; access token 4 giờ được tự làm mới bằng refresh token (30 ngày).",
            ),
            limits=(
                "Mỗi lần cấp quyền tối đa 365 ngày; hết hạn thì bấm «Kết nối Shopee» lại.",
                "Tạo món mới trên Shopee vẫn làm trong Shopee (cần ngành hàng, ảnh tải lên Shopee); Hàng Chọn đồng bộ tồn, giá, đơn.",
            ),
            links=(
                Link("Shopee: Ủy quyền và xác thực", "https://open.shopee.com/developer-guide/20"),
                Link(
                    "Shopee: v2.shop.get_shop_info",
                    "https://open.shopee.com/documents/v2/v2.shop.get_shop_info?module=92&type=1",
                ),
            ),
        ),
        ChannelSpec(
            channel="tiktok_shop",
            label="TikTok Shop",
            kind="marketplaces",
            driver="tiktok_shop",
            oauth=True,
            fields=(
                _f("app_key", "App key", "tiktok_shop_app_key"),
                _f("app_secret", "App secret", "tiktok_shop_app_secret", secret=True),
                _f(
                    "service_id",
                    "Service ID",
                    None,
                    hint="Trên trang chi tiết App ở Partner Center (dùng cho link cấp quyền).",
                ),
                _f("access_token", "Access token", "tiktok_shop_access_token", secret=True, oauth=True),
                _f("refresh_token", "Refresh token", None, secret=True, required=False, oauth=True),
                _f("shop_cipher", "Shop cipher", "tiktok_shop_cipher", oauth=True),
            ),
            needs=(
                "Tài khoản Partner Center của TikTok Shop và một App (loại cho người bán) có App key, App secret, Service ID.",
                "Redirect URL của App đặt đúng địa chỉ bên dưới.",
                "Tài khoản người bán TikTok Shop của chị.",
            ),
            steps=(
                "Bước 1: Trong Partner Center → App & Service, đặt Redirect URL bằng địa chỉ bên dưới; chép App key, App secret, Service ID vào đây, «Lưu».",
                "Bước 2: Bấm «Kết nối TikTok Shop», đăng nhập tài khoản người bán và đồng ý.",
                "Bước 3: Hệ thống nhận token, lấy shop cipher của cửa hàng; access token (7 ngày) được tự làm mới.",
            ),
            limits=(
                "Khi App còn đang phát triển, chỉ «cửa hàng phát triển» (Seller Center test account) cấp quyền được.",
                "Quyền hết hạn theo thời hạn chị chọn lúc cấp; TikTok báo trước 30 ngày, khi đó bấm «Kết nối» lại.",
            ),
            links=(
                Link(
                    "TikTok Shop: Tổng quan ủy quyền",
                    "https://partner.tiktokshop.com/docv2/page/authorization-overview-202407",
                ),
                Link(
                    "TikTok Shop: Get Authorized Shops",
                    "https://partner.tiktokshop.com/docv2/page/get-authorized-shops-202309",
                ),
            ),
        ),
    )
}

SOCIAL_CHANNELS = tuple(c for c, s in SPECS.items() if s.kind == "social")
MARKETPLACE_CHANNELS = tuple(c for c, s in SPECS.items() if s.kind == "marketplaces")


# ---- bản chụp trong bộ nhớ (driver đọc đồng bộ) ------------------------------------------------------------------


@dataclass
class _Snapshot:
    raw: dict[str, dict[str, Any]] = field(default_factory=dict)
    plain: dict[str, dict[str, str]] = field(default_factory=dict)  # giá trị đã giải mã
    loaded_at: float = 0.0


_snap = _Snapshot()


def reset() -> None:
    """Xoá bản chụp (test, sau khi xoá CSDL)."""
    global _snap
    _snap = _Snapshot()


def invalidate() -> None:
    _snap.loaded_at = 0.0


def _decode(raw: dict[str, Any]) -> dict[str, str]:
    out = {k: str(v) for k, v in (raw.get("values") or {}).items() if v not in (None, "")}
    for k, token in (raw.get("secrets") or {}).items():
        if not token:
            continue
        try:
            out[k] = decrypt(token)
        except Exception:  # sai SECRETS_ENCRYPTION_KEY: coi như chưa có, «Kiểm tra kết nối» sẽ báo
            log.warning("Không giải mã được %s của kênh (sai SECRETS_ENCRYPTION_KEY?)", k)
    return out


async def read_all(db: AsyncSession) -> dict[str, dict[str, Any]]:
    from app.modules.control.models import AppSetting

    rows = (await db.execute(select(AppSetting).where(AppSetting.key.startswith(PREFIX)))).scalars()
    return {r.key.removeprefix(PREFIX): dict(r.value or {}) for r in rows if r.key.removeprefix(PREFIX) in SPECS}


async def refresh(db: AsyncSession | None = None) -> None:
    from app.core.db import SessionLocal

    if db is not None:
        raw = await read_all(db)
    else:
        async with SessionLocal() as s:
            raw = await read_all(s)
    _snap.raw = raw
    _snap.plain = {c: _decode(r) for c, r in raw.items()}
    _snap.loaded_at = time.monotonic()


async def ensure_fresh() -> None:
    if time.monotonic() - _snap.loaded_at < CACHE_SECONDS:
        return
    try:
        await refresh()
    except Exception as e:  # CSDL chưa sẵn sàng: dùng biến môi trường, thử lại sau
        _snap.loaded_at = time.monotonic()
        log.warning("Chưa đọc được cấu hình kênh từ CSDL: %s", e)


class RefreshMiddleware:
    """Đọc lại cấu hình kênh (≤ CACHE_SECONDS) trước mỗi request /api/ để driver thấy thay đổi của tiến trình khác."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api/") and scope["path"] != "/api/health":
            await ensure_fresh()
        await self.app(scope, receive, send)


def mode(channel: str) -> Mode | None:
    """Công tắc chị đặt ở Cài đặt; None = chưa đặt (theo biến môi trường)."""
    m = (_snap.raw.get(channel) or {}).get("mode")
    return m if m in ("mock", "real") else None


def value(channel: str, key: str) -> str | None:
    """Giá trị hiệu lực: Cài đặt > biến môi trường > None."""
    v = (_snap.plain.get(channel) or {}).get(key)
    if v:
        return v
    spec = SPECS.get(channel)
    f = spec.field(key) if spec else None
    env = getattr(settings, f.env, None) if f and f.env else None
    return str(env) if env not in (None, "") else None


def source(channel: str, key: str) -> Literal["settings", "env"] | None:
    if (_snap.plain.get(channel) or {}).get(key):
        return "settings"
    return "env" if value(channel, key) else None


def meta(channel: str) -> dict[str, Any]:
    return dict((_snap.raw.get(channel) or {}).get("meta") or {})


def has_db_config(channel: str) -> bool:
    r = _snap.raw.get(channel) or {}
    return bool(r.get("mode") or r.get("values") or r.get("secrets"))


# ---- ghi ---------------------------------------------------------------------------------------------------------


async def load_raw(db: AsyncSession, channel: str) -> dict[str, Any]:
    from app.modules.control.models import AppSetting

    row = await db.get(AppSetting, PREFIX + channel)
    return dict(row.value or {}) if row else {}


async def write_raw(db: AsyncSession, channel: str, raw: dict[str, Any], user_id: uuid.UUID | None = None) -> None:
    from app.modules.control.models import AppSetting

    row = await db.get(AppSetting, PREFIX + channel)
    if row is None:
        row = AppSetting(key=PREFIX + channel, value=raw)
        db.add(row)
    row.value = raw
    row.updated_at = now_utc()
    row.updated_by_id = user_id
    await db.flush()


def apply_changes(
    raw: dict[str, Any],
    spec: ChannelSpec,
    *,
    values: dict[str, str] | None = None,
    clear: list[str] | None = None,
) -> list[str]:
    """Ghi các ô chị nhập vào `raw` (bí mật thì mã hoá + dạng che). Trả về khoá đã đổi (không kèm giá trị)."""
    vals: dict[str, Any] = dict(raw.get("values") or {})
    secs: dict[str, Any] = dict(raw.get("secrets") or {})
    hints: dict[str, Any] = dict(raw.get("hints") or {})
    changed: list[str] = []
    for key in clear or []:
        if spec.field(key) is None:
            raise KeyError(key)
        if vals.pop(key, None) is not None or secs.pop(key, None) is not None:
            changed.append(key)
        hints.pop(key, None)
    for key, v in (values or {}).items():
        f = spec.field(key)
        if f is None:
            raise KeyError(key)
        v = (v or "").strip()
        if not v:
            continue  # ô bí mật để trống = giữ giá trị cũ
        if f.secret:
            secs[key] = encrypt(v)
            hints[key] = mask(v)
        else:
            if vals.get(key) == v:
                continue
            vals[key] = v
        changed.append(key)
    raw["values"], raw["secrets"], raw["hints"] = vals, secs, hints
    return changed


async def store_tokens(
    channel: str,
    tokens: dict[str, str | None],
    meta_update: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Lưu token nhận từ nền tảng (sau «Kết nối» hoặc làm mới) bằng phiên riêng, có hiệu lực ngay."""
    from app.core.db import SessionLocal

    async def _do(s: AsyncSession) -> None:
        raw = await load_raw(s, channel)
        apply_changes(raw, SPECS[channel], values={k: v for k, v in tokens.items() if v})
        raw["meta"] = {**(raw.get("meta") or {}), **(meta_update or {})}
        await write_raw(s, channel, raw)

    if db is not None:
        await _do(db)
    else:
        async with SessionLocal() as s:
            await _do(s)
            await s.commit()
    await refresh(db)
