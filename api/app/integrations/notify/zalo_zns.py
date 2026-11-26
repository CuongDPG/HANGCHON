"""Zalo ZNS — từ 01/01/2026 hợp nhất thành «ZBS Template Message»: tin theo mẫu đã được Zalo duyệt.

**CHƯA THỬ THẬT** với OA/ZBS thật. Viết theo tài liệu chính thức đọc ngày 25/11/2026:
- Gửi qua số điện thoại (developers.zalo.me/docs/zbs-template-message/gui-tin-template-qua-sdt/api-gui-tin-qua-sdt/
  api-gui-tin): `POST https://business.openapi.zalo.me/message/template`, header `access_token`, body
  `{"phone": "84987654321", "template_id", "template_data": {...}, "tracking_id"}` (+ `"mode": "development"` khi gửi thử
  tới quản trị viên) → `{"error": 0, "message": "Success", "data": {"msg_id", "sent_time", "quota": {...}}}`.
- Gửi qua user id OA (…/gui-tin-template-qua-uid/api-gui-tin-qua-uid): `POST https://openapi.zalo.me/v3.0/oa/message/template`,
  body `{"user_id", "template_id", "template_data"}` → `data.message_id`. Chỉ mẫu tạo từ 10/12/2025 trở đi mới gửi được
  qua UID (lỗi -249). Mã lỗi của đường UID theo bộ mã OA API — ở đây chỉ phân loại theo bảng mã ZBS (CHƯA CHẮC).
- Bảng mã lỗi (…/zbs-template-message/bang-ma-loi): -124 token sai/hết hạn → làm mới token rồi gửi lại một lần;
  -133 (cấm gửi 22h–7h), -144/-147/-1441/-1471/-1472 (hạn mức), -115/-126/-137 (số dư ZBS), -100 → lỗi tạm thời;
  còn lại (vd -108 số sai, -118 không có tài khoản Zalo, -109/-117/-131 mẫu sai/chưa duyệt, -139/-141 người dùng từ chối,
  -1121/-1122/-1124 tham số) → lỗi vĩnh viễn.
- Mẫu phải đăng ký trước với Zalo (tag 1 giao dịch, 2 chăm sóc, 3 hậu mãi/quảng cáo). Tham số có giới hạn độ dài theo
  từng mẫu — giá trị dài bị Zalo trả -1121 (không tự cắt ở đây).

Cấu hình: `ZALO_ZNS_TEMPLATES` (JSON) ánh xạ loại tin của hệ thống → mẫu, vd
`{"order_received": {"template_id": "123456", "params": {"customer_name": "ten", "order_code": "ma_don"}}}` — khoá của
`params` là tên tham số trong mẫu Zalo, giá trị là tên ô dữ liệu của hệ thống (như trong mẫu tin chị sửa: `ten`, `ma_don`,
`tong_tien`, `link`...). Token: `app/integrations/_zalo_token.py`. `ZALO_ZNS_DEVELOPMENT=true` để gửi thử.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations import channel_config as cc
from app.integrations._mockutil import short_id
from app.integrations._zalo_token import ZaloTokenStore
from app.integrations.notify import NotifyDriver, NotifyResult, OutboundNotification, failed

PHONE_URL = "https://business.openapi.zalo.me/message/template"
UID_URL = "https://openapi.zalo.me/v3.0/oa/message/template"
TOKEN_INVALID = -124
TEMPORARY = {-100, -133, -144, -147, -1441, -1471, -1472, -115, -126, -137}
EXPLAIN = {
    -108: "Số điện thoại không hợp lệ.",
    -118: "Số này chưa có tài khoản Zalo hoặc tài khoản đã bị khoá.",
    -109: "Mã mẫu ZNS không hợp lệ.",
    -117: "OA/ứng dụng chưa được dùng mẫu ZNS này.",
    -131: "Mẫu ZNS chưa được Zalo duyệt.",
    -133: "Zalo không cho gửi loại tin này từ 22h tới 7h, sẽ gửi lại sau.",
    -139: "Khách đã từ chối nhận loại tin này.",
    -141: "Khách đã từ chối nhận tin qua số điện thoại từ OA.",
    -144: "OA đã hết hạn mức gửi trong ngày.",
    -115: "Tài khoản ZBS không đủ số dư.",
    -137: "Tài khoản ZBS thanh toán thất bại (số dư không đủ?).",
}


def normalize_phone(raw: str) -> str | None:
    """0987654321 / +84 987 654 321 → 84987654321; không phải số di động Việt Nam → None."""
    digits = re.sub(r"[^\d]", "", raw or "")
    if digits.startswith("0") and len(digits) == 10:
        digits = "84" + digits[1:]
    return digits if re.fullmatch(r"84\d{9}", digits) else None


class Driver(NotifyDriver):
    name = "zalo_zns"
    channels = (Channel.ZALO_OA, Channel.ZALO, Channel.SMS, Channel.PHONE)

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, tokens: ZaloTokenStore | None = None) -> None:
        self._transport = transport
        self.tokens = tokens or ZaloTokenStore(transport=transport)

    def missing_config(self) -> str | None:
        if not settings.zalo_zns_templates:
            return "Chưa cấu hình mẫu ZNS (ZALO_ZNS_TEMPLATES): chưa biết gửi loại tin nào bằng mẫu nào."
        if not (cc.value("zalo_oa", "access_token") or self.tokens.can_refresh()):
            return "Chưa có access token Zalo OA (ZALO_OA_ACCESS_TOKEN hoặc ZALO_OA_REFRESH_TOKEN + ZALO_APP_ID + ZALO_APP_SECRET)."
        return None

    def _template(self, msg: OutboundNotification) -> tuple[str, dict[str, str]] | str:
        """(template_id, template_data) hoặc câu lỗi."""
        spec = settings.zalo_zns_templates.get(msg.kind or "") if msg.kind else None
        template_id = msg.template or (str(spec.get("template_id") or "") if spec else "")
        if not template_id:
            return f"Chưa có mẫu ZNS cho loại tin «{msg.kind or 'tin tự do'}» (ZALO_ZNS_TEMPLATES)."
        params: dict[str, Any] = (spec or {}).get("params") or {}
        data: dict[str, str] = {}
        for zalo_name, field in params.items():
            value = msg.data.get(str(field))
            if value is None or str(value).strip() == "":
                return f"Thiếu giá trị «{field}» cho tham số «{zalo_name}» của mẫu ZNS «{msg.kind}»."
            data[str(zalo_name)] = str(value)
        return template_id, data

    async def send(self, msg: OutboundNotification) -> NotifyResult:
        tpl = self._template(msg)
        if isinstance(tpl, str):
            return failed(tpl, retryable=False)
        template_id, template_data = tpl
        phone = normalize_phone(msg.to) or normalize_phone(str(msg.data.get("phone") or ""))
        if phone:
            url = PHONE_URL
            body: dict[str, Any] = {
                "phone": phone,
                "template_id": template_id,
                "template_data": template_data,
                # ≤ 48 ký tự, không ký tự đặc biệt (tài liệu khuyến nghị)
                "tracking_id": short_id(msg.kind, phone, msg.text, length=32),
            }
            if settings.zalo_zns_development:
                body["mode"] = "development"
        elif msg.channel == Channel.ZALO_OA and msg.to and msg.to.isdigit():
            url, body = UID_URL, {"user_id": msg.to, "template_id": template_id, "template_data": template_data}
        else:
            return failed("Khách chưa có số điện thoại dùng Zalo để nhận tin ZNS.", retryable=False)

        token = await self.tokens.access_token()
        res = await self._post(url, body, token)
        if res.get("error") == TOKEN_INVALID and self.tokens.can_refresh():
            res = await self._post(url, body, await self.tokens.refresh(stale=token))
        code = res.get("error")
        if code == 0:
            data = res.get("data") or {}
            return NotifyResult(
                external_id=str(data.get("msg_id") or data.get("message_id") or "") or None,
                status="sent",
                sent_at=now_utc(),
            )
        try:
            code_int = int(code)
        except (TypeError, ValueError):
            code_int = -100
        reason = EXPLAIN.get(code_int) or str(res.get("message") or "lỗi không rõ")
        return failed(f"Zalo ZNS từ chối ({code_int}): {reason}", retryable=code_int in TEMPORARY)

    async def _post(self, url: str, body: dict[str, Any], token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            r = await client.post(url, json=body, headers={"access_token": token})
        if r.status_code >= 500:
            return {"error": -100, "message": f"HTTP {r.status_code}"}
        try:
            data = r.json()
        except ValueError:
            return {"error": -100, "message": f"HTTP {r.status_code}, phản hồi không phải JSON"}
        return data if isinstance(data, dict) else {"error": -100, "message": "phản hồi lạ"}
