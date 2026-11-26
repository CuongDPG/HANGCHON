# syntax=docker/dockerfile:1
# Website + bàn làm việc của Hàng Chọn (Next.js 16, cài gói bằng bun, chạy bản standalone bằng Node).
#
#   docker build -t hangchon-web ./web                                   # API ở http://hangchon-api:8000
#   docker build -t hangchon-web --build-arg API_ORIGIN=http://khac-api:8000 ./web
#
# SITE_URL chỉ cần LÚC CHẠY (env của container): sitemap, robots, JSON-LD, Open Graph tính theo request. Bản build không
# mang tên miền nào — một image (GHCR) dùng cho mọi tên miền; bước build tự kiểm điều đó (xem RUN bên dưới).
# API_ORIGIN thì CÓ LÚC BUILD: rewrites /api/* → API_ORIGIN được Next ghi cứng vào routes-manifest khi `next build`
# (bản standalone không đọc lại next.config lúc chạy). Mặc định http://hangchon-api:8000 = tên container API ở prod;
# code phía máy chủ (Server Component, /feed.xml) vẫn đọc API_ORIGIN từ env lúc chạy.

ARG BUN_VERSION=1.3.14
ARG NODE_VERSION=24

FROM oven/bun:${BUN_VERSION}-slim AS bun

# ---- cài gói ------------------------------------------------------------------------------------------------------
FROM node:${NODE_VERSION}-bookworm-slim AS deps
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /app
COPY package.json bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

# ---- build --------------------------------------------------------------------------------------------------------
FROM deps AS build
ARG API_ORIGIN=http://hangchon-api:8000
# SITE_URL lúc build là giá trị canh gác: nếu nó lọt vào bản build (trang dựng sẵn, bundle) thì build dừng.
ENV API_ORIGIN=${API_ORIGIN} \
    SITE_URL=http://site-url-not-set-at-build.invalid \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
# next.config.ts chưa đặt `output`; NEXT_PRIVATE_STANDALONE=1 làm Next mặc định output "standalone"
# (đặt `output: "standalone"` trong next.config.ts thì bỏ dòng này được).
ENV NEXT_PRIVATE_STANDALONE=1
COPY . .
RUN bun run build \
 && test -f .next/standalone/server.js \
 && if grep -rlF "site-url-not-set-at-build.invalid" .next/standalone .next/static; then \
      echo "SITE_URL lúc build lọt vào bản build (tệp ở trên) — trang đó phải tính theo request" >&2; exit 1; \
    fi

# ---- chạy ---------------------------------------------------------------------------------------------------------
FROM node:${NODE_VERSION}-bookworm-slim AS runtime
ARG API_ORIGIN=http://hangchon-api:8000
# SITE_URL không có mặc định ở đây: compose truyền vào (docker-compose.prod.yml, bắt buộc).
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    API_ORIGIN=${API_ORIGIN}
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public

USER node
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/robots.txt').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
