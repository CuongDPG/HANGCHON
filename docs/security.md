# Bảo mật Hàng Chọn

Rà soát ngày 25/11/2026 (nhánh `feat/security-hardening`). Test giữ từng lỗ đã vá: `api/tests/test_security.py`,
`api/tests/test_prod_guards.py`, `web/src/lib/security-headers.test.ts`.

## 1. Mô hình đe doạ

| Ai | Muốn gì | Cửa vào |
|---|---|---|
| Người ngoài, không tài khoản | Đọc thông tin khách (tên, SĐT, địa chỉ), đơn giả «đã trả tiền», đốt trần chi phí AI, giữ hết suất của đợt, chiếm tài khoản chị | `/api/store/**`, `/api/hooks/**`, trang đăng nhập, tệp `/api/files/public/**` |
| Tài khoản phụ (helper) | Làm việc chỉ chị được làm: đổi mức tự chủ, duyệt, tải bản sao lưu; chạy script trong phiên của chị | `/api/desk/**` (helper gọi được phần lớn), tệp tải lên |
| Nội dung từ ngoài (khách nhắn, trang web, nhà cung cấp) | Khiến AI tự làm việc nguy hiểm (prompt injection) | dữ liệu vào `ai.run(...)` |
| Người đọc repo công khai | Bí mật, mật khẩu mặc định, dữ liệu thật | mã nguồn + lịch sử git |

## 2. Lớp bảo vệ hiện có

| Lớp | Ở đâu |
|---|---|
| Mật khẩu argon2; phiên JWT trong cookie `hc_session` (httpOnly, SameSite=Lax, Secure ở prod qua `COOKIE_SECURE`) | `app/core/security.py`, `app/modules/control/router.py` |
| Phiên gắn **dấu mật khẩu** (`pws`): đổi mật khẩu / chị cấp lại mật khẩu → mọi phiên cũ hết hiệu lực; tài khoản bị khoá → 401 | `app/core/security.py` `password_stamp`, `app/core/deps.py` |
| Khoá dò mật khẩu: 10 lần sai / 15 phút theo email, 30 theo IP (chỉ đếm lần sai); email không tồn tại vẫn băm để không lộ thời gian | `control/router.py` `login` |
| `DeskAuthGuard` chặn mọi `/api/desk/**` thiếu phiên; route khai `CurrentUser` / `OwnerUser` | `app/main.py`, `app/core/deps.py` |
| Việc của chị: duyệt, trả lại, hoàn tác, mức tự chủ (kể cả qua lệnh bằng lời), cài đặt, tài khoản, sao lưu | `OwnerUser` ở router; `control/actions.py` `_set_autonomy` |
| Tệp: khoá kiểm `..`/`\`; `private/**` cần tài khoản còn hoạt động, `private/backups/**` chỉ owner; chỉ ảnh/âm thanh/video/PDF/text được mở trong trình duyệt, kiểu khác trả `attachment`; luôn `nosniff` + CSP `sandbox` | `integrations/storage/__init__.py`, `app/main.py` `serve_file`, `file_headers` |
| Ảnh khách gửi (đánh giá) và ảnh sản phẩm được Pillow mã hoá lại, bỏ EXIF, chặn ảnh bom; số ảnh và cỡ kiểm trước khi đọc | `catalog/images.py`, `catalog/router.py` `submit_review` |
| Route công khai: theo dõi đơn cần mã HMAC (`?t=`) — 80 bit, không lưu; mã đánh giá / thử hàng 144 bit ngẫu nhiên; mã đơn ngẫu nhiên (không lộ số đơn) | `orders/util.py`, `core/security.py` `random_token` |
| Giới hạn tần suất (Redis, cửa sổ trượt): trợ lý AI (6/phút + 120/ngày mỗi IP, 40/ngày mỗi phiên), tra đơn (30/10 phút mỗi IP, 10/giờ mỗi SĐT), đặt hàng (20/10 phút), báo giá, hỏi về đơn, nhờ tìm, bình chọn, đánh giá, nhắc đợt | `app/core/ratelimit.py` + từng router |
| IP khách lấy từ `request.client` — uvicorn chỉ tin `X-Forwarded-For` khi yêu cầu tới từ mạng nội bộ (`FORWARDED_ALLOW_IPS`); không đọc thẳng header | `api/Dockerfile`, `ratelimit.client_ip` |
| Webhook: SePay so khoá hằng-thời-gian; Meta HMAC `X-Hub-Signature-256`; Zalo SHA-256 `X-ZEvent-Signature`; GHN/GHTK không ký → hỏi lại hãng; chống phát lại bằng mã giao dịch / mã tin duy nhất; webhook `mock` 404 ở prod | `integrations/payments/sepay.py`, `integrations/social/_meta_messaging.py`, `_zalo_oa_messaging.py`, `orders/payments.py`, `orders/router.py` `_allowed` |
| Production không khởi động với `JWT_SECRET` hoặc `OWNER_PASSWORD` mẫu / ngắn, hay thiếu `SECRETS_ENCRYPTION_KEY`; trang `/docs` tắt | `app/core/config.py`, `app/main.py` |
| Khoá API nhà cung cấp AI chị nhập ở *Cài đặt → AI và khoá API*: mã hoá Fernet (AES-128-CBC + HMAC-SHA256) bằng `SECRETS_ENCRYPTION_KEY` riêng (không suy ra từ `JWT_SECRET`; xoay khoá bằng danh sách `moi,cu`); API chỉ trả dạng che `sk-ant-…8AAA` + thời điểm/người đổi; chỉ owner đọc/sửa (helper 403); lưu vết `ai.key_changed` / `ai.key_cleared` / `ai.config_changed` không chứa giá trị khoá; khoá không vào log, `ai_runs`, lời báo lỗi (lời lỗi của nhà cung cấp được lọc khoá) | `app/core/secrets.py`, `app/ai/config.py`, `control/ai_settings.py`, `tests/control/test_ai_config.py` |
| Khoá tài khoản kênh (Meta, Threads, TikTok, Zalo OA, Shopee, TikTok Shop) chị nhập ở *Cài đặt → Mạng xã hội*: cùng mã hoá Fernet; API chỉ trả 4 ký tự cuối; chỉ owner; lưu vết `control.channel_account_*` chỉ ghi tên ô; lời lỗi của nền tảng được lọc khoá; `httpx` không ghi log URL (Graph/Shopee để `access_token` trong query); OAuth dùng `state` ngẫu nhiên một lần, 15 phút | `app/integrations/channel_config.py`, `channel_oauth.py`, `control/channels.py`, `tests/control/test_channel_accounts.py` |
| AI: dữ liệu ngoài bọc `<du_lieu>`; mọi hành động khách nhìn thấy mặc định `ask`, đổi trả/hoàn tiền/đặt hàng NCC `locked_ask`; việc `auto` mặc định đều là việc nội bộ | `app/ai`, `modules/*/actions.py` |
| Web: React chặn URL `javascript:`; JSON-LD thoát `<`; `next` sau đăng nhập chỉ nhận `/desk...`; header `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS | `web/src/components/store/json-ld.tsx`, `desk/dang-nhap/login-form.tsx`, `web/src/lib/security-headers.ts` |
| Container chạy bằng user thường (`app`, `node`); Postgres/Redis không mở cổng ra máy chủ | `api/Dockerfile`, `web/Dockerfile`, `docker-compose.prod.yml` |

## 3. Phải làm trước khi mở bán thật

- [ ] `JWT_SECRET`, `POSTGRES_PASSWORD`, `HOOKS_MOCK_SECRET`, `OWNER_PASSWORD` là chuỗi ngẫu nhiên riêng; đổi mật khẩu owner ngay sau lần đăng nhập đầu.
- [ ] `SECRETS_ENCRYPTION_KEY` là khoá Fernet riêng, cất một bản ngoài máy chủ (mất khoá = phải nhập lại khoá API). Khoá API AI nhập ở Cài đặt rồi xoá khỏi env của Dokploy.
- [ ] `PAYMENTS_DRIVER=sepay` + `SEPAY_WEBHOOK_SECRET`; `META_APP_SECRET`, `ZALO_OA_SECRET` trước khi khai webhook.
- [ ] Kiểm sau deploy: gửi `X-Forwarded-For` giả tới `/api/store/assistant/ask` vẫn bị 429 sau 6 câu/phút (xác nhận Traefik nằm trong `FORWARDED_ALLOW_IPS`; mạng Dokploy khác dải mặc định thì đặt biến này).
- [ ] Đặt trần chi phí AI; mức tự chủ giữ «thận trọng»; không chuyển `inbox.reply_faq` / `content.publish_post` sang `auto` khi chưa theo dõi một thời gian.
- [ ] Không chạy dữ liệu mẫu trên prod; tài khoản helper dùng mật khẩu riêng, khoá ngay khi thôi việc.
- [ ] Bản sao lưu (toàn bộ dữ liệu khách) chép ra ngoài máy chủ ở nơi chỉ chị đọc được.

## 4. Rủi ro còn lại

- **Đăng xuất không thu hồi phiên ở máy chủ**: cookie bị chép trước khi đăng xuất còn dùng được tới hết hạn (14 ngày). Cách cắt: đổi mật khẩu (mọi phiên hết hiệu lực). Muốn thu hồi từng phiên cần danh sách thu hồi (Redis) hoặc rút `JWT_EXPIRE_MINUTES`.
- **Helper làm được nhiều việc khách nhìn thấy mà không qua duyệt**: sửa trang sản phẩm đang bán, mở đợt, trả lời tin khách, tạo vận đơn, tạo đơn tay có giá/giảm giá tuỳ ý. Đây là phân quyền nghiệp vụ, chị cần quyết.
- Giới hạn theo IP chặn được một máy; nhiều máy (botnet) vẫn đốt được trần AI — trần tháng là chốt cuối.
- Không có CSP cho script trên web (Next cần nonce); XSS hiện dựa vào React tự thoát chuỗi.
- Webhook GHN/GHTK không ký: ai cũng gọi được, mỗi lần làm API hỏi lại hãng một lần (tốn hạn mức gọi hãng).
- `ai_runs.output` và hàng chờ duyệt có thể chứa SĐT/địa chỉ khách; helper xem được. Chưa có thời hạn xoá dữ liệu cá nhân.
- Khoá mã hoá `SECRETS_ENCRYPTION_KEY` nằm trong env của máy chủ: ai đọc được env (quyền vào Dokploy / `docker inspect`) cùng
  bản sao CSDL thì giải mã được khoá API. Mã hoá bảo vệ trước việc lộ riêng CSDL hay bản sao lưu, không bảo vệ trước người
  chiếm máy chủ. Khoá đã giải mã nằm trong bộ nhớ tiến trình API/worker (cache ≤ 5 giây cấu hình, client SDK theo khoá).
- «Kiểm tra kết nối» là chỗ duy nhất gọi AI theo yêu cầu của người dùng với khoá chưa lưu; chỉ owner bấm được, mỗi lần gọi
  hai lượt rất ngắn và tính vào trần tháng.
- Lịch sử git có email công việc thật của người commit (metadata commit) — không xoá được nếu không viết lại lịch sử.
