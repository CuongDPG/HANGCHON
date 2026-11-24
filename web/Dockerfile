# syntax=docker/dockerfile:1
# Website + bàn làm việc của Hàng Chọn (Next.js 16, cài gói bằng bun, chạy bản standalone bằng Node).
#
#   docker build -t hangchon-web --build-arg API_ORIGIN=http://hangchon-api:8000 --build-arg SITE_URL=https://example.vn ./web
#
# API_ORIGIN và SITE_URL cần CÓ LÚC BUILD: rewrites /api/* → API_ORIGIN được ghi cứng vào bản build; sitemap, robots,
# JSON-LD được dựng sẵn với SITE_URL. Lúc chạy truyền lại đúng hai giá trị đó (code phía máy chủ đọc lại từ env).

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
ARG SITE_URL=http://localhost:3000
ENV API_ORIGIN=${API_ORIGIN} \
    SITE_URL=${SITE_URL} \
    NEXT_PUBLIC_SITE_URL=${SITE_URL} \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
# next.config.ts chưa đặt `output`; NEXT_PRIVATE_STANDALONE=1 làm Next mặc định output "standalone"
# (đặt `output: "standalone"` trong next.config.ts thì bỏ dòng này được).
ENV NEXT_PRIVATE_STANDALONE=1
COPY . .
RUN bun run build \
 && test -f .next/standalone/server.js

# ---- chạy ---------------------------------------------------------------------------------------------------------
FROM node:${NODE_VERSION}-bookworm-slim AS runtime
ARG API_ORIGIN=http://hangchon-api:8000
ARG SITE_URL=http://localhost:3000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    API_ORIGIN=${API_ORIGIN} \
    SITE_URL=${SITE_URL} \
    NEXT_PUBLIC_SITE_URL=${SITE_URL}
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public

USER node
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/robots.txt').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
