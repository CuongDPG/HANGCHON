# Hàng Chọn

Nền tảng bán hàng cá nhân: một người chọn hàng, AI làm phần còn lại và chờ người đó duyệt.

- **Website cho khách** (`/`): kệ hàng đã chọn, hồ sơ chọn của từng món, mở bán theo đợt, đặt hàng, theo dõi đơn.
- **Bàn làm việc** (`/desk`): săn hàng, thẩm định, bàn chọn, nội dung và lịch đăng, hộp thư, đơn hàng, giám sát AI.

Tài liệu: [kiến trúc](docs/ARCHITECTURE.md) · [danh mục chức năng](docs/features.md) · [bản thiết kế và wireframe](docs/design/ban-thiet-ke.html).

## Chạy trên máy

Cần Docker, [uv](https://docs.astral.sh/uv/), [bun](https://bun.sh).

```bash
cp api/.env.example api/.env        # điền khoá khi có; để trống vẫn chạy được với AI giả và tích hợp giả
./scripts/dev.sh start              # API http://localhost:8010 · Web http://localhost:3010
```
