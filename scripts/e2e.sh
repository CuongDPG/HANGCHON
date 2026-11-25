#!/usr/bin/env bash
# Playwright trên một hệ thống dựng riêng: CSDL e2e mới + migrate + dữ liệu mẫu (`app.seed --demo`) + API + worker + web.
# Không đụng máy chủ dev (API :8010 / web :3010 / CSDL `hangchon`): cổng, CSDL, hàng đợi job và thư mục build riêng.
#
#   scripts/e2e.sh                     # toàn bộ bài Playwright (gọi qua scripts/check.sh e2e)
#   scripts/e2e.sh e2e/lifecycle.spec.ts --project=mobile
#   E2E_SHOTS=1 scripts/e2e.sh         # kèm ảnh chụp ở web/test-results/shots/
#   E2E_KEEP=1 scripts/e2e.sh          # giữ máy chủ sau khi chạy để xem (tắt: kill các pid in ra)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
unset VIRTUAL_ENV
WT="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '_')"
API_PORT="${E2E_API_PORT:-8019}"
WEB_PORT="${E2E_WEB_PORT:-3019}"
DB="hangchon_e2e_${WT}"
PG_USER=hangchon
RUN="$ROOT/.logs/e2e"
mkdir -p "$RUN"

for p in "$API_PORT" "$WEB_PORT"; do
  if lsof -iTCP:"$p" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✗ Cổng $p đang bị chiếm (đặt E2E_API_PORT / E2E_WEB_PORT khác)" >&2
    exit 1
  fi
done

docker compose -f "$ROOT/docker-compose.yml" up -d --wait postgres redis >/dev/null
PG="$(docker compose -f "$ROOT/docker-compose.yml" ps -q postgres)"
docker exec "$PG" psql -U "$PG_USER" -d postgres -qc "DROP DATABASE IF EXISTS $DB WITH (FORCE)" -c "CREATE DATABASE $DB" >/dev/null

export DATABASE_URL="postgresql+asyncpg://hangchon:hangchon@localhost:5442/$DB"
export APP_ENV=dev AI_PROVIDER=fake ANTHROPIC_API_KEY= JOBS_EAGER=false JOBS_QUEUE_NAME="arq:hangchon:e2e:$WT"
# mỗi lần chạy là một hệ thống mới (CSDL mới) → xoá luôn bộ đếm giới hạn tần suất của lần trước (khoá theo hàng đợi)
docker compose -f "$ROOT/docker-compose.yml" exec -T redis sh -c \
  "redis-cli --scan --pattern 'rl:$JOBS_QUEUE_NAME:*' | xargs -r redis-cli del" >/dev/null
export SOURCES_DRIVER=mock SOCIAL_DRIVER=mock SOCIAL_CHANNEL_DRIVERS= PAYMENTS_DRIVER=mock SHIPPING_DRIVER=mock
export NOTIFY_DRIVER=mock MARKETPLACES_DRIVER=mock EINVOICE_DRIVER=mock STORAGE_DRIVER=local
export STORAGE_LOCAL_DIR="$RUN/storage" STORAGE_PUBLIC_BASE_URL="http://localhost:$WEB_PORT/api/files"
export WEB_BASE_URL="http://localhost:$WEB_PORT" API_BASE_URL="http://localhost:$API_PORT"
export CORS_ORIGINS="[\"http://localhost:$WEB_PORT\"]" COOKIE_SECURE=false CREATE_OWNER_ON_STARTUP=true
export OWNER_EMAIL="${E2E_OWNER_EMAIL:-chi@hangchon.local}" OWNER_PASSWORD="${E2E_OWNER_PASSWORD:-doimatkhau}"
rm -rf "$RUN/storage"

PIDS=()
cleanup() {
  local code=$?
  if [[ "${E2E_KEEP:-}" == "1" ]]; then
    echo "• giữ máy chủ e2e: web http://localhost:$WEB_PORT · pid ${PIDS[*]}"
    exit $code
  fi
  for pid in "${PIDS[@]}"; do
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  done
  docker exec "$PG" psql -U "$PG_USER" -d postgres -qc "DROP DATABASE IF EXISTS $DB WITH (FORCE)" >/dev/null 2>&1 || true
  rm -rf "$ROOT/web/.next-e2e"  # kiểu route sinh ra ở đây trùng với .next/ khi chạy typecheck
  exit $code
}
trap cleanup EXIT INT TERM

echo "▶ e2e: CSDL $DB + dữ liệu mẫu"
cd "$ROOT/api"
uv sync -q
uv run alembic upgrade head >"$RUN/migrate.log" 2>&1
uv run python -m app.seed --demo >"$RUN/seed.log" 2>&1 || { tail -30 "$RUN/seed.log"; exit 1; }
grep "Dữ liệu mẫu" "$RUN/seed.log" || true

echo "▶ e2e: API :$API_PORT + worker"
# hãng giao giả lên nấc mỗi 3 giây (thay vì 1 giờ) để bài vòng đời đi tới «đã giao»
export MOCK_SHIPPING_STEP_SECONDS=3
(exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >"$RUN/api.log" 2>&1) &
PIDS+=($!)
(exec uv run arq app.worker.WorkerSettings >"$RUN/worker.log" 2>&1) &
PIDS+=($!)

echo "▶ e2e: web :$WEB_PORT"
cd "$ROOT/web"
bun install --silent
# thư mục build riêng để không đụng `next dev` của máy dev (.next)
(API_ORIGIN="http://localhost:$API_PORT" NEXT_DIST_DIR=".next-e2e" exec bunx next dev -p "$WEB_PORT" >"$RUN/web.log" 2>&1) &
PIDS+=($!)

for i in $(seq 1 120); do
  if curl -fsS "http://localhost:$API_PORT/api/health" >/dev/null 2>&1 && curl -fsS -o /dev/null "http://localhost:$WEB_PORT/desk/dang-nhap" 2>/dev/null; then
    break
  fi
  if [[ $i == 120 ]]; then
    echo "✗ máy chủ e2e chưa lên (xem $RUN/*.log)" >&2
    tail -20 "$RUN/api.log" "$RUN/web.log" >&2
    exit 1
  fi
  sleep 1
done

echo "▶ e2e: Playwright"
E2E_API=1 E2E_BASE_URL="http://localhost:$WEB_PORT" bunx playwright test "$@"
