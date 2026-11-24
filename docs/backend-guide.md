# Hướng dẫn backend cho agent làm module

Đọc kèm [ARCHITECTURE.md](ARCHITECTURE.md) (hợp đồng) và [data-model.md](data-model.md) (bảng). Tài liệu này là
**giao diện lập trình** của nền móng: những gì module được dùng, cách đăng ký, và các quyết định khác với kiến trúc.

## 1. Lệnh

```bash
docker compose up -d                       # Postgres 5442, Redis 6382 (tên dự án cố định «hangchon», mọi worktree dùng chung)
./scripts/dev.sh start | stop [all] | logs [api|worker|web|infra|all] | status
scripts/check.sh api                       # ruff check + ruff format --check + toàn bộ pytest — phải xanh trước khi gộp
cd api && uv run pytest tests/<file> -k ten
cd api && uv run python -m app.seed        # tài khoản chị (OWNER_EMAIL/OWNER_PASSWORD) + dữ liệu mẫu tối thiểu
cd api && uv run arq app.worker.WorkerSettings
```

Máy có `VIRTUAL_ENV` của dự án khác: `unset VIRTUAL_ENV` trước `uv run` (scripts đã làm sẵn).

## 2. Module tự khám phá

```
api/app/modules/<ten>/
  models.py    bảng (kế thừa app.core.db.Base)          ← đã có sẵn cho 12 module, KHÔNG sửa bảng của module khác
  schemas.py   Pydantic; đã có sẵn <Model>Out cho mọi bảng (sinh từ models), thêm schema tạo/sửa/công khai tuỳ ý
  actions.py   register_action / handler / undoer / on_returned / stat_provider / intent / register_setting
  ai_tasks.py  ai.task(...) + @ai.fake(...)
  jobs.py      @job / @cron
  router.py    `router` (APIRouter) hoặc `routers` (list[APIRouter])
  service.py   nghiệp vụ (không tự nạp; router/actions import)
```

`app/core/discovery.py` nạp theo thứ tự models → actions → ai_tasks → jobs → router cho **mọi** module rồi
`app/main.py` gắn router. Không sửa `main.py`, `worker.py` hay tệp dùng chung nào để đăng ký module.
`tests/test_discovery.py` chứng minh: một thư mục module mới có ngay router + bảng + action + job + tác vụ AI.

## 3. Route

```python
from fastapi import APIRouter, status
from app.core.db import DbSession                       # AsyncSession, commit khi hàm xử lý xong không lỗi
from app.core.deps import CurrentUser, OwnerUser        # owner|helper  /  chỉ owner
from app.core.pagination import Page, Paginated, paginate
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound, AppError

router = APIRouter(prefix="/api/desk/sourcing", tags=["sourcing"])

@router.get("/briefs", response_model=Paginated[SourcingBriefOut])
async def list_briefs(_: CurrentUser, db: DbSession, page: Page) -> Paginated[SourcingBriefOut]:
    return await paginate(db, select(SourcingBrief).order_by(SourcingBrief.created_at.desc()), page, SourcingBriefOut)

@router.post("/briefs", response_model=SourcingBriefOut, status_code=status.HTTP_201_CREATED)
async def create_brief(body: BriefIn, user: CurrentUser, db: DbSession) -> SourcingBrief: ...
```

- Tiền tố: `/api/desk/<module>/**` (cần đăng nhập — middleware `DeskAuthGuard` chặn 401 kể cả khi quên `CurrentUser`,
  nhưng vẫn khai báo để có `user`), `/api/store/<module>/**` (công khai), `/api/hooks/<tich-hop>/**` (webhook, tự kiểm chữ ký).
- Mã trả: 200 GET/PATCH · 201 POST tạo mới · 204 DELETE · **POST hành động** (duyệt, trả lại, hoàn tác, chạy lại...) trả 200 kèm đối tượng.
- Đường dẫn cụ thể khai báo trước `/{id}`.
- `DbSession` commit **trước khi** gửi phản hồi (Depends scope="function"); đọc giá trị server sinh ra sau `await db.flush()`.
  Quan hệ một-nhiều nhỏ (`order.items`, `product.images`, `drop.items`...) nạp sẵn (selectin); quan hệ lớn
  (`thread.messages`, `brief.candidates`...) là `lazy="raise"` → truy vấn riêng.
- Lỗi: raise `NotFound("Không tìm thấy đơn.")`, `Conflict(...)`, `BadRequest(...)`, `Forbidden(...)` hoặc
  `AppError(message, code="ma_rieng")`. Mọi lỗi trả `{"detail": "<câu tiếng Việt>", "code": "<mã>"}`; lỗi dữ liệu 422 có thêm
  `"errors": [{"field", "message", "type"}]`. Lỗi không bắt được → 500 `internal_error` (đã log).
- Cookie phiên: `hc_session` (httpOnly, SameSite=Lax). Đăng nhập: `POST /api/desk/auth/login {email,password}` → `UserOut`;
  `POST /api/desk/auth/logout` 204; `GET /api/desk/auth/me`; `POST /api/desk/auth/password`. Tài khoản phụ: `/api/desk/users` (owner).

## 4. Model

```python
from app.core.db import Base, UUIDPk, Timestamps, CreatedAt, enum_col, fk, money, money_opt, json_list, json_obj, flag, count
from app.core.enums import StrEnum, Channel, SourcePlatform, Language, ShippingStatus, Carrier, Actor

class Thing(UUIDPk, Timestamps, Base):
    __tablename__ = "things"
    status: Mapped[ThingStatus] = mapped_column(enum_col(ThingStatus), default=ThingStatus.NEW)  # VARCHAR, giá trị chữ thường
    price_vnd: Mapped[int] = money()                       # BigInteger, mặc định 0
    product_id: Mapped[uuid.UUID | None] = fk("products")  # SET NULL + index; fk("x", ondelete="CASCADE", nullable=False)
    tags: Mapped[list[Any]] = json_list()                  # JSONB '[]'
```

- Migration: giai đoạn dựng **chỉ một file** `alembic/versions/0001_initial.py` do người tích hợp sinh lại
  (`uv run alembic revision --autogenerate`). Agent module **không** tạo file migration; test dùng `create_all`.
  `alembic/env.py` tự tách khoá ngoại `use_alter` thành `create_foreign_key` (Alembic bỏ qua chúng trong create_table).
- Thêm giá trị enum = sửa lớp enum, không cần migration (VARCHAR(40), không CHECK).
- Muốn thêm/đổi cột ở bảng **của module khác** → ghi vào báo cáo cho người tích hợp; không tự sửa.

## 5. AI — `from app import ai`

```python
# ai_tasks.py — khai báo một lần ở mức module (prompt ổn định → tận dụng cache)
ai.task("sourcing.parse_brief", system="Chuyển lời dặn của chị thành bộ lọc...", tier="smart", web=False)

@ai.fake("sourcing.parse_brief")              # dùng khi AI_PROVIDER=fake (test, máy không có khoá)
def _fake(inp: ParseBriefIn) -> ParseBriefOut:  # sync hoặc async; trả Pydantic hoặc dict hợp schema
    return ParseBriefOut(...)                    # raise ai.FakeRefusal("bio") để giả lập model từ chối

# service.py
res = await ai.run(
    "sourcing.parse_brief",          # task "<module>.<viec>"
    ParseBriefIn(text=...),          # Pydantic | dict | str — được bọc trong <du_lieu>…</du_lieu> (dữ liệu, không phải chỉ dẫn)
    ParseBriefOut,                   # Pydantic → structured output (messages.parse)
    tier="smart",                    # "smart" = AI_MODEL_SMART (claude-opus-5-5) · "fast" = AI_MODEL_FAST (claude-haiku-5-5)
    images=[b"...", "https://...", ai.AIImage(data=..., media_type="image/png")],
    web=True,                        # bật web_search_20260209 + web_fetch_20260209 (timezone Asia/Ho_Chi_Minh, không gửi country)
    system=None, max_tokens=None, effort=None,  # ghi đè khai báo task nếu cần
)
res.output        # ParseBriefOut đã kiểm khuôn
res.run_id        # → ai_runs.id; truyền vào control.propose(ai_run_id=...) và cột ai_run_id của bảng
res.cost_vnd, res.model, res.sources  # sources = [{"url","title"}] từ web search (dẫn nguồn)
```

- Không có hàm giả riêng → provider fake **tự sinh dữ liệu hợp schema** (tôn trọng ge/le/min_length, Literal, Enum).
- Lỗi (đều là AppError, route tự trả câu tiếng Việt): `AIBudgetExceeded` (409, chạm trần — đã tự tạo việc chờ chị
  `control.raise_ai_budget`), `AIRefused` (422, `.category`), `AIUnavailable` (503: khoá, mạng, quá tải), `AIOutputInvalid` (502).
  Job nền nên bắt `ai.AIError` để không retry vô hạn.
- Provider anthropic: `messages.parse(output_format=...)`, không temperature/prefill/tool_choice, không gửi `thinking`
  (Opus 5.5/Haiku 5.5 luôn adaptive; độ sâu = `output_config.effort`), cache_control trên system, tự gửi lại lượt `pause_turn`,
  model trong `AI_FALLBACK_MODELS` bật `fallbacks="default"` (beta `server-side-fallback-2026-07-01`; Haiku không hỗ trợ nên không gửi).
- Chi phí = bảng giá `DEFAULT_AI_PRICING` (ghi đè bằng `AI_PRICING`) × `AI_USD_VND_RATE` + web search; mỗi lần gọi ghi `ai_runs`.
- Trần tháng: `app_settings["ai.monthly_budget_vnd"]` nếu chị đã đặt, không thì `AI_MONTHLY_BUDGET_VND`; `0` = không giới hạn.

## 6. Giám sát — `from app import control`

### Khai báo hành động (actions.py)

```python
control.register_action(
    "content.publish_post", "Đăng bài lên mạng xã hội", "Nội dung",
    default="ask",            # "auto" | "ask" | "off" — thận trọng: nội bộ auto, khách thấy ask
    customer_facing=True,
    locked=False,             # True = luôn hỏi, chị không đổi được (đổi trả/hoàn tiền, đặt hàng & trả tiền NCC)
    description="...",
)

@control.handler("content.publish_post")
async def _publish(ctx: control.ActionContext) -> control.HandlerResult | dict | None:
    # ctx.db (phiên của nơi gọi / route duyệt), ctx.payload (đã gộp phần chị sửa), ctx.preview,
    # ctx.mode "auto"|"approved", ctx.item (ApprovalItem|None), ctx.user (người duyệt|None), ctx.ref_type, ctx.ref_id
    ...
    return control.HandlerResult(result={...}, undo={...}, summary="...", ref_type="scheduled_posts", ref_id=post.id)

@control.undoer("content.publish_post")      # chỉ khi hoàn tác được; nhận ctx.undo = HandlerResult.undo
async def _unpublish(ctx: control.UndoContext) -> None: ...

@control.on_returned("content.publish_post")  # chị trả lại kèm lời nhắn → soạn lại (thường propose lại cùng dedupe_key)
async def _redo(ctx: control.ReturnContext) -> None: ...   # ctx.item, ctx.note
```

Handler chạy trong **savepoint**: lỗi thì mọi ghi trong handler bị huỷ.

### Đề xuất

```python
out = await control.propose(
    "content.publish_post", "Đăng bài Facebook: Bình giữ nhiệt",
    payload={...},              # đủ để thực thi (JSON được)
    preview={...},              # thứ hiện cho chị xem
    db=db,                      # cùng giao dịch với nơi gọi; bỏ trống → tự mở phiên + commit
    summary=None, rationale="căn cứ", sources=[{"url": ...}],
    ref_type="content_drafts", ref_id=draft.id,   # đối tượng liên quan (lọc nhật ký/hàng chờ theo đối tượng)
    ai_run_id=res.run_id,
    dedupe_key=f"draft:{draft.id}",               # đang có việc chờ cùng khoá → cập nhật thay vì tạo mới
    priority=0, ai_generated=True,
)
out.status   # "applied" (đã làm, out.activity_id, out.result) | "pending" (out.item_id) | "blocked" (đang tắt)
             # | "failed" (mức auto nhưng handler lỗi; out.error) — xem mục 10
out.level    # AutonomyLevel thực tế
```

Khác: `control.cancel_pending(db, action=..., dedupe_key=... | ref_type=..., ref_id=...)` huỷ việc chờ không còn cần;
`control.get_level(db, action)`; `control.audit(db, "module.viec", user=..., entity_type=..., entity_id=..., summary=..., data=...)`;
`control.register_setting(key, label, default, group=...)` + `control.get_setting(db, key)` / `control.set_setting(db, key, value, user)`.

### «Hôm nay» và lệnh bằng lời

```python
@control.stat_provider("orders.today", order=10)
async def _stats(db) -> list[control.Stat]:   # lỗi trong provider bị bỏ qua, không làm hỏng màn hình
    return [control.Stat(key="orders.today", label="Đơn hôm nay", value=3, order=3),
            control.Stat(key="orders.cash", label="Tiền về", value=450000, format="vnd", href="/desk/don-hang")]

@control.intent("sourcing.new_brief", "Tạo đề săn hàng", "Chị dặn tiêu chí tìm một món mới",
                params=NewBriefParams, examples=["tìm giúp chị bình giữ nhiệt dưới 200 nghìn"])
async def _new_brief(ctx: control.CommandContext, params: NewBriefParams) -> control.CommandResult:
    # ctx.db, ctx.user, ctx.text, ctx.context (màn hình/đối tượng web gửi kèm). Việc khách thấy → control.propose bên trong.
    return control.CommandResult(message="Em đã tạo đề...", href="/desk/san-hang/...", data={...})
```

Endpoint control (đều dưới `/api/desk/control`): `GET /today` · `GET /approvals?status=&action=&module=&page=&size=` ·
`GET /approvals/{id}` · `POST /approvals/{id}/approve {payload?, note?}` · `POST /approvals/{id}/return {note}` ·
`GET /activity?action=&module=&mode=&ref_type=&ref_id=` · `POST /activity/{id}/undo` · `GET /autonomy` ·
`PATCH /autonomy/{action} {level}` · `GET /ai/costs?month=YYYY-MM` · `PATCH /ai/budget {monthly_budget_vnd}` · `GET /ai/runs` ·
`GET /settings` · `PATCH /settings/{key} {value}` · `GET /audit` · `GET /commands` · `POST /command {text, context}`.
Duyệt/trả lại/hoàn tác/đổi mức/cài đặt/lưu vết: **chỉ owner**; helper xem được.

## 7. Việc nền — `app.core.jobs`

```python
from app.core.jobs import job, cron, enqueue

@job("orders.sync_payments")
async def sync_payments(ctx, since: str | None = None) -> int:
    async with ctx["db"]() as db: ...; await db.commit()

@cron("orders.poll_tracking", minute={0, 30})     # tham số của arq.cron; giờ là GIỜ VIỆT NAM (WorkerSettings.timezone)
async def poll(ctx) -> None: ...

await enqueue("orders.sync_payments", since=None, _defer_by=60)
```

Tên job `"<module>.<viec>"`. Test đặt `JOBS_EAGER=true` → `enqueue` chạy ngay trong tiến trình và trả kết quả.

## 8. Tích hợp — `from app.integrations import get_driver`

| kind | Interface (`app/integrations/<kind>/__init__.py`) | Mock có thêm |
|---|---|---|
| `sources` | `search(SourceQuery)`, `fetch_product(url)`, `search_by_image(bytes\|url)`, `fetch_reviews(url)`, `trends()`, `market_prices(query)` | dữ liệu xác định theo đầu vào |
| `social` | `publish(SocialPost)` (TikTok → `draft_pushed`), `fetch_inbound(since)`, `send_message`, `reply_comment`, `post_metrics`, `parse_webhook` | `simulate_inbound(text, channel=, kind=, author_name=)`, `published`, `sent` |
| `payments` | `create_request(order_code, amount_vnd)` → nội dung CK + QR, `parse_webhook`, `list_transactions(since)` | `simulate_transfer(amount_vnd, content)`, `sign(body)` |
| `shipping` | `quote(req)`, `create(req, service)`, `track(code)`, `cancel(code)`, `parse_webhook` | không giữ trạng thái: lên nấc theo thời gian; `advance(n)` để tua; service `"fail"` đi nhánh hoàn |
| `notify` | `send(OutboundNotification)` | `outbox`; người nhận chứa «fail» → lỗi |
| `marketplaces` | `upsert_product`, `update_stock`, `fetch_orders`, `update_order_status` | `simulate_order(marketplace, sku, qty)` |
| `einvoice` | `issue(InvoiceRequest)` (cùng `reference` không phát hành trùng), `cancel` | — |
| `storage` | `put/get/delete/exists/url` | driver `local` (mặc định), `s3` (chưa kiểm chứng với dịch vụ thật) |

- Chọn driver bằng env `<KIND>_DRIVER` (mặc định `mock`; storage `local`), hoặc `get_driver("shipping", "ghn")`.
  Driver mới = tệp `app/integrations/<kind>/<ten>.py` có lớp `Driver` kế thừa interface — không cần đăng ký thêm.
- Driver mock giữ trạng thái **trong bộ nhớ của từng tiến trình** (API và worker không chung), trừ shipping.
- Webhook mock: header `X-Mock-Signature: sha256=<hmac(HOOKS_MOCK_SECRET, body)>`.
- Tệp: `from app.core.storage import get_storage, new_key` → `await get_storage().put(new_key("public/products", "jpg"), data, "image/jpeg")`.
  `public/...` phục vụ công khai qua `/api/files/<key>`, `private/...` cần đăng nhập. Lưu **khoá**, không lưu URL.

## 9. Tiện ích

`app.core.money`: `to_vnd(amount, fx_rate)`, `round_vnd(v, step=1000)`, `margin_pct(price, cost)`, `format_vnd`, `format_vnd_short`.
`app.core.timeutil`: `now_utc()`, `to_local()`, `local_today()`, `local_day_bounds_utc(day)`, `month_key()`,
`local_month_bounds_utc("YYYY-MM")`, `week_start()`, `VN_TZ`. `app.core.security`: `random_token()`, `hmac_sha256`, `verify_hmac_sha256`.

## 10. Test

- CSDL: `hangchon_test_<thư-mục-worktree>` (vd `hangchon_test_f_api`), tự tạo; `create_all` một lần mỗi phiên, **TRUNCATE mọi bảng
  sau mỗi test**. Đổi máy chủ bằng `TEST_PG_URL`. Không chạy `pytest -n` (các worker dùng chung một CSDL).
- Fixture (`tests/conftest.py`): `db` (AsyncSession, tự commit cuối test) · `client` (chưa đăng nhập) · `owner`, `helper` (User) ·
  `owner_client`, `helper_client` (httpx đã đăng nhập) · `fake_ai` (dict tên tác vụ → hàm giả, tự gỡ) ·
  `temp_registry` (đăng ký action/intent/stat/setting tạm, tự khôi phục). Hằng: `OWNER_EMAIL`, `OWNER_PASSWORD`.
- Driver mock được tạo mới mỗi test (`reset_drivers`): `get_driver("payments").simulate_transfer(...)`.
- Đặt test module tại `api/tests/<module>/test_*.py` (thêm `__init__.py`).

## 11. Quyết định khác tài liệu kiến trúc (25/11/2026)

1. **`control.propose` có thêm trạng thái `"failed"`** (ngoài applied/pending/blocked): mức `auto` mà handler lỗi thì không ghi nhật ký,
   chỉ ghi `audit_log` `control.auto_failed` — không raise để job nền không lặp lại tác dụng phụ.
   Duyệt mà handler lỗi → việc chờ chuyển `failed`, duyệt lại được.
2. **POST hành động trả 200** (approve/return/undo/command), POST tạo mới trả 201.
3. **Enum lưu VARCHAR(40) không dùng enum Postgres** (vẫn `values_callable`) để thêm giá trị không cần migration.
4. **`ai.run` trả `AIResult`** (`.output`, `.run_id`, `.cost_vnd`, `.sources`...) thay vì trả thẳng output — cần `run_id` để nối
   ai_activity / bảng nghiệp vụ và `sources` để dẫn nguồn.
5. Bảng bổ sung ngoài danh sách mục 7: `demand_mentions`, `assessment_scores`, `comparison_items`, `product_variants`,
   `inventory_movements`, `customer_identities`, `order_events`, `marketplace_listings`, `content_insights`, `group_digests`,
   `referral_uses` (tổng 80 bảng).
6. `users` thuộc module control; xác thực ở `/api/desk/auth/*`, quản lý tài khoản phụ ở `/api/desk/users`.
7. Docker compose đặt `name: hangchon` để mọi worktree dùng chung một bộ container; `dev.sh stop` chỉ tắt tiến trình của
   worktree, `dev.sh stop all` mới tắt container.
8. Email đăng nhập không dùng `EmailStr` (email-validator từ chối tên miền `.local` dùng khi chạy máy).
9. Trần chi phí AI = 0 nghĩa là không giới hạn; khi chạm trần mọi tác vụ AI dừng (không chỉ tác vụ tự động) và tạo một việc
   khoá `control.raise_ai_budget` mỗi tháng (chị trả lại = giữ nguyên trần, không hỏi lại trong tháng).
10. Cron arq chạy theo giờ Việt Nam.

## 12. Còn dở (để module sau làm)

- Driver thật: `sources/web`, `sources/onebound`, `social/meta|tiktok_draft|zalo_oa`, `payments/sepay`, `shipping/ghn|ghtk`,
  `notify/zalo_oa|email`, `marketplaces/tiktok_shop|shopee`; `storage/s3` mới viết, chưa kiểm chứng.
- Service/router/UI của 11 module nghiệp vụ; dữ liệu mẫu đầy đủ (`app/seed.py` mới có phần tối thiểu).
- Provider anthropic mới kiểm bằng client giả (chưa gọi API thật vì chưa có khoá); fallbacks `"default"` cho Opus 5.5 theo tài liệu.
