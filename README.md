# Hàng Chọn

Nền tảng bán hàng cá nhân: một người chọn hàng, AI làm phần còn lại và chờ người đó duyệt.

- **Website cho khách** (`/`): kệ hàng đã chọn, hồ sơ chọn của từng món, mở bán theo đợt, đặt hàng, theo dõi đơn.
- **Bàn làm việc** (`/desk`): săn hàng, thẩm định, bàn chọn, nội dung và lịch đăng, hộp thư, đơn hàng, giám sát AI.

Tài liệu: [kiến trúc](docs/ARCHITECTURE.md) · [danh mục chức năng](docs/features.md) · [mô hình dữ liệu](docs/data-model.md) ·
[hướng dẫn backend](docs/backend-guide.md) · [hướng dẫn web](docs/frontend-guide.md) ·
[sổ trạng thái chức năng](docs/status.md) · [triển khai lên Dokploy](docs/deployment.md) ·
[bản thiết kế và wireframe](docs/design/ban-thiet-ke.html).

## Chạy trên máy

Cần Docker, [uv](https://docs.astral.sh/uv/), [bun](https://bun.sh).

```bash
cp api/.env.example api/.env        # điền khoá khi có; để trống vẫn chạy được với AI giả và tích hợp giả
./scripts/dev.sh start              # API http://localhost:8010 · Web http://localhost:3010
```

Dữ liệu mẫu (một câu chuyện chung cho mọi module, chạy một lần; ở `APP_ENV=prod` lệnh tự từ chối):

```bash
cd api && uv run python -m app.seed --demo
```

Kiểm trước khi gộp:

```bash
scripts/check.sh api                # ruff + toàn bộ pytest (Postgres thật)
scripts/check.sh web                # typecheck + eslint + vitest
scripts/check.sh e2e                # Playwright trên hệ thống dựng riêng (CSDL e2e + dữ liệu mẫu); đổi cổng bằng E2E_API_PORT / E2E_WEB_PORT
```
