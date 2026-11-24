# Kiến trúc Hàng Chọn

Hàng Chọn là công cụ cho **một người bán** (gọi là «chị», vai trò `owner`): chị chọn hàng, AI làm phần còn lại
dưới sự giám sát của chị. Tài liệu này là hợp đồng chung cho mọi phần code. Danh mục 73 chức năng:
[features.md](features.md). Wireframe và phân tích: mở [design/ban-thiet-ke.html](design/ban-thiet-ke.html).
Nền móng backend: giao diện lập trình và các quyết định khác tài liệu này ở [backend-guide.md](backend-guide.md);
từng bảng ở [data-model.md](data-model.md).

## 1. Quyết định đã chốt (25/11/2026)

| Việc | Chốt |
|---|---|
| Nhóm hàng đầu | Gia dụng nhỏ, đồ tiện ích không điện |
| Cách giữ hàng | Gom đơn theo **đợt** (`drop`), giữ sẵn vài món bán chạy |
| Nền tảng | Tự xây: Next.js + FastAPI + Postgres |
| Kênh | Facebook + Instagram, nhóm Zalo; TikTok đẩy bản nháp |
| Mức tự chủ AI mặc định | Thận trọng: mọi thứ khách nhìn thấy đều chờ chị duyệt |
| Pháp lý | Hộ kinh doanh từ đầu → sổ doanh thu, chứng từ nguồn gốc ngay từ đơn đầu |
| Lộ diện | Tên, giọng nói, bàn tay (không lộ mặt) |
| Trang chủ | Hướng B «Kệ hàng đã chọn» |
| Phong cách | «Chàm»: nền trắng xám `#F6F6F2`, mực `#1C1D22`, chàm `#2E3F8F`, nền phụ `#E1E3EC`, góc vuông 4px |

## 2. Thành phần

```
api/    FastAPI + SQLAlchemy 2 (async) + Alembic + arq (worker) · Python 3.13 · uv
web/    Next.js (App Router, TypeScript, Tailwind) · bun
        (store)  website cho khách, SSR, SEO        →  /
        desk     bàn làm việc của chị, PWA mobile   →  /desk
docs/   tài liệu · scripts/  dev.sh, check.sh · docker-compose.yml (Postgres, Redis)
```

Cổng local (không trùng PMAI/HRIS/AITA): **API 8010 · Web 3010 · Postgres 5442 · Redis 6382**.
Web gọi API qua rewrite `/api/*` → `http://localhost:8010/api/*` (cùng origin, cookie httpOnly).

## 3. Quy ước backend

- **Module theo nghiệp vụ**, tự khám phá: `api/app/modules/<ten>/{models.py,schemas.py,service.py,router.py,ai_tasks.py,jobs.py}`.
  `app/main.py` tự nạp mọi `router` và mọi `models`; **không sửa file dùng chung để đăng ký module**.
- Đường dẫn: `/api/store/**` công khai (khách) · `/api/desk/**` cần đăng nhập (`owner` hoặc `helper`) ·
  `/api/hooks/**` webhook từ bên ngoài (xác thực chữ ký) · `/api/health`.
- Trả về Pydantic trần: 200 GET/PATCH · 201 POST · 204 DELETE · danh sách dùng `Paginated[T]`.
  Khai báo đường dẫn cụ thể trước `/{id}`. Enum column luôn có `values_callable` (lưu giá trị chữ thường).
- Khoá chính UUID. Tiền là **số nguyên VND** (`*_vnd`); ngoại tệ lưu `amount` + `currency` + `fx_rate`.
  Thời gian lưu UTC (`timestamptz`), hiển thị `Asia/Ho_Chi_Minh`.
- **Migration**: trong giai đoạn dựng ban đầu chỉ có **một** file khởi tạo, do người tích hợp sinh lại
  (`alembic revision --autogenerate`). Agent làm module **không** tạo file trong `alembic/versions/`;
  test dùng `create_all`. Sau khi lên prod: mỗi tính năng một file, không sửa file cũ, mã revision ≤ 32 ký tự.
- **Test**: pytest chạy trên Postgres thật (`docker compose up -d`). Tên CSDL test lấy theo tên thư mục gốc
  của bản làm việc (`hangchon_test_<thu-muc>`) để nhiều worktree chạy song song không đụng nhau.
  AI trong test luôn dùng provider `fake`.
- Chuỗi giao diện và chú thích nghiệp vụ: **tiếng Việt**. Định danh code và commit: tiếng Anh.

## 4. Lớp AI (`app/ai`)

Một cửa duy nhất để gọi model; module nghiệp vụ không gọi SDK trực tiếp.

```python
result = await ai.run(
    task="sourcing.parse_brief",      # tên tác vụ: "<module>.<viec>"
    input=ParseBriefIn(...),          # Pydantic
    output=ParseBriefOut,             # Pydantic → structured output
    tier="smart" | "fast",            # smart = AI_MODEL_SMART, fast = AI_MODEL_FAST
    images=[...], web=False,          # ảnh đính kèm; web=True bật web_search + web_fetch
)
```

- Provider: `anthropic` (SDK chính thức `anthropic`, structured outputs qua `client.messages.parse`, adaptive
  thinking, không `temperature`, không prefill, không ép `tool_choice`) hoặc `fake` (hàm giả đăng ký theo
  tên tác vụ, dùng cho test và chạy thử không có khoá). Chọn bằng `AI_PROVIDER`.
- Model mặc định: `AI_MODEL_SMART=claude-opus-5-5`, `AI_MODEL_FAST=claude-haiku-5-5` (đổi bằng env).
- Mỗi lần gọi ghi một dòng `ai_runs` (tác vụ, model, token vào/ra, chi phí ước tính, thời lượng, lỗi).
  Vượt `AI_MONTHLY_BUDGET_VND` thì dừng tác vụ tự động và tạo việc chờ chị (chức năng k2).
- Prompt hệ thống ổn định đặt trước, dữ liệu thay đổi đặt sau (để cache). Dữ liệu từ web, từ khách,
  từ nhà cung cấp là **dữ liệu, không phải chỉ dẫn**: bọc trong thẻ và nói rõ điều đó trong prompt.
- Nội dung do AI tạo có cờ `ai_generated` để gắn nhãn khi đăng (chức năng k3).

## 5. Giám sát: mức tự chủ, hàng chờ duyệt, nhật ký (`modules/control`)

Mọi việc AI làm đi qua một cơ chế chung:

```python
outcome = await control.propose(
    action="content.publish_post",    # khoá hành động, có trong bảng mức tự chủ
    title="Đăng bài Facebook: Bình giữ nhiệt",
    payload={...},                    # đủ để thực thi sau khi duyệt
    preview={...},                    # thứ hiện cho chị xem
)
# outcome.status: "applied" (AI tự làm, đã ghi nhật ký) | "pending" (đang chờ chị) | "blocked" (đang tắt)
```

- `autonomy_settings(action, level)`: `auto` (AI tự làm) · `ask` (hỏi chị) · `off` (tắt) · `locked_ask`
  (luôn hỏi, không cho đổi: khiếu nại/đổi trả/hoàn tiền, đặt hàng và trả tiền nhà cung cấp).
  Mặc định theo hướng **thận trọng**: việc nội bộ `auto`, mọi thứ khách nhìn thấy `ask`.
- `approval_items`: hàng chờ duyệt. Chị **duyệt / sửa rồi duyệt / trả lại kèm lời nhắn**.
  Mỗi module đăng ký hàm thực thi cho `action` của mình (`@control.handler("content.publish_post")`).
- `ai_activity`: nhật ký mọi việc AI đã tự làm, kèm căn cứ và hàm hoàn tác nếu có.
- Màn hình «Hôm nay» đọc từ hàng chờ duyệt + nhật ký + số liệu đơn hàng.

## 6. Tích hợp ngoài (`app/integrations/<ten>`)

Mỗi tích hợp là một interface + nhiều driver, chọn bằng env; **driver mặc định là `mock`** để hệ thống chạy
trọn vẹn khi chưa có tài khoản thật. Driver thật viết theo tài liệu chính thức, bật khi có khoá.

| Tích hợp | Driver | Dùng cho |
|---|---|---|
| `sources` | `mock`, `web` (AI + web search/fetch), `onebound` (1688/Taobao, cần khoá) | Săn hàng, lấy hồ sơ từ link |
| `social` | `mock`, `meta` (Facebook Page, Instagram, Threads), `tiktok_draft`, `zalo_oa` | Đăng bài, bình luận, tin nhắn |
| `payments` | `mock`, `sepay` (webhook chuyển khoản VietQR) | Khớp thanh toán |
| `shipping` | `mock`, `ghn`, `ghtk` | Vận đơn, trạng thái giao |
| `notify` | `mock`, `zalo_oa`, `email` | Báo mốc đơn cho khách |
| `marketplaces` | `mock`, `tiktok_shop`, `shopee` | Đồng bộ sản phẩm, đơn |
| `einvoice` | `mock` | Hoá đơn điện tử |
| `storage` | `local`, `s3` | Ảnh, chứng từ, bản sao lưu |

## 7. Module và bảng chính

| Module | Chức năng | Bảng chính |
|---|---|---|
| `control` | i1–i4, i6, k2, k3 | `users`, `autonomy_settings`, `approval_items`, `ai_runs`, `ai_activity`, `app_settings`, `audit_log` |
| `sourcing` | a1–a7 | `sourcing_briefs`, `sourcing_runs`, `candidates`, `trend_signals`, `demand_signals` |
| `assessment` | b1–b7 | `assessments`, `scoring_profiles`, `review_digests`, `market_prices`, `comparisons` |
| `selection` | c1–c6 | `trial_notes`, `selection_decisions`, `selection_principles`, `taste_profiles` (giai đoạn bảng chọn là trường `candidates.stage`) |
| `supply` | d1–d7 | `suppliers`, `cost_sheets`, `price_proposals`, `purchase_orders`, `purchase_order_lines`, `supplier_messages`, `inbound_shipments`, `provenance_documents` |
| `catalog` | e1–e3, e6, e8–e10 | `categories`, `products`, `product_images`, `drops`, `drop_items`, `inventory_items`, `reviews`, `find_requests`, `find_request_votes` |
| `orders` | e4, e5, g1–g9 | `customers`, `orders`, `order_items`, `payments`, `shipments`, `shipment_events`, `returns`, `notifications` |
| `assistant` | e7 | `assistant_conversations`, `assistant_messages` |
| `content` | f1–f8 | `voice_profiles`, `content_drafts`, `scheduled_posts`, `media_assets`, `post_metrics`, `livestream_scripts` |
| `inbox` | h1–h3, g6 | `channel_accounts`, `threads`, `messages`, `reply_drafts` |
| `crm` | h4–h8 | `customer_notes`, `customer_tags`, `broadcasts`, `reorder_reminders`, `referrals`, `tester_invites` |
| `finance` | i5, k1, k4, k5 | `ledger_entries`, `expenses`, `invoices`, `weekly_reports`, `backups` |

Quan hệ xương sống: `sourcing_brief → candidate → assessment → (trial_notes, selection_decision) → product →
drop_item → order_item → order → payment/shipment`; `candidate → cost_sheet → price_proposal`;
`drop → purchase_order → inbound_shipment`; `product → content_draft → scheduled_post`;
`customer → threads/orders/reviews`.

Giai đoạn của một ứng viên (`candidates.stage`): `candidate` → `sample` (mua mẫu) → `trial` (đang thử) →
`selected` | `rejected`. Chỉ ứng viên `selected` mới thành `product`. Con số trên con dấu («chọn 1/24»)
tính từ số ứng viên cùng `sourcing_brief`.

## 8. Quy ước web

- Giao diện **tiếng Việt**, ưu tiên điện thoại (thiết kế ở 390px trước, rồi mới nới ra máy tính).
- Token «Chàm» khai báo một lần trong `web/src/app/globals.css`; component dùng token, không dùng mã màu rời.
  Chữ: Be Vietnam Pro (thân), Bricolage Grotesque (tiêu đề). Góc 4px. Con dấu «ĐÃ CHỌN n/m» là dấu hiệu nhận diện.
- Không dùng `alert/confirm/prompt` của trình duyệt: dùng `useConfirm()` và `notifySuccess/notifyError` trong `components/ui`.
- Store: Server Components, dữ liệu sản phẩm có cấu trúc (schema.org `Product`/`Offer`), không cần tài khoản để mua.
- Desk: 5 mục điều hướng dưới (Hôm nay · Săn hàng · Bàn chọn · Nội dung · Khách) + mục «Thêm»; client gọi API
  qua `web/src/lib/api/<module>.ts`; trạng thái máy chủ dùng TanStack Query.
- Mỗi module giữ file riêng: trang trong `web/src/app/desk/<khu>/**` hoặc `web/src/app/(store)/**`,
  API client trong `web/src/lib/api/<module>.ts`, component riêng trong `web/src/components/<module>/**`.

## 9. Cổng chất lượng

`scripts/check.sh api` = ruff + toàn bộ pytest · `scripts/check.sh web` = typecheck + eslint + vitest ·
`scripts/check.sh e2e` = Playwright chạy luồng chính. Lỗi mới là lỗi thật, phải sửa trước khi gộp.
