"""Cấu hình đọc link và ảnh của từng nguồn cung (*Cài đặt → Nguồn hàng → Cấu hình nâng cao*).

Mỗi sàn một **hồ sơ** (`Profile`): nhận ra link sản phẩm của sàn và mã món (ASIN, offer id, item id…), dựng lại link
ngắn chuẩn, bỏ tham số theo dõi, máy chủ ảnh hợp lệ, quy tắc đổi link ảnh nhỏ sang ảnh lớn, header khi tải ảnh, cách
đọc trang chi tiết và vài dòng dặn AI riêng cho sàn. Mặc định nằm trong code (`DEFAULTS`); chị sửa từng ô ở Cài đặt,
lưu ở `app_settings` khoá `source_profile.<sàn>` = `{"fields": {ô: giá trị}}` (chỉ những ô đã đổi). Thứ tự
**Cài đặt > mặc định**. Bản chụp đọc lại cùng nhịp với `source_config` (đầu request ≤ 5 giây, đầu job, sau khi lưu).

Dùng ở: kết quả tìm, đọc link / lấy chi tiết (`sources/_profiled.py`), driver `web` (link chuẩn + lời dặn AI + ảnh
đọc thẳng từ trang), lưu ảnh về kho (`sourcing/gallery.py`: máy chủ ảnh + header). Tài liệu: docs/source-accounts.md.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PREFIX = "source_profile."
GENERIC = "web"  # hồ sơ cho link trang lạ
FetchVia = Literal["route", "skip"]
FETCH_VIA = ("route", "skip")
MAX_IMAGES_CAP = 12  # gallery.MAX_IMAGES
# tham số theo dõi luôn bỏ (kể cả khi hồ sơ giữ mọi tham số bằng "*")
TRACKING = re.compile(
    r"^(utm_.*|fbclid|gclid|yclid|msclkid|igshid|mc_cid|mc_eid|spm|scm|ref|ref_|pd_rd_.*|pf_rd_.*|_encoding|"
    r"ali_trackid|ali_refid|clickTrackInfo|tracelog|utparam|share_crt_v|sp_tk|union_lens|ttid|pvid|xxc|abbucket)$",
    re.I,
)
HEADER_NAMES = ("Referer", "User-Agent", "Accept-Language", "Origin", "Accept")


@dataclass(frozen=True)
class Profile:
    platform: str
    label: str
    domains: tuple[str, ...] = ()  # tên miền của sàn (gồm tên miền con) → nhận ra link thuộc sàn nào
    url_patterns: tuple[str, ...] = ()  # regex có nhóm (?P<id>…) → mã món
    canonical_url: str = ""  # mẫu có {id}; trống = giữ link gốc, chỉ bỏ tham số
    keep_params: tuple[str, ...] = ("*",)  # tham số giữ lại; "*" = giữ mọi tham số trừ tham số theo dõi
    image_hosts: tuple[
        str, ...
    ] = ()  # máy chủ ảnh hợp lệ ("*.alicdn.com", "m.media-amazon.com/images/I/*"); trống = mọi nơi
    image_rewrites: tuple[dict[str, str], ...] = ()  # [{pattern, replace}] áp lần lượt → ảnh cỡ lớn
    fetch_headers: dict[str, str] = field(default_factory=dict)  # header khi tải ảnh / đọc trang (Referer…)
    fetch_via: FetchVia = "route"  # route = theo cách lấy hàng đã chọn · skip = không đọc trang (bị chặn)
    page_image_patterns: tuple[str, ...] = ()  # regex tìm ảnh trong HTML trang (máy chủ đọc thẳng, không tốn AI)
    prompt_hints: str = ""  # dặn thêm AI khi tìm / đọc trang của sàn
    max_images: int = MAX_IMAGES_CAP

    def view(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, tuple):
                d[k] = list(v)
        return d


EDITABLE = tuple(f.name for f in fields(Profile) if f.name not in ("platform", "label"))

_ALICDN_REWRITE = {"pattern": r"(\.(?:jpe?g|png|gif|webp))_[^/]*$", "replace": r"\1"}
_AMAZON_REWRITE = {"pattern": r"\._[A-Za-z0-9_,+-]+_\.(jpe?g|png|gif|webp)$", "replace": r".\1"}
_AMAZON_PAGE_IMAGES = (
    r'"hiRes":"(https://m\.media-amazon\.com/images/I/[^"]+)"',
    r'"large":"(https://m\.media-amazon\.com/images/I/[^"]+)"',
)
_AMAZON_HOSTS = ("m.media-amazon.com/images/I/*", "images-*.ssl-images-amazon.com/images/I/*")
_AMAZON_HINT = (
    "Amazon: ảnh sản phẩm là link https://m.media-amazon.com/images/I/<mã>.jpg trong khối ảnh chính (bỏ phần "
    "«._AC_SX300_» để lấy ảnh lớn); không lấy ảnh quảng cáo, logo, ảnh món khác. Giá thật là giá ở khối mua "
    "(«価格» / «Price»), không lấy giá trong mục «一緒に購入» hay món gợi ý."
)
_UA_DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

DEFAULTS: dict[str, Profile] = {
    p.platform: p
    for p in (
        Profile(
            "1688",
            "1688",
            domains=("1688.com",),
            url_patterns=(r"1688\.com/offer/(?P<id>\d{6,})\.html", r"[?&]offerId=(?P<id>\d{6,})"),
            canonical_url="https://detail.1688.com/offer/{id}.html",
            keep_params=(),
            image_hosts=("*.alicdn.com",),
            image_rewrites=(_ALICDN_REWRITE,),
            fetch_headers={"Referer": "https://detail.1688.com/"},
            prompt_hints="1688: giá sỉ theo bậc số lượng — ghi giá bậc thấp nhất và số lượng tối thiểu (起订量). "
            "Ảnh ở cbu01.alicdn.com; bỏ đuôi cỡ như «_400x400.jpg» để lấy ảnh lớn.",
        ),
        Profile(
            "taobao",
            "Taobao",
            domains=("taobao.com",),
            url_patterns=(r"taobao\.com/.*[?&](?:id|itemId)=(?P<id>\d{6,})", r"taobao\.com/item/(?P<id>\d{6,})\.htm"),
            canonical_url="https://item.taobao.com/item.htm?id={id}",
            keep_params=(),
            image_hosts=("*.alicdn.com", "*.tbcdn.cn"),
            image_rewrites=(_ALICDN_REWRITE,),
            fetch_headers={"Referer": "https://item.taobao.com/"},
            prompt_hints="Taobao: trang chi tiết thường bắt đăng nhập; không đọc được thì ghi rõ, không đoán giá. "
            "Ảnh ở img.alicdn.com / gw.alicdn.com.",
        ),
        Profile(
            "tmall",
            "Tmall",
            domains=("tmall.com", "tmall.hk"),
            url_patterns=(r"tmall\.(?:com|hk)/.*[?&](?:id|itemId)=(?P<id>\d{6,})",),
            canonical_url="https://detail.tmall.com/item.htm?id={id}",
            keep_params=(),
            image_hosts=("*.alicdn.com", "*.tbcdn.cn"),
            image_rewrites=(_ALICDN_REWRITE,),
            fetch_headers={"Referer": "https://detail.tmall.com/"},
            prompt_hints="Tmall dùng chung kho với Taobao; trang chi tiết thường bắt đăng nhập.",
        ),
        Profile(
            "pinduoduo",
            "Pinduoduo",
            domains=("yangkeduo.com", "pinduoduo.com"),
            url_patterns=(r"[?&]goods_id=(?P<id>\d{5,})",),
            canonical_url="https://mobile.yangkeduo.com/goods.html?goods_id={id}",
            keep_params=(),
            image_hosts=("*.pddpic.com", "*.yangkeduo.com"),
            image_rewrites=({"pattern": r"\?imageView2/.*$", "replace": ""},),
            prompt_hints="Pinduoduo chủ yếu mở trong app; trang web thường không có giá.",
        ),
        Profile(
            "alibaba",
            "Alibaba.com",
            domains=("alibaba.com",),
            url_patterns=(r"alibaba\.com/product-detail/(?:[^/?#]*_)?(?P<id>\d{8,})\.html",),
            keep_params=(),
            image_hosts=("*.alicdn.com",),
            image_rewrites=(_ALICDN_REWRITE,),
            prompt_hints="Alibaba.com: giá sỉ theo khoảng (USD) và MOQ; ghi giá thấp nhất và MOQ.",
        ),
        Profile(
            "rakuten",
            "Rakuten",
            domains=("rakuten.co.jp",),
            url_patterns=(r"item\.rakuten\.co\.jp/(?P<id>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",),
            canonical_url="https://item.rakuten.co.jp/{id}/",
            keep_params=(),
            image_hosts=("*.rakuten.co.jp", "*.r10s.jp"),
            image_rewrites=(
                {
                    "pattern": r"^https?://thumbnail\.image\.rakuten\.co\.jp/@0_mall/",
                    "replace": "https://image.rakuten.co.jp/",
                },
                {"pattern": r"\?_ex=\d+x\d+$", "replace": ""},
            ),
            prompt_hints="Rakuten: ảnh ở image.rakuten.co.jp / shop.r10s.jp (bỏ «?_ex=128x128» để lấy ảnh lớn).",
        ),
        Profile(
            "amazon_jp",
            "Amazon Nhật",
            domains=("amazon.co.jp",),
            url_patterns=(
                r"amazon\.co\.jp/(?:.*/)?(?:dp|gp/product|gp/aw/d|exec/obidos/ASIN|o/ASIN)/(?P<id>[A-Z0-9]{10})",
            ),
            canonical_url="https://www.amazon.co.jp/dp/{id}",
            keep_params=(),
            image_hosts=_AMAZON_HOSTS,
            image_rewrites=(_AMAZON_REWRITE,),
            fetch_headers={"Accept-Language": "ja-JP,ja;q=0.9", "User-Agent": _UA_DESKTOP},
            page_image_patterns=_AMAZON_PAGE_IMAGES,
            prompt_hints=_AMAZON_HINT,
        ),
        Profile(
            "amazon",
            "Amazon",
            domains=("amazon.com",),
            url_patterns=(
                r"amazon\.com/(?:.*/)?(?:dp|gp/product|gp/aw/d|exec/obidos/ASIN|o/ASIN)/(?P<id>[A-Z0-9]{10})",
            ),
            canonical_url="https://www.amazon.com/dp/{id}",
            keep_params=(),
            image_hosts=_AMAZON_HOSTS,
            image_rewrites=(_AMAZON_REWRITE,),
            fetch_headers={"Accept-Language": "en-US,en;q=0.9", "User-Agent": _UA_DESKTOP},
            page_image_patterns=_AMAZON_PAGE_IMAGES,
            prompt_hints=_AMAZON_HINT,
        ),
        Profile(
            "xiaohongshu",
            "Tiểu Hồng Thư",
            domains=("xiaohongshu.com", "xhslink.com"),
            url_patterns=(r"xiaohongshu\.com/(?:explore|discovery/item|goods-detail)/(?P<id>[0-9a-f]{24})",),
            keep_params=("xsec_token", "xsec_source"),
            image_hosts=("*.xhscdn.com",),
            image_rewrites=({"pattern": r"![^/]*$", "replace": ""},),
            prompt_hints="Tiểu Hồng Thư là bài review, không phải trang bán: ghi tên món được nhắc, không bịa giá.",
        ),
        Profile(GENERIC, "Trang khác (mặc định)"),
    )
}


# ---- bản chụp (mặc định + phần chị sửa) --------------------------------------------------------------------------

_overrides: dict[str, dict[str, Any]] = {}
_effective: dict[str, Profile] = {}
_compiled: dict[str, tuple[re.Pattern[str], ...]] = {}


def reset() -> None:
    _overrides.clear()
    _effective.clear()
    _compiled.clear()


async def read_all(db: AsyncSession) -> dict[str, dict[str, Any]]:
    from app.modules.control.models import AppSetting

    rows = (await db.execute(select(AppSetting).where(AppSetting.key.startswith(PREFIX)))).scalars()
    return {r.key.removeprefix(PREFIX): dict((r.value or {}).get("fields") or {}) for r in rows}


async def refresh(db: AsyncSession) -> None:
    raw = await read_all(db)
    reset()
    for platform, fs in raw.items():
        if platform not in DEFAULTS:
            continue
        try:
            _overrides[platform] = clean(fs)
        except ValueError:  # dòng hỏng (sửa tay trong CSDL): bỏ qua, dùng mặc định
            continue


def overrides(platform: str) -> dict[str, Any]:
    return dict(_overrides.get(platform) or {})


def build(platform: str, override: dict[str, Any] | None = None) -> Profile:
    base = DEFAULTS[platform]
    ov = _overrides.get(platform, {}) if override is None else override
    return replace(base, **{k: _tuple(v) for k, v in ov.items()}) if ov else base


def get(platform: str) -> Profile:
    p = str(platform)
    if p not in DEFAULTS:
        p = GENERIC
    if p not in _effective:
        _effective[p] = build(p)
    return _effective[p]


def all_profiles() -> list[Profile]:
    return [get(p) for p in DEFAULTS]


def _tuple(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(dict(x) if isinstance(x, dict) else x for x in v)
    return v


# ---- kiểm dữ liệu chị nhập ---------------------------------------------------------------------------------------

_HOST_PATTERN = re.compile(r"^[A-Za-z0-9*.\-]+(/[A-Za-z0-9*._\-/]*)?$")
_DOMAIN = re.compile(r"^[a-z0-9.\-]+\.[a-z]{2,}$")
_PARAM = re.compile(r"^[A-Za-z0-9_.\-*]{1,60}$")


def _regex(s: Any, label: str, *, need_id: bool = False, need_group: bool = False) -> str:
    if not isinstance(s, str) or not s.strip():
        raise ValueError(f"{label}: không được để trống.")
    if len(s) > 300:
        raise ValueError(f"{label}: dài quá 300 ký tự.")
    try:
        rx = re.compile(s)
    except re.error as e:
        raise ValueError(f"{label}: biểu thức «{s}» sai ({e}).") from e
    if need_id and "id" not in rx.groupindex:
        raise ValueError(f"{label}: «{s}» phải có nhóm (?P<id>…) để lấy mã món.")
    if need_group and rx.groups < 1:
        raise ValueError(f"{label}: «{s}» phải có một nhóm (…) bao quanh link ảnh.")
    return s


def _str_list(v: Any, label: str, max_items: int = 12) -> list[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{label}: phải là danh sách chữ.")
    out = [x.strip() for x in v if x.strip()]
    if len(out) > max_items:
        raise ValueError(f"{label}: tối đa {max_items} dòng.")
    return out


def clean(fs: dict[str, Any]) -> dict[str, Any]:
    """Kiểm và chuẩn hoá các ô chị sửa. Sai → ValueError (câu tiếng Việt)."""
    out: dict[str, Any] = {}
    for k, v in fs.items():
        if k not in EDITABLE:
            raise ValueError(f"Không có ô «{k}».")
        if k == "domains":
            ds = [d.lower().removeprefix("www.") for d in _str_list(v, "Tên miền")]
            for d in ds:
                if not _DOMAIN.match(d):
                    raise ValueError(f"Tên miền: «{d}» không hợp lệ (vd amazon.co.jp).")
            out[k] = ds
        elif k == "url_patterns":
            out[k] = [_regex(x, "Mẫu link sản phẩm", need_id=True) for x in _str_list(v, "Mẫu link sản phẩm")]
        elif k == "canonical_url":
            s = (v or "").strip() if isinstance(v, str) else None
            if s is None:
                raise ValueError("Link chuẩn: phải là chữ.")
            if s:
                if not s.startswith(("https://", "http://")) or "{id}" not in s:
                    raise ValueError(
                        "Link chuẩn: phải bắt đầu bằng https:// và có {id} (vd https://www.amazon.co.jp/dp/{id})."
                    )
                if "{" in s.replace("{id}", "") or "}" in s.replace("{id}", ""):
                    raise ValueError("Link chuẩn: chỉ dùng được {id}.")
            out[k] = s
        elif k == "keep_params":
            ps = _str_list(v, "Tham số giữ lại", 20)
            for p in ps:
                if not _PARAM.match(p):
                    raise ValueError(f"Tham số giữ lại: «{p}» không hợp lệ.")
            out[k] = ps
        elif k == "image_hosts":
            hs = [h.lower() for h in _str_list(v, "Máy chủ ảnh", 20)]
            for h in hs:
                if not _HOST_PATTERN.match(h) or h.startswith("/"):
                    raise ValueError(
                        f"Máy chủ ảnh: «{h}» không hợp lệ (vd *.alicdn.com hoặc m.media-amazon.com/images/I/*)."
                    )
            out[k] = hs
        elif k == "image_rewrites":
            if not isinstance(v, list) or len(v) > 10:
                raise ValueError("Quy tắc đổi link ảnh: tối đa 10 quy tắc.")
            rules = []
            for r in v:
                if not isinstance(r, dict) or not isinstance(r.get("replace", ""), str):
                    raise ValueError("Quy tắc đổi link ảnh: mỗi quy tắc gồm «tìm» và «thay bằng».")
                pat = _regex(r.get("pattern"), "Quy tắc đổi link ảnh")
                rep = r.get("replace") or ""
                try:
                    re.compile(pat).sub(rep, "")  # Python ≥ 3.12 kiểm «thay bằng» (\1, \g<x>) cả khi không khớp
                except (re.error, IndexError) as e:
                    raise ValueError(f"Quy tắc đổi link ảnh: «thay bằng» {rep!r} sai ({e}).") from e
                rules.append({"pattern": pat, "replace": rep})
            out[k] = rules
        elif k == "fetch_headers":
            if not isinstance(v, dict):
                raise ValueError("Header khi tải: phải là các cặp tên: giá trị.")
            hs2: dict[str, str] = {}
            for name, val in v.items():
                n = next((h for h in HEADER_NAMES if h.lower() == str(name).strip().lower()), None)
                if n is None:
                    raise ValueError(f"Header khi tải: chỉ dùng được {', '.join(HEADER_NAMES)}.")
                if not isinstance(val, str) or len(val) > 300 or any(c in val for c in "\r\n\0"):
                    raise ValueError(f"Header khi tải: giá trị của {n} không hợp lệ.")
                if val.strip():
                    hs2[n] = val.strip()
            out[k] = hs2
        elif k == "fetch_via":
            if v not in FETCH_VIA:
                raise ValueError("Cách đọc trang chi tiết: chỉ «route» hoặc «skip».")
            out[k] = v
        elif k == "page_image_patterns":
            out[k] = [_regex(x, "Mẫu ảnh trong trang", need_group=True) for x in _str_list(v, "Mẫu ảnh trong trang", 6)]
        elif k == "prompt_hints":
            if not isinstance(v, str) or len(v) > 1000:
                raise ValueError("Dặn thêm AI: tối đa 1.000 ký tự.")
            out[k] = v.strip()
        elif k == "max_images":
            if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= MAX_IMAGES_CAP:
                raise ValueError(f"Số ảnh tối đa: từ 1 đến {MAX_IMAGES_CAP}.")
            out[k] = v
    return out


# ---- áp dụng -----------------------------------------------------------------------------------------------------


def _patterns(p: Profile, key: str) -> tuple[re.Pattern[str], ...]:
    ck = f"{p.platform}:{key}:{hash(getattr(p, key))}"
    if ck not in _compiled:
        out = []
        for s in getattr(p, key):
            try:
                out.append(re.compile(s))
            except re.error:
                continue
        _compiled[ck] = tuple(out)
    return _compiled[ck]


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def detect(url: str, profiles: list[Profile] | None = None) -> Profile:
    """Hồ sơ của link: theo tên miền, rồi theo mẫu link; không khớp → hồ sơ chung."""
    ps = [p for p in (profiles or all_profiles()) if p.platform != GENERIC]
    host = _host(url)
    for p in ps:
        if any(host == d or host.endswith("." + d) for d in p.domains):
            return p
    for p in ps:
        if any(rx.search(url) for rx in _patterns(p, "url_patterns")):
            return p
    return next((p for p in (profiles or []) if p.platform == GENERIC), None) or get(GENERIC)


def extract_id(url: str, p: Profile) -> tuple[str | None, str | None]:
    """(mã món, mẫu đã khớp)."""
    for rx in _patterns(p, "url_patterns"):
        m = rx.search(url)
        if m and m.groupdict().get("id"):
            return m.group("id"), rx.pattern
    return None, None


def strip_params(url: str, keep: tuple[str, ...] | list[str]) -> str:
    try:
        u = urlparse(url)
    except ValueError:
        return url
    q = parse_qsl(u.query, keep_blank_values=True)
    if "*" in keep:
        q = [(k, v) for k, v in q if not TRACKING.match(k)]
    else:
        q = [(k, v) for k, v in q if k in keep]
    return urlunparse(u._replace(query=urlencode(q), fragment=""))


def canonical(url: str, p: Profile | None = None) -> str:
    """Link ngắn chuẩn của một link sản phẩm (để AI đọc được — web_fetch nhận tối đa 250 ký tự — và khử trùng)."""
    if not url or not url.startswith(("http://", "https://")):
        return url
    p = p or detect(url)
    pid, _ = extract_id(url, p)
    if pid and p.canonical_url:
        return p.canonical_url.replace("{id}", pid)
    return strip_params(url, p.keep_params)


def rewrite_image(url: str, p: Profile) -> tuple[str, list[str]]:
    """(link ảnh sau khi đổi, các quy tắc đã đổi)."""
    applied = []
    for r in p.image_rewrites:
        try:
            new = re.sub(r["pattern"], r.get("replace") or "", url)
        except (re.error, IndexError, KeyError):
            continue
        if new != url:
            applied.append(r["pattern"])
            url = new
    return url, applied


def image_allowed(url: str, p: Profile) -> bool:
    if not p.image_hosts:
        return True
    try:
        u = urlparse(url)
    except ValueError:
        return False
    host, path = (u.hostname or "").lower(), u.path or "/"
    for pat in p.image_hosts:
        h, _, rest = pat.partition("/")
        if not fnmatch.fnmatchcase(host, h) and not (h.startswith("*.") and host == h[2:]):
            continue
        if not rest or fnmatch.fnmatchcase(path, "/" + rest):
            return True
    return False


def clean_images(urls: list[str], p: Profile) -> list[str]:
    """Đổi sang ảnh lớn → bỏ ảnh ngoài máy chủ ảnh của sàn → khử trùng → tối đa `max_images`."""
    out: list[str] = []
    for u in urls:
        if not isinstance(u, str) or not u.startswith(("http://", "https://")):
            continue
        big, _ = rewrite_image(u.strip(), p)
        if image_allowed(big, p) and big not in out:
            out.append(big)
    return out[: max(1, min(p.max_images, MAX_IMAGES_CAP))]


def page_images(html: str, p: Profile) -> list[str]:
    found: list[str] = []
    for rx in _patterns(p, "page_image_patterns"):
        for m in rx.finditer(html):
            found.append((m.group(1) if rx.groups else m.group(0)).replace("\\/", "/"))
    return clean_images(found, p)


def try_link(url: str, image_url: str | None = None, profiles: list[Profile] | None = None) -> dict[str, Any]:
    """«Thử với một link» (không gọi AI, không gọi mạng)."""
    p = detect(url, profiles)
    pid, pattern = extract_id(url, p)
    out: dict[str, Any] = {
        "platform": p.platform,
        "label": p.label,
        "id": pid,
        "matched_pattern": pattern,
        "canonical_url": canonical(url, p),
        "fetch_via": p.fetch_via,
        "image": None,
    }
    if image_url:
        big, applied = rewrite_image(image_url.strip(), p)
        out["image"] = {"input": image_url, "output": big, "rules_applied": applied, "allowed": image_allowed(big, p)}
    return out
