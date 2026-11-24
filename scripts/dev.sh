#!/usr/bin/env bash
# Chạy Hàng Chọn trên máy: hạ tầng (Postgres 5442, Redis 6382) + API :8010 + worker + Web :3010 (nếu có web/).
#
#   ./scripts/dev.sh start            # bật tất cả (tự migrate CSDL)
#   ./scripts/dev.sh stop             # tắt API/worker/web của bản làm việc này (giữ container dùng chung)
#   ./scripts/dev.sh stop all         # tắt cả container Postgres/Redis
#   ./scripts/dev.sh logs [api|worker|web|infra|all]
#   ./scripts/dev.sh status
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/.logs"
PIDS="$ROOT/.pids"
API_PORT="${API_PORT:-8010}"
WEB_PORT="${WEB_PORT:-3010}"
mkdir -p "$LOGS" "$PIDS"
unset VIRTUAL_ENV  # tránh dùng nhầm venv của dự án khác

compose() { docker compose -f "$ROOT/docker-compose.yml" "$@"; }

port_busy() { lsof -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

is_running() { [[ -f "$PIDS/$1.pid" ]] && kill -0 "$(cat "$PIDS/$1.pid")" 2>/dev/null; }

launch() { # tên, thư mục, lệnh...
  local name="$1" dir="$2"
  shift 2
  if is_running "$name"; then
    echo "• $name đang chạy (pid $(cat "$PIDS/$name.pid"))"
    return
  fi
  # exec + chuyển hết fd vào log để tiến trình nền không giữ stdout của người gọi
  (cd "$dir" && exec nohup "$@" >"$LOGS/$name.log" 2>&1 </dev/null) &
  echo $! >"$PIDS/$name.pid"
  echo "• $name: pid $(cat "$PIDS/$name.pid"), log .logs/$name.log"
}

stop_proc() {
  local name="$1"
  if is_running "$name"; then
    local pid
    pid="$(cat "$PIDS/$name.pid")"
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
    echo "• đã tắt $name"
  fi
  rm -f "$PIDS/$name.pid"
}

start() {
  echo "▶ Hạ tầng (Postgres :5442, Redis :6382)"
  compose up -d --wait

  echo "▶ API"
  cd "$ROOT/api"
  [[ -f .env ]] || { cp .env.example .env; echo "• đã tạo api/.env từ .env.example"; }
  uv sync -q
  uv run alembic upgrade head
  if port_busy "$API_PORT" && ! is_running api; then
    echo "✗ Cổng $API_PORT đang bị chiếm" >&2
    exit 1
  fi
  launch api "$ROOT/api" uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$API_PORT"
  launch worker "$ROOT/api" uv run arq app.worker.WorkerSettings --watch app

  if [[ -f "$ROOT/web/package.json" ]]; then
    echo "▶ Web"
    (cd "$ROOT/web" && bun install --silent)
    launch web "$ROOT/web" env PORT="$WEB_PORT" bun dev
  else
    echo "• chưa có web/, bỏ qua"
  fi
  echo
  echo "API  http://localhost:$API_PORT/docs"
  [[ -f "$ROOT/web/package.json" ]] && echo "Web  http://localhost:$WEB_PORT"
  return 0
}

stop() {
  stop_proc web
  stop_proc worker
  stop_proc api
  if [[ "${1:-}" == "all" ]]; then
    compose stop
  fi
}

logs() {
  case "${1:-all}" in
    api | worker | web) tail -n 100 -f "$LOGS/$1.log" ;;
    infra) compose logs -f --tail 100 ;;
    all) tail -n 50 -f "$LOGS"/*.log ;;
    *) echo "logs [api|worker|web|infra|all]" >&2; exit 2 ;;
  esac
}

status() {
  compose ps
  for n in api worker web; do
    if is_running "$n"; then echo "• $n: đang chạy (pid $(cat "$PIDS/$n.pid"))"; else echo "• $n: tắt"; fi
  done
}

case "${1:-}" in
  start) start ;;
  stop) stop "${2:-}" ;;
  restart) stop; start ;;
  logs) logs "${2:-all}" ;;
  status) status ;;
  *) echo "Dùng: $0 start | stop [all] | restart | logs [api|worker|web|infra|all] | status" >&2; exit 2 ;;
esac
