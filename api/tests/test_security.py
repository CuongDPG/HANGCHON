"""Rà soát bảo mật (25/11/2026): mỗi test giữ một lỗ đã vá — vượt quyền helper, tệp tải lên chạy script, giới hạn
tần suất bị vượt bằng X-Forwarded-For, dò mật khẩu, phiên cũ sống sau khi đổi mật khẩu."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.main import app as fastapi_app
from app.modules.control.models import User
from tests.conftest import HELPER_EMAIL, HELPER_PASSWORD, OWNER_EMAIL, OWNER_PASSWORD


def _anon() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test")


# ---- phân quyền ----------------------------------------------------------------------------------------------------


async def test_helper_cannot_change_autonomy_by_voice_command(helper_client, owner_client, fake_ai) -> None:
    """PATCH /control/autonomy là của owner; lệnh bằng lời (helper gọi được) không được là cửa sau."""
    fake_ai["control.classify_command"] = lambda _inp: {
        "intent": "control.set_autonomy",
        "params_json": '{"action": "content.publish_post", "level": "auto"}',
        "confidence": 0.95,
        "clarification": None,
    }
    r = await helper_client.post("/api/desk/control/command", json={"text": "cho AI tự đăng bài"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] != "done"
    rows = (await owner_client.get("/api/desk/control/autonomy")).json()
    level = next(a["level"] for a in _flatten(rows) if a["action"] == "content.publish_post")
    assert level == "ask"
    # chị vẫn ra lệnh được
    r = await owner_client.post("/api/desk/control/command", json={"text": "cho AI tự đăng bài"})
    assert r.json()["status"] == "done"


def _flatten(rows):
    out = []
    for x in rows if isinstance(rows, list) else rows.get("items", rows.get("groups", [])):
        out.extend(_flatten(x["actions"]) if "actions" in x else [x])
    return out


# ---- tệp tải lên -----------------------------------------------------------------------------------------------------


async def test_uploaded_html_is_not_served_as_html(helper_client, owner_client) -> None:
    """Helper tải «clip» mang kiểu text/html (tên .mp4) → khi chị mở, trình duyệt không được chạy nó như trang web."""
    files = {"file": ("clip.mp4", b"<html><script>fetch('/api/desk/users')</script></html>", "text/html")}
    r = await helper_client.post("/api/desk/content/media", files=files)
    assert r.status_code == 201, r.text
    key = r.json()["storage_key"]
    f = await owner_client.get(f"/api/files/{key}")
    assert f.status_code == 200
    assert "html" not in f.headers["content-type"]
    assert f.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in f.headers["content-security-policy"]
    assert f.headers["content-disposition"].startswith("attachment")


async def test_svg_never_inline_but_photos_are(owner_client) -> None:
    st = get_storage()
    await st.put("public/x/a.svg", b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "image/svg+xml")
    await st.put("public/x/b.webp", b"RIFF....WEBP", "image/webp")
    async with _anon() as c:
        svg = await c.get("/api/files/public/x/a.svg")
        assert svg.headers["content-type"] == "application/octet-stream"
        assert svg.headers["content-disposition"].startswith("attachment")
        img = await c.get("/api/files/public/x/b.webp")
        assert img.headers["content-type"] == "image/webp" and "content-disposition" not in img.headers
        assert img.headers["x-content-type-options"] == "nosniff"


async def test_private_files_need_live_account_and_backups_are_owner_only(owner, helper_client, owner_client) -> None:
    st = get_storage()
    await st.put("private/receipts/r.pdf", b"%PDF-1.4", "application/pdf")
    await st.put("private/backups/2026/11/hangchon-x.sql.gz", b"dump", "application/gzip")
    assert (await helper_client.get("/api/files/private/receipts/r.pdf")).status_code == 200
    assert (await helper_client.get("/api/files/private/backups/2026/11/hangchon-x.sql.gz")).status_code == 403
    assert (await owner_client.get("/api/files/private/backups/2026/11/hangchon-x.sql.gz")).status_code == 200
    async with SessionLocal() as s:
        from sqlalchemy import update

        await s.execute(update(User).where(User.email == HELPER_EMAIL).values(is_active=False))
        await s.commit()
    assert (await helper_client.get("/api/files/private/receipts/r.pdf")).status_code == 401


# ---- xác thực ------------------------------------------------------------------------------------------------------


async def test_login_is_rate_limited_and_xff_does_not_reset_it(owner) -> None:
    async with _anon() as c:
        codes = []
        for i in range(12):
            r = await c.post(
                "/api/desk/auth/login",
                json={"email": OWNER_EMAIL, "password": f"doan-{i}"},
                headers={"X-Forwarded-For": f"198.51.100.{i}"},
            )
            codes.append(r.status_code)
        assert codes[0] == 401 and codes[-1] == 429, codes
        # đúng mật khẩu cũng phải đợi: không cho dò tiếp rồi đăng nhập ngay
        r = await c.post("/api/desk/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 429


async def test_password_change_signs_out_other_sessions(helper) -> None:
    other = _anon()
    r = await other.post("/api/desk/auth/login", json={"email": HELPER_EMAIL, "password": HELPER_PASSWORD})
    assert r.status_code == 200
    async with _anon() as me:
        await me.post("/api/desk/auth/login", json={"email": HELPER_EMAIL, "password": HELPER_PASSWORD})
        r = await me.post(
            "/api/desk/auth/password", json={"current_password": HELPER_PASSWORD, "new_password": "mat-khau-moi-789"}
        )
        assert r.status_code == 204
        assert (await me.get("/api/desk/auth/me")).status_code == 200  # phiên đang đổi vẫn giữ
    assert (await other.get("/api/desk/auth/me")).status_code == 401  # phiên khác (máy bị lấy cookie) bị đăng xuất
    await other.aclose()


async def test_owner_reset_of_helper_password_signs_helper_out(helper_client, owner_client, helper) -> None:
    r = await owner_client.patch(f"/api/desk/users/{helper.id}", json={"password": "mat-khau-cap-lai-1"})
    assert r.status_code == 200
    assert (await helper_client.get("/api/desk/auth/me")).status_code == 401


# ---- giới hạn tần suất ở route công khai ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [8])
async def test_assistant_limit_not_bypassed_by_spoofed_xff(n: int) -> None:
    """Mỗi câu hỏi tốn tiền AI; bỏ cookie + đổi X-Forwarded-For không được thoát giới hạn theo IP."""
    codes = []
    for i in range(n):
        async with _anon() as c:  # client mới = không cookie = phiên mới
            r = await c.post(
                "/api/store/assistant/ask",
                json={"question": f"Món này dùng được bao lâu {i}?"},
                headers={"X-Forwarded-For": f"203.0.113.{i}"},
            )
            codes.append(r.status_code)
    assert 429 in codes, codes


async def test_order_lookup_is_rate_limited() -> None:
    """Biết số điện thoại của ai đó thì chỉ có 90.000 mã đơn để dò → phải chặn dò hàng loạt."""
    async with _anon() as c:
        codes = [
            (
                await c.post("/api/store/orders/lookup", json={"phone": "0900000101", "code": f"HC-{10000 + i}"})
            ).status_code
            for i in range(25)
        ]
    assert codes[0] == 404 and codes[-1] == 429, codes


async def test_checkout_is_rate_limited() -> None:
    """Đặt đơn giữ suất ngay; không giới hạn thì một máy giữ hết suất của đợt bằng đơn rác."""
    body = {"items": [{"product_id": str(uuid.uuid4()), "quantity": 1}], "name": "Khách", "phone": "0900000101"}
    async with _anon() as c:
        codes = [(await c.post("/api/store/orders", json=body)).status_code for _ in range(25)]
    assert codes[0] != 429 and codes[-1] == 429, codes
