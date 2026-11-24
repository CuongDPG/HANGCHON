"""Từ vựng nhỏ cho hàm giả AI (provider `fake`): đủ để đề «giá phơi gấp gọn» ra ứng viên có tên, lý do, từ khoá
tiếng Trung/Nhật đọc được như thật. Không dùng khi chạy AI thật."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from unidecode import unidecode


@dataclass(frozen=True)
class ItemType:
    vi: str  # danh từ gốc tiếng Việt («giá phơi»)
    zh: tuple[str, ...]
    ja: tuple[str, ...]
    en: tuple[str, ...]
    category: str  # tên nhóm hàng (catalog.categories.name)
    variants: tuple[tuple[str, str], ...] = ()  # (đuôi tên, điều đáng xem)
    weight_grams: int = 500


GENERIC_VARIANTS: tuple[tuple[str, str], ...] = (
    ("bản inox 304", "chất liệu ghi rõ inox 304, có ảnh cận mối nối"),
    ("bản gấp gọn", "gấp lại gọn, cất ngăn kéo được"),
    ("kiểu Nhật tối giản", "thiết kế gọn, màu trung tính dễ hợp nhà"),
    ("cỡ lớn", "kích thước lớn hơn mặt bằng hàng đang bán ở Việt Nam"),
    ("bản mini", "nhỏ, nhẹ, dễ mang theo"),
    ("có nắp gioăng", "nắp có gioăng silicon, người mua khen kín"),
    ("màu be", "màu be trung tính, ít bám bẩn"),
    ("bản silicon thực phẩm", "silicon thực phẩm, chịu nhiệt tới 220°C"),
    ("bản dày", "thành dày hơn bản thường, ít móp"),
)

TYPES: tuple[ItemType, ...] = (
    ItemType(
        "giá phơi",
        ("折叠晾衣架", "阳台晾衣架", "不锈钢晾衣架"),
        ("物干しラック", "折りたたみ物干し"),
        ("foldable drying rack",),
        "Sắp xếp, lưu trữ",
        (
            ("chữ X, inox 304", "mối hàn kín, ống inox 304, đánh giá xấu chủ yếu về đóng gói"),
            ("treo lan can", "móc thẳng vào lan can, không chiếm sàn ban công"),
            ("gấp 3 tầng", "3 tầng, phơi được cả chăn mỏng"),
            ("cánh bướm có bánh xe", "có bánh xe khoá được, kéo vào nhà khi mưa"),
            ("dựng sau cửa", "gấp lại dày khoảng 6 cm, dựng sau cửa được"),
            ("kéo rút gắn tường", "gắn tường, rút ra khi cần, không vướng lối đi"),
            ("mini để bàn", "nhỏ gọn, hợp phơi đồ lót, tất của bé"),
            ("ống tròn inox dày", "ống inox dày 1,2 mm, người mua nói ít rung"),
            ("chân chữ A nhôm", "nhôm nhẹ, một tay xách được"),
            ("có móc treo đồ lót", "thêm 16 móc kẹp ở thanh dưới"),
        ),
        weight_grams=2100,
    ),
    ItemType(
        "bình giữ nhiệt",
        ("保温杯", "不锈钢保温杯"),
        ("保温ボトル", "真空断熱ボトル"),
        ("vacuum insulated bottle",),
        "Đồ mang theo",
        (
            ("lòng inox 316, 500 ml", "lòng inox 316, giữ nóng 12 giờ theo nhiều đánh giá"),
            ("nắp bật một tay", "nắp bật một tay, khoá chống đổ"),
            ("kiểu Nhật 350 ml", "nhẹ 200 g, vừa túi xách"),
            ("có quai xách", "quai silicon chắc, không mùi"),
            ("ống hút inox", "ống hút tháo rửa được"),
            ("cỡ 1 lít", "dung tích lớn cho người làm ngoài trời"),
        ),
        weight_grams=350,
    ),
    ItemType(
        "hộp cơm",
        ("不锈钢饭盒", "保温饭盒"),
        ("弁当箱", "ステンレス弁当箱"),
        ("stainless lunch box",),
        "Đồ mang theo",
        (
            ("inox 304 hai tầng", "hai tầng, nắp có gioăng, không đổ canh"),
            ("giữ nhiệt ba ngăn", "ba ngăn tách món, giữ ấm khoảng 4 giờ"),
            ("kiểu Nhật gỗ", "nắp gỗ đẹp, hợp đem đi làm"),
            ("có túi giữ nhiệt", "kèm túi giữ nhiệt, giá gần bằng hộp không túi"),
            ("dùng được lò vi sóng", "hộp trong bằng PP chịu nhiệt, cho vào lò vi sóng"),
        ),
        weight_grams=600,
    ),
    ItemType(
        "giá úp bát",
        ("沥水架", "碗架"),
        ("水切りラック",),
        ("dish drying rack",),
        "Nhà bếp",
        (
            ("inox hai tầng", "khay hứng nước nghiêng, nước chảy thẳng xuống bồn"),
            ("gấp gọn trên bồn", "cuộn lại cất ngăn kéo, đặt ngang bồn rửa"),
            ("có ống cắm đũa", "ống cắm đũa tháo rửa được"),
            ("kiểu Nhật một tầng", "gọn, hợp bếp nhỏ"),
        ),
        weight_grams=1200,
    ),
    ItemType("hộp đựng", ("收纳盒",), ("収納ケース",), ("storage box",), "Sắp xếp, lưu trữ", weight_grams=700),
    ItemType("kéo bếp", ("厨房剪刀",), ("キッチンバサミ",), ("kitchen scissors",), "Nhà bếp", weight_grams=200),
    ItemType("hũ", ("密封罐",), ("保存容器", "密閉容器"), ("airtight jar",), "Nhà bếp", weight_grams=400),
    ItemType(
        "thảm", ("防滑垫", "吸水地垫"), ("バスマット", "珪藻土マット"), ("bath mat",), "Phòng tắm", weight_grams=900
    ),
    ItemType("cọ", ("硅胶刷",), ("シリコンブラシ",), ("silicone brush",), "Nhà bếp", weight_grams=120),
    ItemType("móc", ("无痕挂钩",), ("粘着フック",), ("adhesive hook",), "Sắp xếp, lưu trữ", weight_grams=100),
    ItemType("khăn", ("毛巾",), ("タオル",), ("towel",), "Phòng tắm", weight_grams=300),
)

# Danh từ trong dữ liệu nguồn giả (tiếng Trung/Nhật) → tiếng Việt, cho hàm giả dịch
SOURCE_NOUNS: dict[str, str] = {
    "保温杯": "Bình giữ nhiệt",
    "收纳盒": "Hộp đựng đồ",
    "硅胶刷": "Cọ silicon",
    "沥水架": "Giá úp bát",
    "折叠衣架": "Móc phơi gấp",
    "密封罐": "Hũ kín hơi",
    "厨房剪刀": "Kéo bếp",
    "防滑垫": "Thảm chống trượt",
    "保温ボトル": "Bình giữ nhiệt",
    "収納ケース": "Hộp đựng đồ",
    "シリコンブラシ": "Cọ silicon",
    "水切りラック": "Giá úp bát",
    "折りたたみハンガー": "Móc phơi gấp",
    "保存容器": "Hộp bảo quản thực phẩm",
}

MATERIALS = ("inox 304", "inox 316", "inox", "silicon", "nhựa pp", "tre", "gỗ", "thủy tinh", "thuỷ tinh", "gốm", "nhôm")


def plain(text: str) -> str:
    """Bỏ dấu, chữ thường, gọn khoảng trắng."""
    return re.sub(r"\s+", " ", unidecode(text or "").lower()).strip()


def find_type(text: str) -> ItemType | None:
    """Tìm loại hàng trong câu: so có dấu trước; so không dấu chỉ với từ đủ dài (tránh «cọ» khớp «có»)."""
    lower = unicodedata.normalize("NFC", (text or "").lower())
    p = plain(text)
    best: ItemType | None = None
    for t in TYPES:
        hit = re.search(rf"(?<!\w){re.escape(t.vi)}(?!\w)", lower) or (
            len(plain(t.vi)) >= 6 and re.search(rf"\b{re.escape(plain(t.vi))}\b", p)
        )
        if hit and (best is None or len(t.vi) > len(best.vi)):
            best = t
    return best


def variants_for(t: ItemType | None) -> tuple[tuple[str, str], ...]:
    return t.variants if t and t.variants else GENERIC_VARIANTS


def capitalize(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def translate_title(original: str) -> str:
    for src, vi in SOURCE_NOUNS.items():
        if src in (original or ""):
            return vi
    return capitalize(re.sub(r"\s*#\d+$", "", original or "").strip()) or "Món chưa rõ tên"
