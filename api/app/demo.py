"""Dữ liệu mẫu thống nhất cho mọi module: `uv run python -m app.seed --demo`.

Một câu chuyện liền mạch, chạy qua đúng các luồng thật (API trong tiến trình + sự kiện + hàng chờ duyệt) với AI giả và
driver giả, có tua thời gian (time-machine) để đợt cũ nằm đúng chỗ trong quá khứ:

  · 3 đề tìm (bình giữ nhiệt, giá phơi gấp gọn, đồ nhà tắm và góc đọc) · 26 ứng viên ở đủ 5 cột bảng chọn,
    có hồ sơ thẩm định, ghi chú thử, lý do chọn / loại · 3 nhà cung cấp, bảng giá vốn, đề xuất giá
  · 7 sản phẩm đã đăng · Đợt 1 đã về, đã giao, có đánh giá · Đợt 2 đang mở, đơn ở mọi trạng thái · Đợt 3 sắp mở
  · đơn đặt nguồn của đợt, lô bổ sung hàng giữ sẵn đang về · bài nháp / đã duyệt / đã đăng + lịch tuần
  · hội thoại ở cả ba tab hộp thư · sổ khách, khách quen, khách thử hàng · việc chờ duyệt của nhiều module
  · nhật ký AI · sổ doanh thu, chi phí · báo cáo tuần

Chạy lại không sinh trùng: đã có cờ `demo.seeded` thì bỏ qua. Tên người, số điện thoại, món hàng đều là ví dụ."""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.enums import SourcePlatform
from app.core.jobs import JOBS, job_context
from app.core.timeutil import VN_TZ, local_today, now_utc

log = logging.getLogger("app.seed")

MARK = "demo.seeded"
OWNER = "/api/desk"

SUPPLIERS = [
    ("sup_inox", {"name": "Xưởng inox Phật Sơn (ví dụ)", "kind": "factory", "platform": "1688", "country": "CN",
                  "language": "zh", "notes": "Hàng inox 304, MOQ 20, giao kho Quảng Châu 3 ngày."}),
    ("sup_jp", {"name": "Shop gia dụng Osaka (ví dụ)", "kind": "shop", "platform": "rakuten", "country": "JP",
                "language": "ja", "notes": "Hàng Nhật chính hãng, đóng gói kỹ."}),
    ("sup_agent", {"name": "Mua hộ Quảng Châu (ví dụ)", "kind": "purchasing_agent", "country": "CN",
                   "language": "vi", "agent_fee_pct": "3", "notes": "Gom hàng, kiểm đếm, gửi về Hà Nội."}),
]  # fmt: skip

# đề tìm: (khoá, lời chị)
BRIEFS = [
    ("binh", "Tìm bình giữ nhiệt inox 304 khoảng 500 ml, giữ nóng lâu, nắp kín, dưới 250k về tay, ưu tiên hàng Nhật"),
    ("gia", "Tìm giá phơi đồ gấp gọn cho ban công nhỏ, inox không gỉ, dưới 300k, đánh giá tốt"),
    ("nha", "Tìm đồ nhà tắm và góc đọc cho nhà nhỏ: khăn tắm cho bé, đèn kẹp đọc sách không pin, móc dán chịu lực"),
]

# ứng viên: (khoá, đề, tên, tên gốc, nền tảng, giá, tiền tệ, gram, sao, số đánh giá, nhà cung cấp, cột đích)
CANDIDATES = [
    ("p_binh", "binh", "Bình giữ nhiệt nắp bật 500 ml", "ワンタッチ真空ボトル 500ml", "rakuten", "1980", "JPY", 260, "4.7", 812, "sup_jp", "selected"),
    ("p_hop", "binh", "Hộp cơm inox 3 ngăn giữ nhiệt", "304不锈钢三格保温饭盒", "1688", "38", "CNY", 640, "4.8", 2140, "sup_inox", "selected"),
    ("c_mini", "binh", "Bình giữ nhiệt mini 350 ml", "迷你保温杯350ml", "taobao", "22", "CNY", 210, "4.6", 530, "sup_inox", "trial"),
    ("c_ly", "binh", "Ly giữ nhiệt có ống hút", "吸管保温杯", "1688", "18", "CNY", 300, "4.5", 960, "sup_inox", "sample"),
    ("c_inhinh", "binh", "Bình giữ nhiệt in hình hoạt hình", "卡通保温杯", "taobao", "15", "CNY", 280, "4.3", 410, None, "rejected"),
    ("c_thuytinh", "binh", "Bình thuỷ tinh lót inox 1 lít", "玻璃内胆保温壶1L", "1688", "45", "CNY", 1100, "4.4", 220, None, "rejected"),
    ("c_coc", "binh", "Cốc giữ nhiệt văn phòng có nắp", "办公室保温杯", "1688", "16", "CNY", 320, "4.6", 1500, None, "candidate"),
    ("c_binhnhat", "binh", "Bình giữ nhiệt Nhật 480 ml", "真空断熱ケータイマグ 480ml", "amazon_jp", "2480", "JPY", 240, "4.8", 3021, None, "candidate"),
    ("c_hoptron", "binh", "Hộp cơm tròn 2 tầng", "圆形双层饭盒", "taobao", "26", "CNY", 520, "4.5", 380, None, "candidate"),
    ("c_binhtre", "binh", "Bình giữ nhiệt cho trẻ em 400 ml", "儿童保温杯400ml", "1688", "24", "CNY", 280, "4.7", 690, None, "candidate"),
    ("p_gia", "gia", "Giá phơi chữ X gấp gọn", "X型折叠晾衣架", "1688", "31", "CNY", 2100, "4.8", 2140, "sup_inox", "selected"),
    ("p_kep", "gia", "Kẹp phơi inox (bộ 20 cái)", "不锈钢晾衣夹20个", "1688", "9", "CNY", 180, "4.9", 5200, "sup_inox", "selected"),
    ("c_lancan", "gia", "Giá phơi treo lan can", "ベランダ手すり物干し", "rakuten", "2980", "JPY", 1300, "4.5", 318, "sup_jp", "trial"),
    ("c_xoay", "gia", "Móc phơi tròn xoay 20 kẹp", "旋转晾衣架20夹", "taobao", "19", "CNY", 420, "4.6", 870, None, "sample"),
    ("c_nhua", "gia", "Giá phơi nhựa gấp", "塑料折叠晾衣架", "taobao", "21", "CNY", 1500, "4.2", 640, None, "rejected"),
    ("c_dung", "gia", "Cây phơi đứng 3 tầng", "三层落地晾衣架", "1688", "48", "CNY", 3600, "4.5", 410, None, "candidate"),
    ("c_rut", "gia", "Dây phơi rút gắn tường", "隐形伸缩晾衣绳", "1688", "12", "CNY", 260, "4.4", 990, None, "candidate"),
    ("c_giay", "gia", "Giá phơi giày ban công", "阳台晒鞋架", "taobao", "14", "CNY", 350, "4.3", 210, None, "candidate"),
    ("p_khan", "nha", "Khăn tắm sợi tre cho bé", "竹纤维婴儿浴巾", "1688", "28", "CNY", 380, "4.8", 1860, "sup_inox", "selected"),
    ("p_den", "nha", "Đèn kẹp đọc sách cắm dây USB", "USB夹式阅读灯", "1688", "25", "CNY", 290, "4.7", 1240, "sup_inox", "selected"),
    ("p_moc", "nha", "Móc dán tường chịu lực (bộ 10)", "強力粘着フック10個", "amazon_jp", "980", "JPY", 120, "4.6", 4410, "sup_jp", "selected"),
    ("c_aochoang", "nha", "Áo choàng tắm cho bé có mũ", "婴儿连帽浴袍", "taobao", "35", "CNY", 450, "4.6", 520, None, "trial"),
    ("c_densac", "nha", "Đèn đọc sách có pin sạc", "充电阅读灯", "1688", "29", "CNY", 310, "4.5", 760, None, "rejected"),
    ("c_khanmat", "nha", "Khăn mặt cotton (bộ 5)", "纯棉毛巾5条", "1688", "20", "CNY", 400, "4.4", 2300, None, "candidate"),
    ("c_ke", "nha", "Kệ góc nhà tắm dán tường", "浴室转角置物架", "taobao", "23", "CNY", 600, "4.5", 880, None, "candidate"),
    ("c_tham", "nha", "Thảm chống trượt nhà tắm", "浴室防滑垫", "1688", "17", "CNY", 700, "4.3", 450, None, "sample"),
]  # fmt: skip

# ghi chú thử của chị (mỗi dòng một ghi chú)
NOTES = {
    "p_binh": ["Rót nước sôi lúc 7 giờ, 5 giờ chiều vẫn còn ấm nóng", "Nắp bật một tay, lật ngược không rỉ giọt nào",
               "Hộp giấy hơi móp khi giao"],
    "p_hop": ["Ba ngăn kín, canh không tràn sang cơm", "Inox dày, rửa nhanh, không ám mùi",
              "Hơi nặng khi xách cả túi"],
    "p_gia": ["Phơi chăn mùa đông không võng", "Gấp lại dựng sau cửa rất gọn", "Ốc ở chân hơi lỏng, phải vặn lại"],
    "p_kep": ["Kẹp chặt, phơi áo len không tuột", "Một tuần ngoài nắng không gỉ"],
    "p_khan": ["Thấm nước nhanh, bé quấn không bị lạnh", "Giặt máy 10 lần vẫn mềm", "Màu nhạt hơn ảnh một chút"],
    "p_den": ["Ánh sáng vàng dịu, đọc lâu không mỏi mắt", "Kẹp chắc vào đầu giường", "Dây hơi ngắn, cần thêm dây nối"],
    "p_moc": ["Treo khăn ướt 2 tuần không bong", "Gỡ ra không để lại vết keo"],
    "c_mini": ["Nhỏ gọn bỏ túi, giữ ấm 4 tiếng"],
    "c_lancan": ["Kẹp lan can chắc nhưng chỉ hợp lan can tròn"],
    "c_aochoang": ["Vải dày, mũ hơi rộng với bé 2 tuổi"],
}  # fmt: skip

REASONS = {
    "p_binh": (["Giữ nóng tới chiều.", "Nắp bật một tay, không rỉ."], ["Hộp giấy dễ móp khi giao."]),
    "p_hop": (["Ba ngăn kín, không tràn.", "Inox dày, rửa nhanh."], ["Hơi nặng khi xách."]),
    "p_gia": (["Phơi chăn không võng.", "Gấp gọn sau cửa."], ["Ốc chân cần vặn lại sau vài tuần."]),
    "p_kep": (["Kẹp chặt, không tuột.", "Không gỉ sau một tuần phơi nắng."], ["Lò xo hơi cứng với tay trẻ nhỏ."]),
    "p_khan": (["Thấm nhanh, bé không bị lạnh.", "Giặt máy vẫn mềm."], ["Màu nhạt hơn ảnh."]),
    "p_den": (["Ánh sáng dịu, đọc lâu không mỏi.", "Không pin, cắm USB là dùng."], ["Dây hơi ngắn."]),
    "p_moc": (["Treo đồ ướt không bong.", "Gỡ không để vết keo."], ["Chỉ hợp tường phẳng, nhẵn."]),
}
REJECTS = {
    "c_inhinh": ("Nắp rỉ khi lật ngược, sơn in bong sau vài lần rửa", ["do_ben"]),
    "c_thuytinh": ("Nặng 1,1 kg và dễ vỡ khi giao xa", ["van_chuyen"]),
    "c_nhua": ("Khớp nhựa gãy sau một tuần phơi chăn", ["do_ben"]),
    "c_densac": ("Có pin sạc, chưa nhập được ở giai đoạn này", ["van_chuyen"]),
}
# cost sheet thêm cho món đã chọn: (cước nội địa VND)
PRICE = {"p_binh": 289000, "p_hop": 329000, "p_gia": 279000, "p_kep": 119000, "p_khan": 189000, "p_den": 239000,
         "p_moc": 99000}  # fmt: skip

CUSTOMERS = {
    "ha": ("Đào Thu Hà", "0900000101", "Hà Nội"),
    "minh": ("Lê Minh Anh", "0900000102", "Hà Nội"),
    "lan": ("Phạm Ngọc Lan", "0900000103", "Đà Nẵng"),
    "khoa": ("Đỗ Đức Khoa", "0900000104", "TP Hồ Chí Minh"),
    "huong": ("Trần Thu Hương", "0900000105", "Hải Phòng"),
    "mai": ("Vũ Thanh Mai", "0900000106", "Hà Nội"),
    "ngoc": ("Bùi Bảo Ngọc", "0900000107", "Cần Thơ"),
    "huy": ("Ngô Quang Huy", "0900000108", "Hà Nội"),
    "thao": ("Hoàng Phương Thảo", "0900000109", "Huế"),
}


@contextlib.contextmanager
def at(days_ago: float, hour: int | None = None) -> Iterator[None]:
    """Tua đồng hồ về quá khứ (time-machine, có trong nhóm dev). Không có thì chạy ở hiện tại."""
    try:
        import time_machine
    except ImportError:  # pragma: no cover - bản chạy thật không có time-machine
        yield
        return
    target = now_utc() - timedelta(days=days_ago)
    if hour is not None:
        local = target.astimezone(VN_TZ)
        target = datetime.combine(local.date(), time(hour, 0), tzinfo=VN_TZ)
    with time_machine.travel(target, tick=True):
        yield


class Story:
    def __init__(self, c: httpx.AsyncClient, public: httpx.AsyncClient) -> None:
        self.c, self.pub = c, public
        self.ids: dict[str, str] = {}
        self.products: dict[str, dict[str, Any]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.counts: dict[str, int] = {}

    def bump(self, k: str, n: int = 1) -> None:
        self.counts[k] = self.counts.get(k, 0) + n

    async def call(
        self, method: str, path: str, *, ok: tuple[int, ...] = (200, 201), public: bool = False, **kw: Any
    ) -> Any:
        r = await (self.pub if public else self.c).request(method, path, **kw)
        if r.status_code == 401 and not public:  # đồng hồ vừa tua: phiên cũ «chưa tới hạn» → đăng nhập lại
            await self.login()
            r = await self.c.request(method, path, **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} → {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else None

    async def login(self) -> None:
        self.c.cookies.clear()
        r = await self.c.post(
            f"{OWNER}/auth/login", json={"email": settings.owner_email, "password": settings.owner_password}
        )
        if r.status_code != 200:
            raise RuntimeError("Chưa đăng nhập được tài khoản chị (OWNER_EMAIL / OWNER_PASSWORD) để dựng dữ liệu mẫu.")

    async def approve(self, item_id: str, payload: dict[str, Any] | None = None) -> Any:
        return await self.call("POST", f"{OWNER}/control/approvals/{item_id}/approve",
                               json={"payload": payload} if payload else {})  # fmt: skip

    async def pending(self, action: str) -> list[dict[str, Any]]:
        res = await self.call("GET", f"{OWNER}/control/approvals", params={"status": "pending", "action": action,
                                                                            "size": 100})  # fmt: skip
        return res["items"]

    # ---- săn hàng, thẩm định, bàn chọn -----------------------------------------------------------------------------

    async def sourcing(self) -> None:
        from app.modules.sourcing.models import Candidate, CandidateOrigin

        for key, data in SUPPLIERS:
            self.ids[key] = (await self.call("POST", f"{OWNER}/supply/suppliers", json=data))["id"]
        for key, text in BRIEFS:
            b = await self.call("POST", f"{OWNER}/sourcing/briefs", json={"text": text})
            self.ids[key] = b["id"]
            self.bump("briefs")
        await self.call(
            "PATCH", f"{OWNER}/sourcing/briefs/{self.ids['gia']}", json={"status": "active"}, ok=(200, 400, 422)
        )
        async with SessionLocal() as s:
            for i, (key, brief, title, orig, plat, price, cur, grams, rating, reviews, sup, _) in enumerate(CANDIDATES):
                c = Candidate(
                    brief_id=uuid.UUID(self.ids[brief]), origin=CandidateOrigin.BRIEF_SCAN, title_vi=title,
                    title_original=orig, source_platform=SourcePlatform(plat),
                    source_url=f"https://example.com/{plat}/item/{i + 1001}", source_external_id=f"demo-{i + 1001}",
                    price_amount=Decimal(price), price_currency=cur, weight_grams=grams, rating=Decimal(rating),
                    review_count=reviews, sales_count=reviews * 3,
                    supplier_id=uuid.UUID(self.ids[sup]) if sup else None,
                    seller_name={"rakuten": "Shop Osaka (ví dụ)", "amazon_jp": "Amazon Nhật (ví dụ)"}.get(plat, "Xưởng ví dụ"),
                    rank_reason="Khớp đề: đúng chất liệu, nhiều đánh giá thật, giá về tay trong ngân sách.",
                    description_vi=f"{title}. Thông tin dịch từ trang gốc (ví dụ).",
                )  # fmt: skip
                s.add(c)
                await s.flush()
                self.ids[key] = str(c.id)
                self.bump("candidates")
            await s.commit()
        for key, *_rest in CANDIDATES:
            a = await self.call("POST", f"{OWNER}/assessment/candidates/{self.ids[key]}/run", json={})
            self.ids[f"a_{key}"] = a["id"]
            self.bump("assessments")
        # chị xác nhận điểm cho các món đã đi tiếp
        for key, *_rest, target in CANDIDATES:
            if target in ("selected", "trial"):
                await self.call("POST", f"{OWNER}/assessment/assessments/{self.ids['a_' + key]}/confirm-score")

    async def move(self, key: str, to: str, reason: str | None = None, tags: list[str] | None = None) -> Any:
        body: dict[str, Any] = {"to": to}
        if reason:
            body.update(reason=reason, reason_tags=tags or [])
        return await self.call("POST", f"{OWNER}/selection/candidates/{self.ids[key]}/stage", json=body)

    async def sample_and_trial(self, key: str, *, trial: bool = True) -> None:
        """Mua mẫu (đơn đặt mẫu chờ chị → duyệt → gửi → trả tiền → mẫu về) rồi đưa vào thử."""
        await self.move(key, "sample")
        pos = (await self.call("GET", f"{OWNER}/supply/purchase-orders", params={"candidate_id": self.ids[key]}))[
            "items"
        ]
        if pos and trial:
            po = pos[0]
            await self.approve(po["approval_item_id"])
            po = await self.call("POST", f"{OWNER}/supply/purchase-orders/{po['id']}/status", json={"to": "sent"})
            if po["total_vnd"]:
                await self.call("POST", f"{OWNER}/supply/purchase-orders/{po['id']}/payments",
                                json={"amount_vnd": po["total_vnd"]})  # fmt: skip
            for lot in po["inbound"]:
                await self.call("POST", f"{OWNER}/supply/inbound/{lot['id']}/milestones", json={"status": "delivered"})
        if trial:
            await self.move(key, "trial")
            for text in NOTES.get(key, []):
                await self.call("POST", f"{OWNER}/selection/candidates/{self.ids[key]}/notes", data={"text": text})
                self.bump("trial_notes")

    async def select(self, key: str) -> dict[str, Any]:
        """Đã chọn → AI soạn lý do → chị chốt → sản phẩm nháp → AI viết trang → giá vốn, giá → duyệt và đăng."""
        st = await self.move(key, "selected")
        good, bad = REASONS[key]
        await self.call("POST", f"{OWNER}/selection/decisions/{st['decision']['id']}/approve",
                        json={"reason_selected": good, "not_satisfied": bad})  # fmt: skip
        from app.modules.catalog.models import Product

        async with SessionLocal() as s:
            pid = (
                await s.execute(select(Product.id).where(Product.candidate_id == uuid.UUID(self.ids[key])))
            ).scalar_one()
        await JOBS["catalog.write_product_page"](job_context(), str(pid))
        row = next(r for r in CANDIDATES if r[0] == key)
        await self.call("POST", f"{OWNER}/supply/cost-sheets", json={
            "candidate_id": self.ids[key], "unit_price_amount": row[5], "currency": row[6], "weight_grams": row[7],
            "domestic_shipping_vnd": 8000, "supplier_id": self.ids[row[10]] if row[10] else None,
        })  # fmt: skip
        prop = await self.call("POST", f"{OWNER}/supply/price-proposals", json={"candidate_id": self.ids[key]})
        await self.approve(prop["approval_item_id"], {"price_vnd": PRICE[key]})
        if key == "p_kep":  # món giữ sẵn (bán cả theo đợt lẫn có sẵn)
            await self.call("PATCH", f"{OWNER}/catalog/products/{pid}", json={"sale_mode": "both"})
        if key == "p_khan":  # đồ dùng hằng ngày: nhắc mua lại sau 90 ngày
            await self.call("PUT", f"{OWNER}/crm/reorder-rules/{pid}", json={"cycle_days": 90})
        pub = await self.call("POST", f"{OWNER}/catalog/products/{pid}/publish")
        self.products[key] = pub
        self.ids[f"prod_{key}"] = str(pid)
        self.bump("products")
        await JOBS["content.compose_pending"](job_context())
        return pub

    async def publish_posts(self, product_key: str, channels: tuple[str, ...], *, publish: bool) -> None:
        """Duyệt bài các kênh cho một sản phẩm; `publish` = tới giờ đăng luôn (bài trong quá khứ)."""
        from app.modules.content.models import ScheduledPost

        studio = await self.call("GET", f"{OWNER}/content/studio/product/{self.ids['prod_' + product_key]}")
        for d in studio["drafts"]:
            if d["channel"] not in channels or d["status"] != "pending_review":
                continue
            out = await self.call("POST", f"{OWNER}/content/drafts/{d['id']}/approve", json={})
            post = out.get("post") or {}
            if publish and post.get("id"):
                async with SessionLocal() as s:
                    sp = await s.get(ScheduledPost, uuid.UUID(post["id"]))
                    sp.scheduled_at = now_utc() - timedelta(minutes=5)
                    await s.commit()
            self.bump("posts_approved")
        if publish:
            self.bump("posts_published", await JOBS["content.publish_due"](job_context()))

    # ---- đợt, đơn, giao hàng -------------------------------------------------------------------------------------

    async def drop(self, key: str, title: str, items: list[tuple[str, int]], *, opens_in_days: float = 0,
                   closes_in_days: float, arrival_days: int) -> dict[str, Any]:  # fmt: skip
        body: dict[str, Any] = {
            "title": title,
            "closes_at": (now_utc() + timedelta(days=closes_in_days)).isoformat(),
            "expected_arrival_date": (local_today() + timedelta(days=arrival_days)).isoformat(),
            "items": [{"product_id": self.ids["prod_" + k], "slots_total": slots, "max_per_order": 3} for k, slots in items],
        }  # fmt: skip
        if opens_in_days:
            body["opens_at"] = (now_utc() + timedelta(days=opens_in_days)).isoformat()
        d = await self.call("POST", f"{OWNER}/catalog/drops", json=body)
        res = await self.call("POST", f"{OWNER}/catalog/drops/{d['id']}/open")
        if res.get("approval_item_id") and res["status"] in ("draft", "pending_review"):
            await self.approve(res["approval_item_id"])
        self.ids[key] = d["id"]
        self.bump("drops")
        return d

    async def order(self, key: str, who: str, lines: list[tuple[str, int, str | None]], *, pay: bool = True,
                    method: str = "bank_transfer", src: str | None = None) -> dict[str, Any]:  # fmt: skip
        from app.integrations import get_driver

        name, phone, province = CUSTOMERS[who]
        body = {
            "items": [{"product_id": self.ids["prod_" + p], "drop_id": self.ids[d] if d else None, "quantity": q}
                      for p, q, d in lines],
            "name": name, "phone": phone, "address_line": "Số 12 ngõ Ví Dụ", "ward": "Phường Mẫu",
            "district": "Quận Mẫu", "province": province, "payment_method": method, "client_ref": f"demo-{key}",
            **({"src": src} if src else {}),
        }  # fmt: skip
        o = await self.call("POST", "/api/store/orders", json=body, public=True)
        if pay and method == "bank_transfer":
            drv = get_driver("payments")
            t = drv.simulate_transfer(o["payment"]["amount_due_vnd"], o["payment"]["transfer_content"])
            raw = json.dumps({"transfers": [t.model_dump(mode="json")]}).encode()
            await self.call("POST", "/api/hooks/payments/mock", public=True, content=raw,
                            headers={"X-Mock-Signature": drv.sign(raw), "content-type": "application/json"})  # fmt: skip
        self.orders[key] = o
        self.bump("orders")
        return o

    async def order_id(self, key: str) -> str:
        from app.modules.orders.models import Order

        async with SessionLocal() as s:
            return str((await s.execute(select(Order.id).where(Order.code == self.orders[key]["code"]))).scalar_one())

    async def ship(self, keys: list[str]) -> list[str]:
        ids = [await self.order_id(k) for k in keys]
        res = await self.call("POST", f"{OWNER}/orders/shipments", json={"order_ids": ids})
        return [r["shipment_id"] for r in res["results"] if r.get("shipment_id")]

    # ---- câu chuyện ---------------------------------------------------------------------------------------------

    async def run(self) -> None:
        # 5 tuần trước: ra đề, quét, thẩm định; mua mẫu những món đáng thử
        with at(35, 9):
            await self.sourcing()
            for key, *_rest, target in CANDIDATES:
                if target == "rejected" and key in ("c_inhinh", "c_nhua"):
                    await self.sample_and_trial(key)
                if key in ("p_gia", "p_khan", "p_binh", "p_hop", "p_kep", "p_den", "p_moc"):
                    await self.sample_and_trial(key)
        # 4 tuần trước: chọn giá phơi + khăn tắm, loại vài món, đăng bài
        with at(28, 10):
            for key, (reason, tags) in REJECTS.items():
                await self.move(key, "rejected", reason, tags)
            await self.select("p_gia")
            await self.select("p_khan")
            await self.publish_posts("p_gia", ("facebook", "instagram"), publish=True)
            await self.publish_posts("p_khan", ("facebook",), publish=True)
            await self.drop(
                "d1", "Đồ phơi và đồ tắm cho bé", [("p_gia", 40), ("p_khan", 60)], closes_in_days=6, arrival_days=20
            )
        with at(26, 20):  # đơn của đợt 1
            await self.order("d1_ha", "ha", [("p_gia", 1, "d1"), ("p_khan", 2, "d1")])
            await self.order("d1_minh", "minh", [("p_khan", 1, "d1")])
            await self.order("d1_lan", "lan", [("p_gia", 1, "d1")])
            await self.order("d1_khoa", "khoa", [("p_gia", 2, "d1")])
            await self.order("d1_huong", "huong", [("p_khan", 1, "d1")], method="cod")
        with at(22, 21):  # hết hạn → chốt đợt → đơn đặt nguồn
            await self.call("POST", f"{OWNER}/catalog/drops/{self.ids['d1']}/close")
        with at(21, 9):
            await self.receive_drop_batch_start("d1")
        with at(10, 10):  # lô về → đơn chờ giao → vận đơn
            await self.finish_inbound("d1")
            self.ship_ids = await self.ship(["d1_ha", "d1_minh", "d1_lan", "d1_khoa", "d1_huong"])
        with at(8, 18):  # giao xong (hãng giả lên nấc theo thời gian)
            for sid in self.ship_ids:
                await self.call("POST", f"{OWNER}/orders/shipments/{sid}/sync")
        with at(7, 20):  # khách gửi đánh giá
            await self.reviews()
        # 3 tuần trước: chọn thêm bình giữ nhiệt, hộp cơm, kẹp phơi, đèn kẹp, móc dán
        with at(18, 9):
            for key in ("p_binh", "p_hop", "p_kep", "p_den", "p_moc"):
                await self.select(key)
            await self.restock()
        # 5 ngày trước: mở đợt 2
        with at(5, 9):
            await self.drop(
                "d2",
                "Giữ nhiệt mùa đông",
                [("p_binh", 50), ("p_hop", 40), ("p_kep", 80)],
                closes_in_days=9,
                arrival_days=21,
            )
            await self.publish_posts("p_binh", ("facebook", "threads"), publish=True)
            await self.publish_posts("p_hop", ("facebook",), publish=True)
        with at(3, 20):
            src = await self.src_of("p_binh")
            await self.order("d2_ha", "ha", [("p_binh", 2, "d2")], src=src)  # khách quen quay lại
            await self.order("d2_minh", "minh", [("p_hop", 1, "d2"), ("p_kep", 1, "d2")])
            await self.order("d2_mai", "mai", [("p_binh", 1, "d2")], pay=False)  # chờ chuyển khoản
            await self.order("d2_ngoc", "ngoc", [("p_hop", 2, "d2")], method="cod")
            await self.order("d2_huy", "huy", [("p_binh", 1, "d2")])
        with at(2, 9):
            await self.call("POST", f"{OWNER}/orders/{await self.order_id('d2_huy')}/cancel",
                            json={"reason": "Khách đặt nhầm màu, xin huỷ"})  # fmt: skip
        with at(1, 15):  # hàng giữ sẵn: một đơn chờ gói, một đơn đã giao cho hãng
            await self.order("s_lan", "lan", [("p_kep", 1, None)])
            await self.order("s_thao", "thao", [("p_kep", 2, None)])
        with at(0.15):
            shipping = await self.ship(["s_thao"])
        for sid in shipping:  # hãng giả đã lấy hàng, đang giao
            await self.call("POST", f"{OWNER}/orders/shipments/{sid}/sync")
        await JOBS["orders.complete_delivered"](job_context())
        # đợt 3 sắp mở, lịch tuần, hộp thư, khách, sổ sách
        await self.drop(
            "d3",
            "Góc đọc và nhà tắm gọn",
            [("p_den", 30), ("p_moc", 60)],
            opens_in_days=3,
            closes_in_days=10,
            arrival_days=28,
        )
        await self.publish_posts("p_den", ("facebook",), publish=False)
        await self.content_week()
        with at(6, 9):  # ba món đang thử
            for key in ("c_mini", "c_lancan", "c_aochoang"):
                await self.sample_and_trial(key)
        await self.inbox()
        await self.crm()
        for key in ("c_ly", "c_xoay", "c_tham"):
            await self.move(key, "sample")  # đơn đặt mẫu nằm trong hàng chờ chị
        await self.books()

    async def receive_drop_batch_start(self, drop_key: str) -> None:
        """Duyệt đơn đặt lô của đợt, gửi bên mua hộ, trả tiền (lô đang trên đường về)."""
        from app.modules.supply.models import PurchaseOrder

        async with SessionLocal() as s:
            pos = list((await s.execute(select(PurchaseOrder.id).where(PurchaseOrder.drop_id == uuid.UUID(self.ids[drop_key])))).scalars())  # fmt: skip
        self.ids[f"po_{drop_key}"] = ",".join(str(p) for p in pos)
        for pid in pos:
            po = await self.call("GET", f"{OWNER}/supply/purchase-orders/{pid}")
            if po["status"] == "pending_approval":
                await self.approve(po["approval_item_id"])
            po = await self.call("POST", f"{OWNER}/supply/purchase-orders/{pid}/status", json={"to": "sent"})
            if po["total_vnd"]:
                await self.call(
                    "POST", f"{OWNER}/supply/purchase-orders/{pid}/payments", json={"amount_vnd": po["total_vnd"]}
                )
            for lot in po["inbound"]:
                for stt in ("seller_shipped", "at_agent_warehouse", "international_transit"):
                    await self.call("POST", f"{OWNER}/supply/inbound/{lot['id']}/milestones", json={"status": stt})

    async def finish_inbound(self, drop_key: str) -> None:
        for pid in filter(None, self.ids.get(f"po_{drop_key}", "").split(",")):
            po = await self.call("GET", f"{OWNER}/supply/purchase-orders/{pid}")
            for lot in po["inbound"]:
                for stt in ("customs", "domestic_transit", "delivered"):
                    await self.call("POST", f"{OWNER}/supply/inbound/{lot['id']}/milestones", json={"status": stt})

    async def reviews(self) -> None:
        from app.modules.catalog.models import Review

        for item in await self.pending("catalog.send_review_request"):  # chị duyệt tin xin đánh giá
            await self.approve(item["id"])

        texts = [
            (5, "Phơi được cả chăn đôi, gấp lại gọn sau cửa. Ốc chân mình vặn lại một lần là chắc."),
            (5, "Khăn mềm, bé thích quấn. Giặt máy mấy lần vẫn mềm như mới."),
            (4, "Giá phơi chắc, giao hơi lâu nhưng đúng như chị tả."),
            (3, "Khăn ổn nhưng màu nhạt hơn ảnh mình xem."),
        ]
        async with SessionLocal() as s:
            rows = list((await s.execute(select(Review.id, Review.token).order_by(Review.created_at))).all())
        for (rid, token), (rating, body) in zip(rows, texts, strict=False):
            await self.call("POST", f"/api/store/catalog/reviews/{token}", public=True,
                            data={"rating": str(rating), "body": body})  # fmt: skip
            self.bump("reviews")
            if rating >= 4:  # chị duyệt hiển thị; đánh giá 3★ để lại trong hàng chờ
                await self.call("POST", f"{OWNER}/catalog/reviews/{rid}/approve", ok=(200, 409))

    async def restock(self) -> None:
        """Hàng giữ sẵn kẹp phơi: một lô đã về (nhập tồn), một lô bổ sung đang trên đường."""
        for i, (qty, done) in enumerate(((30, True), (40, False))):
            po = await self.call("POST", f"{OWNER}/supply/purchase-orders", json={
                "kind": "restock", "supplier_id": self.ids["sup_inox"], "currency": "CNY",
                "notes": "Bổ sung kẹp phơi giữ sẵn",
                "lines": [{"product_id": self.ids["prod_p_kep"], "candidate_id": self.ids["p_kep"],
                           "description": "不锈钢晾衣夹20个", "quantity": qty, "unit_price_amount": "9"}],
            })  # fmt: skip
            await self.approve(po["approval_item_id"])
            po = await self.call("POST", f"{OWNER}/supply/purchase-orders/{po['id']}/status", json={"to": "sent"})
            steps = ("seller_shipped", "international_transit", "customs", "domestic_transit", "delivered") if done else (
                "seller_shipped", "international_transit")  # fmt: skip
            for lot in po["inbound"]:
                for stt in steps:
                    await self.call("POST", f"{OWNER}/supply/inbound/{lot['id']}/milestones", json={"status": stt})
            _ = i

    async def src_of(self, key: str) -> str | None:
        from app.modules.content.models import ContentDraft, PostStatus, ScheduledPost
        from app.modules.content.schedule import src_code

        async with SessionLocal() as s:
            sp = (
                await s.execute(
                    select(ScheduledPost).join(ContentDraft, ContentDraft.id == ScheduledPost.draft_id)
                    .where(ContentDraft.product_id == uuid.UUID(self.ids["prod_" + key]),
                           ScheduledPost.status == PostStatus.PUBLISHED).limit(1)
                )
            ).scalar_one_or_none()  # fmt: skip
        return src_code(sp) if sp else None

    async def content_week(self) -> None:
        """Lịch tuần: bài đợt 2 đã duyệt nằm rải trong tuần; bài các kênh khác còn chờ chị."""
        await JOBS["content.compose_pending"](job_context())
        studio = await self.call("GET", f"{OWNER}/content/studio/drop/{self.ids['d2']}", ok=(200, 404))
        for d in (studio or {}).get("drafts", [])[:2]:
            if d["status"] == "pending_review":
                await self.call("POST", f"{OWNER}/content/drafts/{d['id']}/approve", json={})
                self.bump("posts_approved")
        await self.call("POST", f"{OWNER}/content/calendar/plan", json={}, ok=(200, 201, 400, 409, 422))

    async def inbox(self) -> None:
        msgs = [
            ("facebook", "direct_message", "demo_psid_ha", "Đào Thu Hà", "Bình giữ nhiệt nắp bật còn hàng không chị?", True),
            ("facebook", "comment", "demo_psid_tuan", "Tuấn Vũ", "Hộp cơm inox 3 ngăn giá bao nhiêu ạ?", True),
            ("zalo_oa", "direct_message", "demo_zalo_khoa", "Đỗ Đức Khoa", f"Đơn {self.orders['d1_khoa']['code']} mình nhận giá phơi bị móp một chân rồi shop ơi", False),
            ("instagram", "direct_message", "demo_ig_quynh", "quynh.nha", "Khăn tắm cho bé giặt máy được không ạ?", False),
            ("zalo_oa", "direct_message", "demo_zalo_lananh", "Lan Anh", "Mình bị dị ứng niken, dùng hộp cơm inox có sao không chị?", False),
            ("facebook", "direct_message", "demo_psid_hien", "Thu Hiền", "Chị ơi lấy cho em 2 hộp cơm inox 3 ngăn nhé, số em 0900000110", False),
            ("facebook", "direct_message", "demo_psid_son", "Minh Sơn", "Phí ship về Đà Nẵng bao nhiêu chị?", True),
        ]  # fmt: skip
        for ch, kind, author, name, text, auto in msgs:
            await self.call("PATCH", f"{OWNER}/control/autonomy/inbox.reply_faq", json={"level": "auto" if auto else "ask"},
                            ok=(200, 400, 403, 404))  # fmt: skip
            await self.call("POST", f"{OWNER}/inbox/dev/simulate", json={
                "text": text, "channel": ch, "kind": kind, "author_name": name, "author_external_id": author,
                **({"post_external_id": "demo_post_1"} if kind == "comment" else {}),
            })  # fmt: skip
            self.bump("messages")
        await self.call(
            "PATCH", f"{OWNER}/control/autonomy/inbox.reply_faq", json={"level": "ask"}, ok=(200, 400, 403, 404)
        )

    async def crm(self) -> None:
        from app.modules.orders.models import Customer

        async with SessionLocal() as s:
            cust = {c.phone: c.id for c in (await s.execute(select(Customer))).scalars()}
        ha = cust.get(CUSTOMERS["ha"][1])
        if ha:
            await self.call("POST", f"{OWNER}/crm/customers/{ha}/notes",
                            json={"body": "Hay mua đồ cho bé, thích hàng Nhật, nhận hàng giờ hành chính.", "pinned": True})  # fmt: skip
            await self.call("POST", f"{OWNER}/crm/customers/{ha}/referral", ok=(200, 201))
        # khách quen thử hàng cùng chị (h8): mời thử áo choàng tắm, một khách đã gửi cảm nhận
        ids = [cust[CUSTOMERS[k][1]] for k in ("ha", "minh") if CUSTOMERS[k][1] in cust]
        if ids:
            res = await self.call("POST", f"{OWNER}/crm/tester-invites",
                                  json={"candidate_id": self.ids["c_aochoang"], "customer_ids": [str(i) for i in ids]})  # fmt: skip
            invites = res if isinstance(res, list) else res.get("items", [])
            first = next((i for i in invites if i.get("link")), None)
            if first:
                token = first["link"].rsplit("/", 1)[1]
                await self.call("POST", f"/api/store/crm/thu-hang/{token}", public=True, json={"action": "accept"})
                await self.call("POST", f"/api/store/crm/thu-hang/{token}", public=True,
                                json={"action": "feedback", "feedback": "Vải dày, bé mặc ấm; mũ hơi rộng với bé 2 tuổi.", "rating": 4})  # fmt: skip

    async def books(self) -> None:
        await self.call("POST", f"{OWNER}/finance/expenses", json={
            "incurred_on": (local_today() - timedelta(days=4)).isoformat(), "category": "packaging",
            "amount_vnd": 350000, "description": "Hộp carton và băng keo (ví dụ)", "vendor": "Cửa hàng bao bì (ví dụ)",
        }, ok=(200, 201, 422))  # fmt: skip
        from app.core.timeutil import week_start

        for weeks in (4, 3, 2, 1, 0):
            ws = week_start() - timedelta(days=7 * weeks)
            await self.call("POST", f"{OWNER}/finance/reports/generate", json={"week_start": ws.isoformat()})
            self.bump("weekly_reports")


async def seed_demo() -> dict[str, int]:
    """Dựng câu chuyện mẫu (một lần). Trả số đối tượng đã tạo; đã dựng rồi thì trả {}."""
    from app.main import app
    from app.modules.control.models import AppSetting

    async with SessionLocal() as s:
        if await s.get(AppSetting, MARK):
            return {}
    # dữ liệu mẫu luôn dùng AI giả + driver giả, chạy việc nền ngay trong tiến trình
    saved = {k: getattr(settings, k) for k in ("ai_provider", "jobs_eager", "sources_driver", "social_driver",
                                                "payments_driver", "shipping_driver", "notify_driver", "app_env")}  # fmt: skip
    settings.ai_provider, settings.jobs_eager = "fake", True
    for k in ("sources_driver", "social_driver", "payments_driver", "shipping_driver", "notify_driver"):
        setattr(settings, k, "mock")
    if settings.app_env == "prod":
        settings.app_env = "dev"  # giả lập tiền về / tin đến chỉ mở ở dev
    from app.core import ratelimit

    ratelimit.force_local(True)
    try:
        transport = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://demo") as c,
            httpx.AsyncClient(transport=transport, base_url="http://demo") as pub,
        ):
            story = Story(c, pub)
            await story.login()
            await story.run()
        async with SessionLocal() as s:
            s.add(AppSetting(key=MARK, value={"at": now_utc().isoformat(), "counts": story.counts}))
            await s.commit()
        return story.counts
    finally:
        ratelimit.force_local(False)
        for k, v in saved.items():
            setattr(settings, k, v)
