# CLAUDE.md

Hàng Chọn — nền tảng bán hàng cá nhân: một người chọn hàng («chị»), AI làm phần còn lại dưới sự giám sát của chị.
Monorepo: `api/` (FastAPI + arq), `web/` (Next.js: website `/` + bàn làm việc PWA `/desk`).

**Nguyên tắc:** viết ít code nhất giải quyết được việc, chỉ đụng thứ cần đụng, nêu rõ chỗ chưa chắc thay vì đoán,
kiểm chứng bằng tiêu chí rõ ràng.

## Lệnh

```bash
./scripts/dev.sh start | stop | logs      # hạ tầng (Postgres 5442, Redis 6382) + API :8010 + worker + Web :3010
scripts/check.sh [api|web|e2e]            # cổng trước khi gộp
# api/:  uv run pytest tests/<module> -k "ten"   ·   uv run alembic upgrade head
# web/:  bun dev | bun run typecheck | bun run lint | bun run test
```

## Quy tắc

- **Ngôn ngữ:** tiếng Việt cho chuỗi giao diện và chú thích nghiệp vụ; tiếng Anh cho định danh code và commit.
- **Kiến trúc là hợp đồng:** đọc [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) trước khi viết code. Chức năng: [docs/features.md](docs/features.md).
- **AI:** chỉ gọi model qua `app.ai.run(...)`; mọi việc AI làm đi qua `control.propose(...)` (mức tự chủ → hàng chờ duyệt → nhật ký). Test dùng provider `fake`.
- **Tích hợp ngoài:** interface + driver, mặc định `mock`. Không commit khoá bí mật; `api/.env` và `web/.env.local` nằm trong `.gitignore`.
- **Backend:** Pydantic trần (200 GET/PATCH · 201 POST · 204 DELETE, `Paginated[T]`); đường dẫn cụ thể trước `/{id}`; Enum column luôn có `values_callable`; tiền là số nguyên VND.
- **Web:** ưu tiên điện thoại; token «Chàm» trong `globals.css`; không dùng `alert/confirm/prompt` của trình duyệt.
- **Test:** pytest chạy trên Postgres thật, phải xanh trước khi gộp. Không chạy `bun run build` khi `next dev` đang chạy.
- **Repo công khai:** không đưa dữ liệu khách hàng thật, số điện thoại, khoá API vào code, test hay tài liệu.
