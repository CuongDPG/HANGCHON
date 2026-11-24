"""Lỗi thống nhất. Mọi lỗi trả về dạng `{"detail": "<câu tiếng Việt>", "code": "<mã>", "errors": [...]}`.

`detail` là chuỗi tiếng Việt hiển thị thẳng cho người dùng; `code` để web rẽ nhánh; `errors` chỉ có khi dữ liệu
gửi lên sai (từng trường)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Yêu cầu không hợp lệ."

    def __init__(self, message: str | None = None, *, code: str | None = None, data: Any = None) -> None:
        self.message = message or self.message
        if code:
            self.code = code
        self.data = data
        super().__init__(self.message)


class BadRequest(AppError):
    pass


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Chị cần đăng nhập để tiếp tục."


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    message = "Tài khoản này không có quyền làm việc này."


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Không tìm thấy dữ liệu."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "Dữ liệu đã thay đổi hoặc bị trùng, chị tải lại rồi thử lại."


class Unprocessable(AppError):
    status_code = 422
    code = "unprocessable"
    message = "Không xử lý được yêu cầu này."


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "Dịch vụ tạm thời không phản hồi, chị thử lại sau ít phút."


_HTTP_MESSAGES = {
    400: "Yêu cầu không hợp lệ.",
    401: Unauthorized.message,
    403: Forbidden.message,
    404: "Không tìm thấy trang hoặc dữ liệu.",
    405: "Thao tác này không được hỗ trợ.",
    409: Conflict.message,
    413: "Tệp quá lớn.",
    415: "Định dạng tệp không được hỗ trợ.",
    429: "Thao tác quá nhanh, chị đợi một chút rồi thử lại.",
}

_FIELD_MESSAGES = {
    "missing": "Thiếu thông tin bắt buộc.",
    "string_too_short": "Nội dung quá ngắn.",
    "string_too_long": "Nội dung quá dài.",
    "value_error": "Giá trị không hợp lệ.",
    "int_parsing": "Cần nhập số nguyên.",
    "float_parsing": "Cần nhập số.",
    "uuid_parsing": "Mã không hợp lệ.",
    "enum": "Giá trị không nằm trong danh sách cho phép.",
    "literal_error": "Giá trị không nằm trong danh sách cho phép.",
    "greater_than_equal": "Giá trị quá nhỏ.",
    "less_than_equal": "Giá trị quá lớn.",
    "greater_than": "Giá trị quá nhỏ.",
    "less_than": "Giá trị quá lớn.",
    "json_invalid": "Dữ liệu gửi lên không đúng định dạng JSON.",
    "bool_parsing": "Cần chọn đúng hoặc sai.",
    "datetime_parsing": "Thời gian không hợp lệ.",
    "date_parsing": "Ngày không hợp lệ.",
}


def _body(detail: str, code: str, errors: list[dict[str, Any]] | None = None, data: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"detail": detail, "code": code}
    if errors:
        body["errors"] = errors
    if data is not None:
        body["data"] = data
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.message, exc.code, data=exc.data), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            msg = _FIELD_MESSAGES.get(str(err.get("type")))
            if msg is None:
                msg = str(err.get("msg") or "Giá trị không hợp lệ.")
                if msg.startswith("Value error, "):
                    msg = msg.removeprefix("Value error, ")
            errors.append({"field": ".".join(loc), "message": msg, "type": err.get("type")})
        return JSONResponse(
            _body("Dữ liệu chưa hợp lệ, chị kiểm tra lại các ô được đánh dấu.", "validation_error", errors),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) and not exc.detail.isascii() else None
        message = detail or _HTTP_MESSAGES.get(exc.status_code, "Có lỗi xảy ra.")
        return JSONResponse(
            _body(message, f"http_{exc.status_code}"),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Lỗi không xử lý được ở %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(_body("Hệ thống gặp lỗi, chị thử lại sau ít phút.", "internal_error"), status_code=500)
