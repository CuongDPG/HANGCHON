"""Hành động mẫu `demo.*` — chỉ nạp khi đặt `HC_DEMO_ACTIONS=1` (máy dev, ảnh chụp, Playwright).

Giúp xem trọn luồng «Hôm nay» → duyệt / sửa rồi duyệt / trả lại → nhật ký → hoàn tác khi các module nghiệp vụ
chưa gộp về. Không dùng ở bản chạy thật: module nghiệp vụ tự đăng ký hành động của mình.
"""

from __future__ import annotations

from app.modules.control.registry import (
    ActionContext,
    HandlerResult,
    ReturnContext,
    UndoContext,
    handler,
    on_returned,
    register_action,
    undoer,
)

DEMO_ACTIONS = [
    # (khoá, nhãn, nhóm, mặc định, khách thấy, khoá cứng)
    ("demo.reply_faq", "Trả lời giá, còn hàng, phí giao", "Khách", "auto", True, False),
    ("demo.reply_draft", "Soạn câu trả lời tin nhắn khác", "Khách", "ask", True, False),
    ("demo.reorder_reminder", "Nhắn nhắc khách mua lại", "Khách", "ask", True, False),
    ("demo.publish_scheduled", "Đăng bài chị đã duyệt theo lịch", "Nội dung", "auto", True, False),
    ("demo.publish_post", "Soạn và đăng bài mới", "Nội dung", "ask", True, False),
    ("demo.price_proposal", "Đề xuất giá bán", "Nguồn cung", "ask", True, False),
    ("demo.match_payment", "Khớp khoản chuyển tới với đơn", "Đơn hàng", "auto", False, False),
    ("demo.create_shipment", "Tạo vận đơn", "Đơn hàng", "auto", False, False),
    ("demo.refund", "Khiếu nại, đổi trả, hoàn tiền", "Đơn hàng", "ask", True, True),
    ("demo.supplier_order", "Đặt hàng và trả tiền nhà cung cấp", "Nguồn cung", "ask", False, True),
]

RETURNED: list[str] = []

for key, label, group, default, facing, locked in DEMO_ACTIONS:
    register_action(key, label, group, default=default, customer_facing=facing, locked=locked,
                    description="Hành động mẫu để xem thử giao diện.")  # fmt: skip

    @handler(key)
    async def _run(ctx: ActionContext, key: str = key) -> HandlerResult:
        return HandlerResult(
            result={"ok": True, "demo": True},
            undo={"key": key},
            summary=f"Đã làm (mẫu): {ctx.payload.get('title', key)}",
        )

    @undoer(key)
    async def _undo(ctx: UndoContext) -> None:
        return None

    @on_returned(key)
    async def _ret(ctx: ReturnContext) -> None:
        RETURNED.append(ctx.note)
