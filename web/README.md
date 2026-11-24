# web — Hàng Chọn (Next.js)

Website cho khách (`/`) và bàn làm việc PWA của chị (`/desk`). Hướng dẫn đầy đủ: [docs/frontend-guide.md](../docs/frontend-guide.md).

```bash
bun install
bun dev              # http://localhost:3010 (API: API_ORIGIN, mặc định http://localhost:8010)
bun run typecheck    # next typegen + tsc
bun run lint
bun run test         # vitest
bun run build        # không chạy khi `bun dev` đang chạy
bun run e2e          # Playwright (tự bật dev server ở 3010 nếu chưa có); E2E_SHOTS=1 để chụp ảnh
```

Trang trưng bày component: http://localhost:3010/desk/kit
