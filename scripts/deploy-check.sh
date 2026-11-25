#!/usr/bin/env bash
# Thử bản chạy thật trên máy: build 2 image, dựng docker-compose.prod.yml với env thử (project + tên container riêng,
# cổng lạ), chờ healthy, kiểm API/web/đăng nhập/sao lưu, rồi dọn sạch (down -v + xoá image thử).
#
#   scripts/deploy-check.sh                  # mặc định web :3900, api :8900
#   WEB_PORT=3901 API_PORT=8901 scripts/deploy-check.sh
#   KEEP=1 scripts/deploy-check.sh           # giữ container lại để xem (tự dọn sau bằng lệnh in ra cuối)
#   KEEP_IMAGES=1 scripts/deploy-check.sh    # dọn container/volume nhưng giữ image (lần sau build nhanh hơn)
#   NO_CACHE=1 scripts/deploy-check.sh       # build lại từ đầu (đo thời gian build thật)
#
# Không đụng bộ container dev (`hangchon`, Postgres 5442/Redis 6382) hay API 8010/Web 3010: Postgres/Redis của
# bản thử không mở cổng ra máy, chỉ api và web mở trên 127.0.0.1.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="${PROJECT:-hangchon-deploycheck}"
PREFIX="${CONTAINER_PREFIX:-hangchon-deploycheck}"
WEB_PORT="${WEB_PORT:-3900}"
API_PORT="${API_PORT:-8900}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"
OWNER_EMAIL="chi@deploycheck.local"
OWNER_PASSWORD="deploycheck-$(openssl rand -hex 6)"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/hangchon-deploycheck.XXXXXX")"
ENV_FILE="$TMP/check.env"
OVERRIDE="$TMP/ports.yml"
JAR="$TMP/cookies.txt"

say() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
ok() { printf '  ✓ %s\n' "$*"; }
die() { printf '  ✗ %s\n' "$*" >&2; exit 1; }

compose() {
  docker compose -p "$PROJECT" -f "$ROOT/docker-compose.prod.yml" -f "$OVERRIDE" --env-file "$ENV_FILE" "$@"
}

cleanup() {
  local code=$?
  if [[ "${KEEP:-}" == "1" ]]; then
    echo
    echo "Giữ lại bản thử. Dọn bằng:"
    echo "  docker compose -p $PROJECT -f docker-compose.prod.yml -f $OVERRIDE --env-file $ENV_FILE down -v --remove-orphans"
    return
  fi
  if (( code != 0 )); then
    say "Lỗi — log 80 dòng cuối"
    compose ps -a || true
    compose logs --no-color --tail 80 || true
  fi
  say "Dọn bản thử"
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  if [[ "${KEEP_IMAGES:-}" != "1" ]]; then
    docker image rm -f "$PREFIX-api:latest" "$PREFIX-web:latest" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
  ok "đã down -v, xoá env thử"
  exit "$code"
}
trap cleanup EXIT

port_busy() { lsof -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

expect_status() { # mô tả, mã mong đợi, curl args...
  local what="$1" want="$2"
  shift 2
  local got
  got="$(curl -sS -o "$TMP/body" -w '%{http_code}' --max-time 30 "$@")" || got="000"
  if [[ "$got" != "$want" ]]; then
    echo "    phản hồi: $(head -c 400 "$TMP/body" 2>/dev/null)" >&2
    die "$what: HTTP $got (cần $want)"
  fi
  ok "$what: HTTP $got"
}

# ---- chuẩn bị ------------------------------------------------------------------------------------------------------
say "Chuẩn bị (project $PROJECT, web :$WEB_PORT, api :$API_PORT)"
command -v docker >/dev/null || die "cần docker"
command -v curl >/dev/null || die "cần curl"
for p in "$WEB_PORT" "$API_PORT"; do
  port_busy "$p" && die "cổng $p đang bị chiếm — đặt WEB_PORT/API_PORT khác"
done

cat >"$ENV_FILE" <<EOF
CONTAINER_PREFIX=$PREFIX
SITE_URL=http://localhost:$WEB_PORT
POSTGRES_PASSWORD=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)
SECRETS_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
HOOKS_MOCK_SECRET=$(openssl rand -hex 16)
OWNER_EMAIL=$OWNER_EMAIL
OWNER_PASSWORD=$OWNER_PASSWORD
# bản thử chạy HTTP thường → cookie không đặt Secure
COOKIE_SECURE=false
AI_PROVIDER=fake
EOF

cat >"$OVERRIDE" <<EOF
services:
  api:
    ports: ["127.0.0.1:$API_PORT:8000"]
  web:
    ports: ["127.0.0.1:$WEB_PORT:3000"]
EOF
ok "env thử ở $TMP (khoá ngẫu nhiên, xoá khi xong)"

# ---- build ---------------------------------------------------------------------------------------------------------
say "Build image"
t0=$(date +%s)
if [[ "${NO_CACHE:-}" == "1" ]]; then
  compose build --no-cache --pull api web
else
  compose build api web
fi
t1=$(date +%s)
ok "build xong trong $((t1 - t0))s"
for img in "$PREFIX-api:latest" "$PREFIX-web:latest"; do
  size=$(docker image inspect "$img" --format '{{.Size}}')
  ok "$img: $((size / 1024 / 1024)) MB"
done

# ---- dựng ----------------------------------------------------------------------------------------------------------
say "Dựng compose (chờ healthy, tối đa ${WAIT_TIMEOUT}s)"
t2=$(date +%s)
compose up -d --no-build --wait --wait-timeout "$WAIT_TIMEOUT"
ok "mọi dịch vụ healthy sau $(($(date +%s) - t2))s"
compose ps --format 'table {{.Name}}\t{{.Status}}'

# ---- kiểm ----------------------------------------------------------------------------------------------------------
say "Kiểm API"
expect_status "GET /api/health (API trực tiếp)" 200 "http://127.0.0.1:$API_PORT/api/health"
grep -q '"ok"' "$TMP/body" || die "/api/health không trả status ok"
heads=$(docker exec "$PREFIX-api" alembic heads 2>/dev/null | grep -c '(head)')
[[ "$heads" == 1 ]] || die "alembic heads = $heads"
current=$(docker exec "$PREFIX-api" alembic current 2>/dev/null | grep -c '(head)')
[[ "$current" == 1 ]] || die "CSDL chưa ở head"
ok "alembic: 1 head, CSDL đã migrate tới head"
[[ "$(docker exec "$PREFIX-api" id -u)" != 0 ]] || die "API chạy bằng root"
ok "API chạy bằng user $(docker exec "$PREFIX-api" id -un)"
docker exec "$PREFIX-api" sh -c 'pg_dump --version && ffmpeg -hide_banner -version | head -n1' | sed 's/^/  · /'

say "Kiểm web"
expect_status "GET / (trang chủ)" 200 "http://127.0.0.1:$WEB_PORT/"
grep -qi '<html' "$TMP/body" || die "trang chủ không phải HTML"
expect_status "GET /robots.txt" 200 "http://127.0.0.1:$WEB_PORT/robots.txt"
grep -q "http://localhost:$WEB_PORT/sitemap.xml" "$TMP/body" || die "robots.txt không mang SITE_URL"
ok "robots.txt mang SITE_URL"
expect_status "GET /api/health qua web (rewrite → API_ORIGIN)" 200 "http://127.0.0.1:$WEB_PORT/api/health"

say "Đăng nhập owner (qua web, cùng origin)"
expect_status "POST /api/desk/auth/login" 200 -c "$JAR" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$OWNER_PASSWORD\"}" "http://127.0.0.1:$WEB_PORT/api/desk/auth/login"
grep -q '"owner"' "$TMP/body" || die "đăng nhập không trả vai trò owner"
expect_status "GET /api/desk/auth/me (cookie phiên)" 200 -b "$JAR" "http://127.0.0.1:$WEB_PORT/api/desk/auth/me"
expect_status "GET /api/desk/auth/me (không cookie)" 401 "http://127.0.0.1:$WEB_PORT/api/desk/auth/me"

say "Sao lưu (pg_dump trong image khớp bản Postgres)"
expect_status "POST /api/desk/finance/backups" 201 -b "$JAR" -X POST "http://127.0.0.1:$API_PORT/api/desk/finance/backups"
grep -q '"status":"succeeded"' "$TMP/body" || die "sao lưu không thành công: $(head -c 400 "$TMP/body")"
ok "sao lưu thành công, tệp nằm trong volume /data/storage"

say "Worker"
docker exec "$PREFIX-worker" arq --check app.worker.WorkerSettings >/dev/null 2>&1 || die "worker không báo khoẻ"
ok "arq --check: worker đang chạy"

say "✓ deploy-check xanh (build $((t1 - t0))s)"
