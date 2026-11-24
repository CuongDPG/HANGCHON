"""Lỗi của lớp AI. Đều là AppError nên route tự trả câu tiếng Việt."""

from __future__ import annotations

from app.core.errors import AppError


class AIError(AppError):
    status_code = 502
    code = "ai_error"
    message = "AI gặp lỗi khi xử lý, chị thử lại sau."


class AIUnavailable(AIError):
    status_code = 503
    code = "ai_unavailable"
    message = "Dịch vụ AI tạm thời không phản hồi, chị thử lại sau ít phút."


class AIRefused(AIError):
    status_code = 422
    code = "ai_refused"
    message = "AI từ chối xử lý yêu cầu này. Chị xem lại nội dung hoặc tự làm phần này."

    def __init__(self, message: str | None = None, *, category: str | None = None) -> None:
        super().__init__(message, data={"category": category} if category else None)
        self.category = category


class AIOutputInvalid(AIError):
    status_code = 502
    code = "ai_output_invalid"
    message = "AI trả kết quả không đúng khuôn, chị thử lại."


class AIBudgetExceeded(AIError):
    status_code = 409
    code = "ai_budget_exceeded"
    message = "Đã chạm trần chi phí AI của tháng này. AI tạm dừng và chờ chị quyết định ở Hàng chờ duyệt."
