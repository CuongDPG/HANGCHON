# Sổ trạng thái chức năng

Cập nhật 25/11/2026, sau đợt tích hợp 7 lát cắt (nhánh `feat/integration`). Danh mục gốc: [features.md](features.md).

**Cách đọc cột «Trạng thái»** (chỉ ghi «chạy thật» cho thứ đã tự thấy chạy — trong bài test tích hợp
`api/tests/integration/test_lifecycle.py`, bài Playwright `web/e2e/lifecycle.spec.ts`, bài rà route `web/e2e/routes.spec.ts`
hoặc mở tay trên máy dev với dữ liệu mẫu `uv run python -m app.seed --demo`):

- **chạy thật** — logic của chính hệ thống, không cần tài khoản ngoài; đã chạy từ giao diện tới CSDL.
- **chạy với AI giả, cần khoá Anthropic** — luồng chạy trọn với provider `fake` (câu trả lời mẫu có nghĩa); chất lượng
  thật của AI chưa đo vì chưa có khoá. Provider `anthropic` mới kiểm bằng client giả.
- **chạy với mock, cần tài khoản X** — luồng chạy trọn với driver `mock`; driver thật đã viết theo tài liệu chính thức
  nhưng **chưa thử với tài khoản thật**.
- **một phần — thiếu gì** — nói rõ phần thiếu.

| Mã | Chức năng | Trạng thái | Màn hình |
|---|---|---|---|
| a1 | Ra đề bằng lời | chạy với AI giả, cần khoá Anthropic (nói bằng giọng dùng Web Speech của trình duyệt) | `/desk/san-hang`, `/desk/san-hang/de/[id]` |
| a2 | Dán link, lấy hồ sơ | chạy với mock, cần khoá Anthropic (driver `web`) hoặc tài khoản Onebound (driver `onebound`) | `/desk/san-hang` |
| a3 | Tìm bằng ảnh | chạy với mock, cần tài khoản Onebound | `/desk/san-hang` |
| a4 | Quét nhiều nguồn | chạy với mock, cần tài khoản Onebound / khoá Anthropic có web search | `/desk/san-hang/de/[id]` |
| a5 | Radar xu hướng | chạy với mock, cần khoá Anthropic (web search) | `/desk/san-hang` |
| a6 | Nghe khách muốn gì | chạy với AI giả (gom từ tin nhắn, «Nhờ chị tìm», trợ lý web) | `/desk/san-hang` (nhu cầu) |
| a7 | Săn theo lịch | chạy thật phần lịch (cron 7 ngày, ngưỡng báo); quét bằng mock | `/desk/san-hang/de/[id]` |
| b1 | Hồ sơ thẩm định | chạy với AI giả + nguồn mock, cần khoá Anthropic | `/desk/san-hang/ung-vien/[id]` |
| b2 | Đọc hộ đánh giá | chạy với AI giả + nguồn mock | `/desk/san-hang/ung-vien/[id]` |
| b3 | Bảng so sánh cạnh nhau | chạy với AI giả | `/desk/san-hang/so-sanh/[id]` |
| b4 | Chấm điểm theo khung của chị | chạy thật phần khung + chị sửa điểm (25/20/15/15/10/10/5); điểm nháp bằng AI giả | `/desk/san-hang/khung-cham`, hồ sơ thẩm định |
| b5 | Giá bán ở Việt Nam | chạy với mock (giá Shopee/TikTok giả lập), cần khoá Anthropic có web search | hồ sơ thẩm định |
| b6 | Kiểm an toàn và giấy tờ | chạy với AI giả; chị xác nhận chạy thật | hồ sơ thẩm định |
| b7 | Cảnh báo hàng nhái, đánh giá ảo | chạy với AI giả + nguồn mock | hồ sơ thẩm định |
| c1 | Bảng chọn | chạy thật (5 cột, kéo thả trên máy tính, tab trên điện thoại) | `/desk/ban-chon` |
| c2 | Nhật ký thử hàng bằng giọng nói | chạy thật phần ghi/ảnh/ghi âm; chép lời bằng Web Speech; AI sắp ý bằng AI giả | `/desk/ban-chon/[id]` |
| c3 | Lý do chọn và điều chưa ưng | chạy với AI giả; chị sửa lời rồi chốt chạy thật | `/desk/ban-chon/[id]` |
| c4 | Lý do loại | chạy thật | `/desk/ban-chon/[id]`, `/san-pham/[slug]/ho-so-chon` |
| c5 | Bộ nguyên tắc của chị | chạy thật | `/desk/ban-chon/nguyen-tac` |
| c6 | AI học gu chị | chạy với AI giả | `/desk/ban-chon/gu` |
| d1 | Sổ nhà cung cấp | chạy thật | `/desk/nguon-cung`, `/desk/nguon-cung/ncc/[id]` |
| d2 | Tính giá vốn về tay | chạy thật (tỷ giá, cước, phí, thuế, hao hụt; tính lại hằng ngày) | `/desk/nguon-cung/gia-von/[id]` |
| d3 | Đề xuất giá bán | chạy thật (theo giá vốn + giá thị trường + biên chị đặt), duyệt qua hàng chờ | hàng chờ duyệt, giá vốn |
| d4 | Chứng từ nguồn gốc | chạy thật phần lưu/nhắc thiếu; AI đọc chứng từ bằng AI giả | `/desk/nguon-cung/don/[id]`, `/lo/[id]` |
| d5 | Đặt mẫu, đặt lô | chạy thật (luôn chờ chị); gửi cho NCC là chị tự gửi tin AI soạn | `/desk/nguon-cung/don/[id]` |
| d6 | Nhắn hỏi nhà cung cấp | chạy với AI giả (soạn/dịch); chưa gửi tự động qua WeChat/1688 | `/desk/nguon-cung/ncc/[id]` |
| d7 | Theo dõi lô hàng về | chạy thật (mốc nhập tay); theo dõi tự động qua `shipping` mock | `/desk/nguon-cung/lo/[id]` |
| e1 | Tự dựng trang sản phẩm | chạy với AI giả (viết trang ở worker); chị duyệt, đăng chạy thật | `/desk/san-pham/[id]` |
| e2 | Con dấu và hồ sơ chọn | chạy thật | `/san-pham/[slug]`, `/san-pham/[slug]/ho-so-chon` |
| e3 | Mở bán theo đợt | chạy thật (hẹn giờ, hết hạn/hết suất tự đóng, chốt sớm từ màn Đơn hàng) | `/dot`, `/dot/[slug]`, `/desk/san-pham/dot` |
| e4 | Đặt hàng một trang | chạy thật (COD); chuyển khoản VietQR chạy với mock, cần tài khoản SePay | `/gio-hang`, `/dat-hang` |
| e5 | Theo dõi đơn | chạy thật | `/don`, `/don/[code]` |
| e6 | Xử lý ảnh sản phẩm | chạy thật (cắt, cân sáng bằng Pillow, không tạo ảnh giả) | `/desk/san-pham/[id]` |
| e7 | Trợ lý hỏi đáp trên web | chạy với AI giả, cần khoá Anthropic | `/hoi`, trang sản phẩm |
| e8 | Đánh giá có ảnh của khách | chạy thật phần xin/gửi/duyệt (link «Viết đánh giá» trên trang theo dõi đơn); lọc bằng AI giả; tin xin đánh giá gửi qua `notify` mock | `/danh-gia/[token]`, `/desk/san-pham/danh-gia` |
| e9 | Trang Nhờ chị tìm | chạy thật | `/nho-tim`, `/desk/san-pham/nho-tim` |
| e10 | Để AI đọc được | chạy thật (JSON-LD Product/Offer, sitemap, `/feed.xml`) | trang sản phẩm |
| f1 | Một sản phẩm, nhiều bản | chạy với AI giả | `/desk/noi-dung/san-pham/[id]`, `/desk/noi-dung/dot/[id]` |
| f2 | Giọng của chị | chạy với AI giả | `/desk/noi-dung/giong` |
| f3 | Lịch đăng | chạy thật (xếp, đổi giờ, huỷ); AI xếp tuần bằng AI giả | `/desk/noi-dung/lich` |
| f4 | Đăng tự động | chạy với mock, cần ứng dụng Meta (Facebook/Instagram/Threads), Zalo OA, TikTok (đẩy nháp) | `/desk/noi-dung/lich` |
| f5 | Soát lời quảng cáo | chạy thật (luật số liệu/nói quá) + AI giả | xưởng nội dung |
| f6 | Dựng video ngắn | một phần — dựng bằng ffmpeg trên máy (cần `ffmpeg`), kế hoạch cắt bằng AI giả; chưa thử với clip thật | `/desk/noi-dung/video` |
| f7 | Đo và học | chạy với mock (số liệu bài giả lập); đơn theo bài qua `?src=` chạy thật | `/desk/noi-dung/so-lieu` |
| f8 | Kịch bản livestream | chạy với AI giả | `/desk/noi-dung/livestream` |
| g1 | Gom đơn mọi kênh | chạy thật (web, tạo tay, nháp từ tin nhắn); đơn sàn qua mock | `/desk/don-hang` |
| g2 | Khớp thanh toán | chạy với mock, cần tài khoản SePay (webhook) | `/desk/don-hang/van-hanh` |
| g3 | Tổng hợp đợt để đặt nguồn | chạy thật (đóng đợt → đơn đặt lô theo NCC chờ chị duyệt) | hàng chờ duyệt, `/desk/nguon-cung` |
| g4 | Tạo vận đơn | chạy với mock, cần tài khoản GHN hoặc GHTK | `/desk/don-hang/[id]`, `/desk/don-hang/in-nhan` |
| g5 | Báo tin cho khách | chạy với mock, cần OA Zalo + ZBS (mẫu ZNS đã duyệt) hoặc máy chủ SMTP — mốc đơn, mẫu tin, chống trùng, kênh dự phòng, gửi lại khi lỗi tạm thời chạy thật; driver `zalo_zns` (viết theo tài liệu ZBS Template Message 11/2026) và `email` (SMTP) mới kiểm bằng máy chủ giả | `/desk/don-hang/van-hanh` (mẫu tin, kênh đang bật, tin gửi lỗi) |
| g6 | Chốt đơn từ tin nhắn | chạy với AI giả (đơn nháp chờ chị) | hàng chờ duyệt, `/desk/don-hang` |
| g7 | Đổi trả, hoàn tiền | chạy thật (luôn chờ chị); AI kiểm điều kiện bằng AI giả; hoàn tiền thật phải chị chuyển tay | `/don/[code]`, `/desk/don-hang/[id]` |
| g8 | Tồn kho nhỏ | chạy thật (giữ hàng khi đã trả, trừ khi giao hãng, nhập khi lô bổ sung về, báo sắp hết) | `/desk/don-hang/van-hanh` |
| g9 | Bán trên TikTok Shop, Shopee | chạy với mock, cần tài khoản TikTok Shop / Shopee Open Platform (driver mới là khung) | `/desk/don-hang/van-hanh` |
| h1 | Hộp thư gộp | chạy với mock, cần ứng dụng Meta + Zalo OA (webhook) | `/desk/khach`, `/desk/khach/hoi-thoai/[id]` |
| h2 | AI soạn sẵn câu trả lời | chạy với AI giả | hội thoại |
| h3 | Chuyển cho chị | chạy thật (luật khiếu nại/sức khoẻ) + AI giả | hội thoại, hàng chờ |
| h4 | Sổ khách | chạy thật (hồ sơ ngay từ tin nhắn đầu); tóm tắt bằng AI giả | `/desk/khach/so-khach` |
| h5 | Nhóm khách quen | chạy với AI giả; gửi nhóm Zalo qua mock | `/desk/khach/khach-quen` |
| h6 | Nhắc mua lại đúng lúc | chạy thật phần lịch và kiểm đồng ý nhận tin (chỉ khách tích «đồng ý» khi đặt hàng, chưa từ chối; nhắn «TỪ CHỐI» là thôi nhận); tin nhắc bằng AI giả, gửi qua mock | `/desk/khach/nhac-mua-lai` |
| h7 | Giới thiệu bạn | chạy thật (mã `?ref=` giữ qua giỏ tới đơn) | `/desk/khach/gioi-thieu` |
| h8 | Khách thử hàng cùng chị | chạy thật (link mời, cảm nhận hiện cạnh ghi chú thử ở Bàn chọn) | `/desk/khach/thu-hang`, `/thu-hang/[token]` |
| i1 | Hôm nay | chạy thật (số liệu của mọi module) | `/desk` |
| i2 | Hàng chờ duyệt | chạy thật (duyệt / sửa rồi duyệt / trả lại, bấm tới màn hình của đối tượng) | `/desk/duyet` |
| i3 | Mức tự chủ theo từng việc | chạy thật | `/desk/tu-chu` |
| i4 | Nhật ký AI | chạy thật (hoàn tác, căn cứ, bấm tới đối tượng) | `/desk/nhat-ky-ai` |
| i5 | Báo cáo tuần | chạy thật phần số liệu; nhận xét bằng AI giả | `/desk/bao-cao` |
| i6 | Ra lệnh bằng lời | chạy với AI giả — lệnh do từng module đăng ký (`control.intent`): đề săn hàng, soạn bài cho món, tóm tắt đơn (hôm nay / chờ giao / chờ chuyển khoản), tìm khách, mở/đóng đợt (qua hàng chờ theo mức tự chủ), việc đang chờ, chi phí AI tháng, kiểm bản sao lưu, đổi mức tự chủ | nút «Nói với AI» mọi màn |
| k1 | Sổ doanh thu, chi phí | chạy thật (doanh thu khi đơn đã trả, chi phí NCC + tiền AI hằng tháng, bảng kê CSV) | `/desk/so-sach` |
| k2 | Trần chi phí AI | chạy thật phần đếm/chặn; đổi nhà cung cấp/khoá/model/trần ngay ở Cài đặt (Anthropic, OpenRouter, AI giả). Anthropic đã gọi thật được với `claude-haiku-5-5`, `claude-opus-5-5`; OpenRouter mới kiểm bằng máy chủ giả, chưa gọi thật. Model ngoài bảng giá: OpenRouter lấy chi phí nó tự báo (`usage.cost`), provider khác tính theo giá model «việc khó» (có cảnh báo trong log) | `/desk/tu-chu/chi-phi-ai`, `/desk/cai-dat/ai` |
| k3 | Nhãn AI và lưu vết | chạy thật; lưu vết cả việc đổi khoá API / cấu hình AI (ai đổi, lúc nào, đổi trường nào — không ghi giá trị khoá) | nhật ký AI, bài đăng |
| k4 | Sao lưu và phân quyền | chạy thật phần tài khoản phụ; sao lưu chạy được khi máy có `pg_dump` hoặc container Postgres (`docker exec`), image prod có `postgresql-client-16`; chép ra S3/R2 khi điền `S3_*` (driver `s3` chưa thử thật); kiểm khôi phục (checksum + giải nén + cấu trúc, không ghi đè) | `/desk/cai-dat/sao-luu`, `/desk/cai-dat/nguoi-phu-giup` |
| k5 | Hoá đơn điện tử | một phần — luồng soạn/duyệt/chống trùng chạy với mock (prod từ chối phát hành bằng mock); **chưa có driver nhà cung cấp hoá đơn thật** | `/desk/so-sach` |

## Cần chị/anh cung cấp để bật driver thật

Đặt vào `api/.env` (xem `api/.env.example`); chọn kênh mạng xã hội bằng `SOCIAL_CHANNEL_DRIVERS`.

| Việc | Cần | Biến |
|---|---|---|
| AI thật (mọi chức năng «AI giả») | Khoá Claude API hoặc OpenRouter, đặt trần chi phí tháng — nhập ở *Cài đặt → AI và khoá API* (mã hoá trong CSDL) | `SECRETS_ENCRYPTION_KEY` (bắt buộc ở prod); hoặc qua env: `AI_PROVIDER=anthropic`/`openrouter`, `ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY`, `AI_MONTHLY_BUDGET_VND` |
| Săn hàng 1688/Taobao | Tài khoản Onebound (key + secret) | `SOURCES_DRIVER=onebound`, `ONEBOUND_API_KEY`, `ONEBOUND_API_SECRET` (hoặc `SOURCES_DRIVER=web` chỉ cần khoá Anthropic) |
| Facebook Page, Instagram, Threads (đăng bài + hộp thư) | Ứng dụng Meta đã duyệt quyền `pages_manage_posts`, `pages_messaging`, `instagram_content_publish`, `instagram_manage_messages`; Page token dài hạn; webhook trỏ về `/api/hooks/social/facebook` | `META_APP_ID`, `META_APP_SECRET`, `META_PAGE_ID`, `META_PAGE_TOKEN`, `META_IG_USER_ID`, `META_WEBHOOK_VERIFY_TOKEN`, `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` |
| Zalo OA (tin nhắn, bài viết OA) | OA đã xác thực + ứng dụng Zalo, access token OA (làm mới định kỳ), webhook `/api/hooks/social/zalo_oa` | `ZALO_APP_ID`, `ZALO_OA_ID`, `ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_SECRET` |
| TikTok (đẩy bản nháp) | Ứng dụng TikTok for Developers có Content Posting API, token người dùng | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN` |
| Chuyển khoản VietQR tự khớp | Tài khoản SePay nối tài khoản ngân hàng, webhook `/api/hooks/payments/sepay` | `PAYMENTS_DRIVER=sepay`, `SEPAY_API_KEY`, `SEPAY_WEBHOOK_SECRET`, `BANK_CODE`, `BANK_ACCOUNT_NO`, `BANK_ACCOUNT_NAME` |
| Giao hàng | Tài khoản GHN (token + shop id) hoặc GHTK (token + địa chỉ lấy hàng) | `SHIPPING_DRIVER=ghn`/`ghtk`, `GHN_TOKEN`, `GHN_SHOP_ID`, `GHTK_TOKEN`, `GHTK_PICK_*` |
| Báo tin cho khách (g5) | Zalo: OA đã xác thực + ứng dụng Zalo có quyền «Gửi tin qua số điện thoại», tài khoản ZBS có số dư, các mẫu tin đã được duyệt (mỗi mốc đơn một mẫu); email: máy chủ SMTP | `NOTIFY_CHANNEL_DRIVERS=zalo_oa=zalo_zns,email=email`, `ZALO_APP_ID`, `ZALO_APP_SECRET`, `ZALO_OA_ACCESS_TOKEN`, `ZALO_OA_REFRESH_TOKEN`, `ZALO_ZNS_TEMPLATES`, `SMTP_*` (xem [deployment.md](deployment.md) mục 6) |
| Sàn TikTok Shop / Shopee | Tài khoản Partner, quyền API shop | `MARKETPLACES_DRIVER`, `TIKTOK_SHOP_*`, `SHOPEE_*` |
| Hoá đơn điện tử (k5) | Chọn nhà cung cấp (VNPT, Viettel, MISA…) — **driver chưa viết**, xem mục dưới | `EINVOICE_DRIVER` |
| Lưu ảnh/sao lưu trên S3/R2 | Bucket + khoá | `STORAGE_DRIVER=s3`, `S3_*` |

## Hoá đơn điện tử (k5): cần gì khi chọn nhà cung cấp

Interface `api/app/integrations/einvoice` đã đủ chỗ cắm: `issue` (phát hành, chống trùng theo mã đơn), `get_status` (trạng
thái + mã của cơ quan thuế), `download` (PDF / XML), `adjust` / `replace` (hoá đơn điều chỉnh / thay thế), `cancel`.
Khi chọn nhà cung cấp cần hỏi và ghi lại: tài liệu API + môi trường thử (sandbox) và cách cấp khoá; mẫu số / ký hiệu hoá
đơn đã đăng ký (hoá đơn có mã hay không mã của cơ quan thuế, loại dành cho hộ kinh doanh); cách ký số (chữ ký số của nhà
cung cấp hay USB token / ký từ xa); quy trình xử lý sai sót họ hỗ trợ (điều chỉnh, thay thế — còn cho huỷ không, theo quy
định hiện hành); cách tra trạng thái (gọi hỏi hay webhook) và thời gian cơ quan thuế cấp mã; tải được bản PDF/XML gốc
để lưu trữ không; khoá chống phát hành trùng phía họ; giá theo gói số hoá đơn và hạn mức gọi API.

## Kiểm chứng

- `scripts/check.sh api` — ruff + toàn bộ pytest (gồm `tests/integration/test_lifecycle.py`, `test_event_contract.py`, dữ liệu mẫu).
- `scripts/check.sh web` — typecheck + eslint + vitest; `bun run build`.
- `scripts/check.sh e2e` — tự dựng CSDL e2e + dữ liệu mẫu + API + worker + web rồi chạy toàn bộ Playwright
  (gồm `e2e/lifecycle.spec.ts` và `e2e/routes.spec.ts` rà mọi route ở 390px và 1280px).
