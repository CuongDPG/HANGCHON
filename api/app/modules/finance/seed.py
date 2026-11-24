"""Dữ liệu mẫu cho sổ sách (k1): vài khoản chi tháng này và tháng trước, đã ghi sổ. Chạy lại không sinh trùng.

Doanh thu không tạo ở đây: sổ chỉ ghi doanh thu từ đơn thật (sự kiện `order.paid` của orders)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import local_today
from app.modules.finance import service
from app.modules.finance.models import Expense, ExpenseCategory

EXPENSES = [
    # (cách hôm nay mấy ngày, nhóm, số tiền, diễn giải, nơi bán)
    (1, ExpenseCategory.PACKAGING, 360_000, "Hộp giấy carton 200 cái", "Bao bì Minh An (ví dụ)"),
    (3, ExpenseCategory.SAMPLES, 485_000, "Mua mẫu 3 bình giữ nhiệt", "Shop mẫu (ví dụ)"),
    (6, ExpenseCategory.SHIPPING, 64_000, "Cước gửi mẫu cho khách thử", "GHN"),
    (9, ExpenseCategory.ADS, 300_000, "Tăng tương tác bài Đợt 11", "Meta"),
    (12, ExpenseCategory.SOFTWARE, 250_000, "Tên miền và máy chủ", "Nhà cung cấp máy chủ (ví dụ)"),
    (35, ExpenseCategory.GOODS, 9_800_000, "Đặt lô Đợt 10: 120 món", "Xưởng Phật Sơn (ví dụ)"),
    (40, ExpenseCategory.PACKAGING, 180_000, "Băng keo, giấy chống sốc", "Bao bì Minh An (ví dụ)"),
]


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    if await db.scalar(select(Expense.id).where(Expense.description == EXPENSES[0][3]).limit(1)):
        return {"expenses": 0}
    today = local_today()
    n = 0
    for days, cat, amount, desc, vendor in EXPENSES:
        exp = Expense(incurred_on=today - timedelta(days=days), category=cat, amount_vnd=amount, description=desc,
                      vendor=vendor, payment_method="bank_transfer")  # fmt: skip
        db.add(exp)
        await db.flush()
        await service.record_expense(db, exp.id, manual=True)
        n += 1
    return {"expenses": n}
