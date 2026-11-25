"""Báo tin qua email (SMTP, thư viện chuẩn `smtplib` chạy trong luồng phụ để không chặn vòng sự kiện).

Thư gồm bản văn bản + bản HTML đơn giản (không nhúng ảnh ngoài), tiếng Việt, ghi tên cửa hàng. Cấu hình: `SMTP_HOST`,
`SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` = `starttls` (mặc định, cổng 587) | `ssl`
(cổng 465) | `none` (chỉ máy chủ nội bộ/thử). Phân loại lỗi theo mã SMTP: 4xx / mất kết nối → tạm thời (gửi lại sau);
5xx (địa chỉ không tồn tại, bị từ chối) → vĩnh viễn; sai mật khẩu (535) → thiếu cấu hình.
"""

from __future__ import annotations

import asyncio
import html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from app.core.config import settings
from app.core.enums import Channel
from app.core.timeutil import now_utc
from app.integrations.notify import NotifyDriver, NotifyResult, OutboundNotification, failed


def build_message(msg: OutboundNotification) -> EmailMessage:
    shop = settings.app_name
    site = settings.web_base_url.rstrip("/")
    name, addr = parseaddr(settings.smtp_from)
    em = EmailMessage()
    em["Subject"] = msg.subject or f"{shop}: thông báo cho bạn"
    em["From"] = formataddr((name or shop, addr))
    em["To"] = msg.to
    em["Message-ID"] = make_msgid(domain=(addr.split("@", 1)[1] if "@" in addr else None))
    lines = [msg.text]
    if msg.link_url and msg.link_url not in msg.text:
        lines += ["", msg.link_url]
    lines += ["", f"— {shop} · {site}"]
    # quoted-printable: an toàn cả với máy chủ không nhận 8BITMIME (tiếng Việt có dấu)
    em.set_content("\n".join(lines), cte="quoted-printable")
    paras = "".join(f"<p>{html.escape(p)}</p>" for p in msg.text.split("\n") if p.strip())
    link = (
        f'<p><a href="{html.escape(msg.link_url, quote=True)}">{html.escape(msg.link_url)}</a></p>'
        if msg.link_url and msg.link_url not in msg.text
        else ""
    )
    em.add_alternative(
        '<!doctype html><html lang="vi"><body style="font-family:sans-serif;color:#1C1D22;line-height:1.5">'
        f"{paras}{link}"
        f'<p style="color:#6b6d75;font-size:13px">— {html.escape(shop)} · '
        f'<a href="{html.escape(site, quote=True)}" style="color:#2E3F8F">{html.escape(site)}</a></p>'
        "</body></html>",
        subtype="html",
        cte="quoted-printable",
    )
    return em


class Driver(NotifyDriver):
    name = "email"
    channels = (Channel.EMAIL,)

    def missing_config(self) -> str | None:
        if not settings.smtp_host:
            return "Chưa cấu hình máy chủ gửi email (SMTP_HOST)."
        if not parseaddr(settings.smtp_from)[1]:
            return "SMTP_FROM chưa có địa chỉ gửi hợp lệ."
        return None

    def _deliver(self, em: EmailMessage) -> None:
        host, port, timeout = settings.smtp_host or "", settings.smtp_port, settings.smtp_timeout_seconds
        if settings.smtp_tls == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout)
        with smtp:
            if settings.smtp_tls == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(em)

    async def send(self, msg: OutboundNotification) -> NotifyResult:
        if "@" not in msg.to:
            return failed(f"«{msg.to}» không phải địa chỉ email.", retryable=False)
        em = build_message(msg)
        try:
            await asyncio.to_thread(self._deliver, em)
        except smtplib.SMTPAuthenticationError:
            return failed("Máy chủ email từ chối đăng nhập: kiểm tra SMTP_USER / SMTP_PASSWORD.", retryable=False)
        except smtplib.SMTPRecipientsRefused as e:
            code = next(iter(e.recipients.values()))[0] if e.recipients else 550
            return failed(f"Máy chủ email từ chối người nhận {msg.to} (mã {code}).", retryable=400 <= code < 500)
        except smtplib.SMTPResponseException as e:
            return failed(f"Máy chủ email báo lỗi {e.smtp_code}.", retryable=400 <= e.smtp_code < 500)
        except (smtplib.SMTPException, OSError) as e:
            return failed(
                f"Không gửi được email (mất kết nối máy chủ: {type(e).__name__}), sẽ thử lại.", retryable=True
            )
        return NotifyResult(external_id=str(em["Message-ID"]).strip("<>"), status="sent", sent_at=now_utc())
