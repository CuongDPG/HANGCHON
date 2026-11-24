"""Dữ liệu mẫu cho bàn làm việc (i1–i4, k2, k3): việc chờ duyệt, nhật ký AI, chi phí AI, lưu vết.

`await seed_demo(db)` chạy lại nhiều lần không sinh trùng. Việc chờ dùng hành động mẫu `demo.*`: muốn duyệt/hoàn tác
được trên giao diện thì chạy API với `HC_DEMO_ACTIONS=1`. Tên món, tên người đều là ví dụ."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Actor
from app.core.timeutil import now_utc
from app.modules.control.models import (
    ActivityMode,
    AIActivity,
    AIRun,
    AIRunStatus,
    ApprovalItem,
    ApprovalStatus,
    AuditLog,
    User,
    UserRole,
)

POST_TEXT = (
    "Ba tuần mình thử năm chiếc bình giữ nhiệt, giữ lại đúng một chiếc.\n\n"
    "Chiếc 480 ml này giữ nóng tới chiều, nắp vặn kín, rửa được bằng máy. Điều chưa ưng: hơi nặng tay (320 g).\n\n"
    "Đợt 12 mở tới thứ Sáu, còn 34 suất."
)

PENDING: list[dict[str, Any]] = [
    {
        "action": "demo.refund", "priority": 20,
        "title": "Khách báo bình bị móp khi nhận",
        "summary": "Đơn HC2611250007 · khách gửi 2 ảnh, nhận hàng hôm qua.",
        "payload": {"order_code": "HC2611250007", "plan": "Đổi chiếc mới, shop chịu phí gửi lại"},
        "preview": {"text": "Khách: «Bình bị móp ở đáy, hộp vẫn nguyên.» AI đề xuất đổi chiếc mới, shop chịu phí gửi lại "
                            "(khoảng 30.000đ). Còn hạn đổi trả 5 ngày.",
                    "fields": [{"label": "Đơn", "value": "HC2611250007"},
                               {"label": "Phương án", "value": "Đổi chiếc mới"},
                               {"label": "Chi phí shop chịu", "value": 30000, "format": "vnd"}]},
        "rationale": "Ảnh cho thấy vết móp ở đáy; chính sách đổi trả 7 ngày khi hàng lỗi do vận chuyển.",
    },
    {
        "action": "demo.publish_post", "priority": 5,
        "title": "Bài Facebook cho Đợt 12 đã soạn xong",
        "summary": "Giọng của chị, có nêu điều chưa ưng. Đăng 20:00 tối nay.",
        "payload": {"channel": "facebook", "text": POST_TEXT, "scheduled": "20:00 hôm nay"},
        "preview": {"channel": "facebook", "text": POST_TEXT, "fields": [{"label": "Giờ đăng", "value": "20:00 hôm nay"}]},
        "rationale": "Số liệu lấy từ hồ sơ thẩm định (trọng lượng 320 g, giữ nóng 12 giờ). Đã soát lời quảng cáo.",
        "sources": [{"url": "https://example.com/ho-so/binh-480", "title": "Hồ sơ thẩm định: bình 480 ml"}],
    },
    {
        "action": "demo.publish_post", "priority": 5,
        "title": "Bộ ảnh Instagram: hộp cơm inox 3 ngăn",
        "summary": "4 ảnh chị chụp, chú thích ngắn.",
        "payload": {"channel": "instagram", "text": "Hộp cơm 3 ngăn, inox 304. Ngăn giữa vừa một quả trứng luộc."},
        "preview": {"channel": "instagram", "text": "Hộp cơm 3 ngăn, inox 304. Ngăn giữa vừa một quả trứng luộc."},
    },
    {
        "action": "demo.price_proposal", "priority": 3,
        "title": "Giá bán hộp cơm inox: 245.000đ, biên 34%",
        "summary": "Giá vốn về tay 162.000đ. Shopee đang bán 229.000–289.000đ.",
        "payload": {"price_vnd": 245000},
        "preview": {"fields": [{"label": "Giá đề xuất", "value": 245000, "format": "vnd"},
                               {"label": "Giá vốn về tay", "value": 162000, "format": "vnd"},
                               {"label": "Biên lợi nhuận", "value": "34%"},
                               {"label": "Giá trên Shopee", "value": "229.000–289.000đ"}]},
        "rationale": "Biên chị đặt tối thiểu 30%; giá nằm giữa khoảng giá thị trường.",
    },
    {
        "action": "demo.supplier_order", "priority": 10,
        "title": "Chốt Đợt 11: đặt 214 món ở 3 nhà cung cấp",
        "summary": "Tổng 18,6 triệu, đặt cọc 30%.",
        "payload": {"drop": "Đợt 11", "total_vnd": 18600000},
        "preview": {"fields": [{"label": "Xưởng Phật Sơn", "value": "120 món · 9.800.000đ"},
                               {"label": "Shop Osaka", "value": "60 món · 6.200.000đ"},
                               {"label": "Xưởng Nghĩa Ô", "value": "34 món · 2.600.000đ"},
                               {"label": "Tổng", "value": 18600000, "format": "vnd"}]},
    },
    {
        "action": "demo.reply_draft", "priority": 0,
        "title": "Trả lời chị Lan: bình có dùng cho bé được không",
        "summary": "Câu hỏi về sức khoẻ → AI soạn nháp, chờ chị.",
        "payload": {"text": "Dạ bình làm bằng inox 304, nắp nhựa PP không BPA. Bé dùng được, chị nhớ rửa kỹ nắp ạ."},
        "preview": {"channel": "messenger", "text": "Dạ bình làm bằng inox 304, nắp nhựa PP không BPA. Bé dùng được, "
                                                     "chị nhớ rửa kỹ nắp ạ."},
    },
]  # fmt: skip

AUTO_TODAY = [
    ("demo.reply_faq", "Trả lời câu hỏi về phí giao", 14),
    ("demo.match_payment", "Khớp khoản chuyển 245.000đ với đơn", 6),
    ("demo.create_shipment", "Tạo vận đơn GHN", 3),
]

AI_TASKS = [
    ("sourcing.parse_brief", 2_400),
    ("assessment.review_digest", 9_800),
    ("content.draft_post", 6_200),
    ("inbox.reply_draft", 1_100),
    ("control.classify_command", 300),
]


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    counts = {"approvals": 0, "activity": 0, "ai_runs": 0, "audit": 0}
    if await db.scalar(select(ApprovalItem.id).where(ApprovalItem.dedupe_key.like("demo:%")).limit(1)):
        return counts
    owner = await db.scalar(select(User).where(User.role == UserRole.OWNER).order_by(User.created_at).limit(1))
    now = now_utc()

    for i, p in enumerate(PENDING):
        db.add(ApprovalItem(module="demo", dedupe_key=f"demo:pending:{i}", sources=p.pop("sources", []), **p))
        counts["approvals"] += 1

    for action, title, n in AUTO_TODAY:
        for k in range(n):
            db.add(AIActivity(action=action, module="demo", title=f"{title} #{k + 1}", mode=ActivityMode.AUTO,
                              summary=title, rationale="Câu hỏi khớp mẫu đã duyệt; số liệu lấy từ trang sản phẩm.",
                              payload={"n": k}, undo_data={"n": k}, undoable=action != "demo.reply_faq",
                              created_at=now - timedelta(minutes=10 * k + 5)))  # fmt: skip
            counts["activity"] += 1
    for d in range(1, 8):
        db.add(AIActivity(action="demo.publish_scheduled", module="demo", title="Đăng bài đã duyệt theo lịch",
                          mode=ActivityMode.AUTO, summary="Đăng lúc 20:00 lên Facebook", payload={},
                          created_at=now - timedelta(days=d)))  # fmt: skip
        counts["activity"] += 1

    # lịch sử duyệt: nhắc mua lại được duyệt 12 lần liền không sửa → gợi ý nới
    for k in range(12):
        when = now - timedelta(days=20 - k)
        item = ApprovalItem(action="demo.reorder_reminder", module="demo", title=f"Nhắc mua lại túi lọc #{k + 1}",
                            status=ApprovalStatus.APPROVED, decided_at=when, decided_by_id=owner.id if owner else None,
                            dedupe_key=f"demo:history:{k}", payload={}, preview={"text": "Túi lọc của chị sắp hết."})  # fmt: skip
        db.add(item)
        await db.flush()
        db.add(AIActivity(action=item.action, module="demo", title=item.title, mode=ActivityMode.APPROVED,
                          approval_item_id=item.id, payload={}, created_at=when))  # fmt: skip
        db.add(AuditLog(actor_kind=Actor.OWNER, actor_user_id=owner.id if owner else None, action="control.approved",
                        entity_type="approval_item", entity_id=str(item.id), summary=f"Duyệt: {item.title}",
                        data={"action": item.action}, created_at=when))  # fmt: skip
        counts["approvals"] += 1
        counts["audit"] += 1
    returned = ApprovalItem(action="demo.publish_post", module="demo", title="Bài TikTok: khăn tắm cho bé",
                            status=ApprovalStatus.RETURNED, decision_note="Bỏ câu «mềm nhất thị trường», nói quá.",
                            decided_at=now - timedelta(days=2), decided_by_id=owner.id if owner else None,
                            dedupe_key="demo:history:returned", payload={}, preview={})  # fmt: skip
    db.add(returned)
    await db.flush()
    db.add(AuditLog(actor_kind=Actor.OWNER, actor_user_id=owner.id if owner else None, action="control.returned",
                    entity_type="approval_item", entity_id=str(returned.id), summary=f"Trả lại: {returned.title}",
                    data={"note": returned.decision_note}, created_at=now - timedelta(days=2)))  # fmt: skip
    counts["audit"] += 1

    # chi phí AI trong tháng: mỗi ngày vài lần gọi
    day0 = now.replace(day=1)
    days = max(1, (now - day0).days + 1)
    for d in range(days):
        for j, (task, cost) in enumerate(AI_TASKS):
            if (d + j) % 3 == 0 or task == "inbox.reply_draft":
                db.add(AIRun(task=task, provider="fake", model="claude-haiku-5-5", tier="fast", status=AIRunStatus.OK,
                             input_tokens=1200, output_tokens=400, cost_vnd=cost + 137 * d,
                             created_at=day0 + timedelta(days=d, hours=2 + j)))  # fmt: skip
                counts["ai_runs"] += 1
    await db.flush()
    return counts
