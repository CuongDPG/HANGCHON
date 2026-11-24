"""Quy ước theo kênh: kênh nào soạn bản gì, giờ đăng mặc định, giới hạn độ dài, nhãn hiển thị."""

from __future__ import annotations

from app.core.enums import Channel
from app.modules.content.models import DraftFormat

# Một sản phẩm lên web → 5 bản, mỗi kênh một cách viết (f1). Zalo = tin cho người quan tâm OA (nhóm khách quen).
PRODUCT_CHANNELS: list[tuple[Channel, DraftFormat]] = [
    (Channel.FACEBOOK, DraftFormat.POST),
    (Channel.INSTAGRAM, DraftFormat.CAROUSEL),
    (Channel.THREADS, DraftFormat.POST),
    (Channel.TIKTOK, DraftFormat.VIDEO_SCRIPT),
    (Channel.ZALO_OA, DraftFormat.ZALO_MESSAGE),
]

# Một đợt mở bán → bài báo mở đợt trên Facebook, Instagram và tin Zalo cho khách quen.
DROP_CHANNELS: list[tuple[Channel, DraftFormat]] = [
    (Channel.FACEBOOK, DraftFormat.POST),
    (Channel.INSTAGRAM, DraftFormat.CAROUSEL),
    (Channel.ZALO_OA, DraftFormat.ZALO_MESSAGE),
]

CONTENT_CHANNELS = [c for c, _ in PRODUCT_CHANNELS]

FORMAT_BY_CHANNEL: dict[Channel, DraftFormat] = dict(PRODUCT_CHANNELS)

CHANNEL_LABELS: dict[Channel, str] = {
    Channel.FACEBOOK: "Facebook",
    Channel.INSTAGRAM: "Instagram",
    Channel.THREADS: "Threads",
    Channel.TIKTOK: "TikTok",
    Channel.ZALO_OA: "Zalo",
}

# Giờ đăng mặc định (giờ Việt Nam) khi chưa đủ số liệu (f3). Sau đó học từ post_metrics.
DEFAULT_TIMES: dict[Channel, tuple[int, int]] = {
    Channel.FACEBOOK: (20, 0),
    Channel.INSTAGRAM: (12, 0),
    Channel.THREADS: (21, 0),
    Channel.TIKTOK: (19, 0),
    Channel.ZALO_OA: (19, 30),
}

# Ngày đăng trong tuần: Thứ Hai (0) → Thứ Bảy (5); Chủ nhật nghỉ.
POSTING_WEEKDAYS = (0, 1, 2, 3, 4, 5)
MAX_POSTS_PER_DAY = 3

# Độ dài thân bài (ký tự) hợp kênh — dùng cho soát lời (f5). Threads giới hạn 500 ký tự, Instagram 2.200 và 30 hashtag.
LENGTH_LIMITS: dict[Channel, tuple[int, int]] = {
    Channel.FACEBOOK: (120, 1800),
    Channel.INSTAGRAM: (60, 2200),
    Channel.THREADS: (20, 500),
    Channel.TIKTOK: (20, 2200),
    Channel.ZALO_OA: (40, 1200),
}
MAX_HASHTAGS: dict[Channel, int] = {Channel.INSTAGRAM: 30, Channel.THREADS: 1, Channel.TIKTOK: 8}
VIDEO_SECONDS = (20, 30)

# Cách viết riêng từng kênh — đưa vào prompt.
CHANNEL_GUIDE: dict[str, str] = {
    "facebook": "Bài Facebook 120–250 chữ: mở bằng một câu chuyện dùng thật, nói lý do chọn, một điều chưa ưng, "
    "kết bằng lời mời nhắn tin hoặc xem link. Xuống dòng thành đoạn ngắn, tối đa 3 hashtag.",
    "instagram": "Bộ ảnh Instagram: chú thích 60–120 chữ, câu đầu bắt mắt, 5–10 hashtag tiếng Việt và tiếng Anh. "
    "Kèm thứ tự ảnh: mỗi ảnh một câu chú thích ngắn (slides), ảnh đầu là ảnh đẹp nhất.",
    "threads": "Threads: 1–3 câu ngắn như đang nói chuyện, dưới 400 ký tự, có thể hỏi lại người đọc. "
    "Không hashtag hoặc một hashtag.",
    "tiktok": "Kịch bản TikTok 20–30 giây: 4–6 cảnh (scenes), mỗi cảnh ghi số giây, hình (bàn tay, món hàng — "
    "không lộ mặt), lời thoại chị đọc, chữ trên hình ngắn. Cảnh đầu 2–3 giây phải có lý do để xem tiếp. "
    "Thân bài (body) là chú thích đăng kèm, dưới 150 ký tự.",
    "zalo_oa": "Tin Zalo cho khách quen: thân mật, 50–120 chữ, như nhắn cho người quen, nói rõ món gì, "
    "giá (nếu có), cách đặt. Không hashtag.",
}


def channel_label(channel: Channel | str) -> str:
    try:
        return CHANNEL_LABELS.get(Channel(channel), str(channel))
    except ValueError:
        return str(channel)
