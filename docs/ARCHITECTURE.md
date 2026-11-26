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

- Provider: `anthropic` (SDK chính thức `anthropic`, structured outputs qua `output_config.format` — khuôn mọi thuộc tính required, xem `app/ai/schema.py`, adaptive
  thinking, không `temperature`, không prefill, không ép `tool_choice`), `openrouter` (REST tương thích OpenAI qua
  `httpx`, `response_format` json_schema, plugin `web`) hoặc `fake` (hàm giả đăng ký theo tên tác vụ, dùng cho test và
  chạy thử không có khoá). Thêm provider = một tệp `app/ai/providers/<ten>.py` với lớp `@register`.
- Cấu hình (`app/ai/config.py`): chị chọn provider, khoá (mã hoá, `SECRETS_ENCRYPTION_KEY`), model, effort, trần ở
  *Cài đặt → AI và khoá API* (bảng `ai_provider_configs`). Thứ tự **Cài đặt > biến môi trường > mặc định**; đọc lại mỗi
  lần gọi (cache 5 giây, xoá khi lưu) nên đổi là có hiệu lực ngay, kể cả worker.
- Model mặc định: `AI_MODEL_SMART=claude-opus-5-5`, `AI_MODEL_FAST=claude-haiku-5-5` (đổi bằng env hoặc Cài đặt).
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
Mạng xã hội và sàn: chị nhập khoá + bật chạy thật từng kênh ở *Cài đặt → Mạng xã hội* (`app/integrations/channel_config.py`,
thứ tự **Cài đặt > env**; driver đọc `channel_config.value(kênh, ô)` thay vì `settings.*`), xem [channel-accounts.md](channel-accounts.md).

| Tích hợp | Driver | Dùng cho |
|---|---|---|
| `sources` | `mock`, `web` (AI + web search/fetch), `onebound` (1688/Taobao/Tmall, cần khoá), `rakuten` (Rakuten API), `routed` (mỗi sàn một đường, chọn ở *Cài đặt → Nguồn hàng*, xem [source-accounts.md](source-accounts.md)) | Săn hàng, lấy hồ sơ từ link |
| `social` | `mock`, `meta` (Facebook Page, Instagram, Threads), `tiktok_draft`, `zalo_oa` | Đăng bài, bình luận, tin nhắn |
| `payments` | `mock`, `sepay` (webhook chuyển khoản VietQR) | Khớp thanh toán |
| `shipping` | `mock`, `ghn`, `ghtk` | Vận đơn, trạng thái giao |
| `notify` | `mock`, `zalo_zns` (Zalo ZNS / ZBS Template Message), `email` (SMTP) — chọn theo kênh `NOTIFY_CHANNEL_DRIVERS` | Báo mốc đơn cho khách, xin đánh giá, nhắc mua lại |
| `marketplaces` | `mock`, `tiktok_shop`, `shopee` | Đồng bộ sản phẩm, đơn |
| `einvoice` | `mock` (interface: phát hành, tra trạng thái, tải PDF/XML, điều chỉnh/thay thế, huỷ) | Hoá đơn điện tử |
| `storage` | `local`, `s3` | Ảnh, chứng từ, bản sao lưu |

## 7. Module và bảng chính

| Module | Chức năng | Bảng chính |
|---|---|---|
| `control` | i1–i4, i6, k2, k3 | `users`, `autonomy_settings`, `approval_items`, `ai_runs`, `ai_activity`, `app_settings`, `audit_log`, `ai_provider_configs` |
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
`selected` | `rejected`. Chỉ ứng viên `selected` mới thành `product`. Con số trên con dấu («chọn 1/24», chỉ hiện ở desk)
tính từ số ứng viên cùng `sourcing_brief`.

## 8. Quy ước web

- Giao diện **tiếng Việt**, ưu tiên điện thoại (thiết kế ở 390px trước, rồi mới nới ra máy tính).
- Token «Chàm» khai báo một lần trong `web/src/app/globals.css`; component dùng token, không dùng mã màu rời.
  Chữ: Be Vietnam Pro (thân), Bricolage Grotesque (tiêu đề). Góc 4px. Con dấu «ĐÃ CHỌN» là dấu hiệu nhận diện (website không kèm số; desk kèm n/m).
- Không dùng `alert/confirm/prompt` của trình duyệt: dùng `useConfirm()` và `notifySuccess/notifyError` trong `components/ui`.
- Store: Server Components, dữ liệu sản phẩm có cấu trúc (schema.org `Product`/`Offer`), không cần tài khoản để mua.
- Desk: 6 mục điều hướng chính (Hôm nay · Săn hàng · Bàn chọn · Sản phẩm · Nội dung · Khách) + mục «Thêm»; client gọi API
  qua `web/src/lib/api/<module>.ts`; trạng thái máy chủ dùng TanStack Query.
- Mỗi module giữ file riêng: trang trong `web/src/app/desk/<khu>/**` hoặc `web/src/app/(store)/**`,
  API client trong `web/src/lib/api/<module>.ts`, component riêng trong `web/src/components/<module>/**`.

## 9. Cổng chất lượng

`scripts/check.sh api` = ruff + toàn bộ pytest · `scripts/check.sh web` = typecheck + eslint + vitest ·
`scripts/check.sh e2e` = Playwright chạy luồng chính. Lỗi mới là lỗi thật, phải sửa trước khi gộp.

## 10. Sự kiện giữa các module

Module không gọi service của module khác. Bên phát gọi `await events.emit(ten, payload, db=db)`; bên nghe khai báo
`@events.on(ten)` trong `app/modules/<ten>/events.py` (xem `app/core/events.py`). `payload` chỉ gồm id và dữ liệu gọn.
Đọc dữ liệu của module khác thì truy vấn bảng của nó (chỉ đọc); **ghi** vào bảng của module khác chỉ qua sự kiện.

| Sự kiện | Payload | Bên phát | Bên nghe (việc phải làm) |
|---|---|---|---|
| `brief.created` | `brief_id` | sourcing | — |
| `candidate.assessed` | `candidate_id`, `assessment_id` | assessment | sourcing (cập nhật điểm xếp hạng), selection (đạt điểm đạt của khung chấm → việc chờ «mua mẫu?», `selection.suggest_sample`) |
| `candidate.stage_changed` | `candidate_id`, `from`, `to` | selection | supply (sang Mua mẫu → đơn đặt mẫu chờ chị duyệt) |
| `candidate.selected` | `candidate_id`, `decision_id` | selection | catalog (tạo sản phẩm nháp, e1), selection (học gu, c6) |
| `candidate.rejected` | `candidate_id`, `decision_id` | selection | selection (học gu) |
| `price.approved` | `candidate_id`, `price_vnd`, `price_proposal_id`, `product_id` | supply | catalog (cập nhật giá bán) |
| `product.published` | `product_id` | catalog | content (soạn bài các kênh, f1) |
| `drop.opened` | `drop_id` | catalog | content (bài báo mở đợt), crm (tin cho nhóm khách quen) |
| `drop.closed` | `drop_id` | catalog | orders (chốt danh sách đơn của đợt), supply (soạn đơn đặt nguồn, g3) |
| `order.created` | `order_id` | orders | crm (sổ khách, mã giới thiệu, đánh dấu đã mua lại) |
| `order.paid` | `order_id`, `payment_id` | orders | finance (ghi sổ doanh thu, k1), catalog (ghi suất/tồn của đơn đã trả; hết suất thì đóng đợt) |
| `order.cancelled` | `order_id`, `was_paid` | orders | catalog (trả suất/tồn) |
| `order.shipped` | `order_id`, `shipment_id` | orders | catalog (món giữ sẵn rời kho: trừ `on_hand` một lần); orders tự báo khách |
| `order.delivered` | `order_id` | orders | catalog (xin đánh giá, e8), crm (nhắc mua lại h6, giới thiệu h7) |
| `order.unpaid` | `order_id`, `payment_id`, `amount_vnd` | orders (chị hoàn tác «khớp khoản chuyển tới», đơn về chờ chuyển khoản) | catalog (tính lại phần tồn/suất đang giữ); finance (chưa nghe: ghi giảm doanh thu — việc của người tích hợp) |
| `inventory.adjust_requested` | `request_id`, `product_id`, `variant_id?`, `set_on_hand?`, `kind`, `note?`, `user_id?`, `low_stock_threshold?` | orders (g8: chị nhập tồn đầu kỳ / điều chỉnh / đặt ngưỡng) | catalog (ghi `inventory_items` + `inventory_movements`, idempotent theo `request_id`) |
| `order.refunded` | `order_id`, `amount_vnd`, `return_id?`, `payment_id?` | orders | finance (ghi giảm trừ), catalog (trả suất/tồn) |
| `inbound.arrived` | `inbound_shipment_id` | supply | orders (đơn chuyển sang chờ giao), catalog (lô bổ sung → nhập tồn; mọi lô của đợt đã về → đợt sang giao) |
| `message.received` | `thread_id`, `message_id` | inbox | orders (hồ sơ khách cho người lạ; nhận ra ý định mua g6), crm (sổ khách), sourcing (nghe khách muốn gì, a6) |
| `customer.identified` | `customer_id`, `thread_id`, `channel`, `external_id`, `created` | orders | inbox (gắn hội thoại vào hồ sơ khách), crm (tóm tắt sổ khách) |
| `review.published` | `review_id`, `product_id` | catalog | content (đánh giá ≥ 4★ → gợi ý bài kể lại lời khách, `content.suggest_post`) |
| `find_request.created` | `find_request_id` | catalog | sourcing (tín hiệu nhu cầu, a6) |
| `find_request.threshold` | `find_request_id` | catalog | sourcing (đề xuất mở đề tìm) |
| `tester.feedback_received` | `tester_invite_id`, `candidate_id`, `customer_id`, `customer_name`, `feedback`, `rating` | crm | selection (ghi chú thử `author=tester` cạnh ghi chú của chị, h8) |
| `post.published` | `scheduled_post_id` | content | — |
| `expense.recorded` | `expense_id` **hoặc** `source_key`, `amount_vnd`, `category`, `incurred_on`, `description`, `vendor?`, `purchase_order_id?` | supply (trả tiền NCC), control (tiền AI tháng trước, ngày 1 hằng tháng) | finance (có `expense_id` → ghi sổ chi phí đó; không thì tạo `expenses` theo `source_key` rồi ghi sổ) |

Một cách tính suất/tồn duy nhất: đơn **chưa trả** còn sống do orders tự cộng «giữ tạm» khi kiểm còn hàng; đơn **đã trả**
(`orders.paid_at`) do catalog ghi vào `drop_items.slots_reserved` / `inventory_items.reserved` (tính lại từ đơn nên
không trừ hai lần). Hằng số chung ở `app/modules/orders/models.py` (`RELEASED_STATUSES`, `PRE_SHIP_STATUSES`).
Kiểm hợp đồng: `api/tests/integration/test_event_contract.py` (bên nghe của từng dòng + các chuỗi) và
`api/tests/integration/test_lifecycle.py` (vòng đời trọn một món).

Bên phát phải phát sự kiện dù chưa có ai nghe. Bên nghe phải chạy được lặp lại mà không sinh trùng (idempotent).
