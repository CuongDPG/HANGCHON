#!/usr/bin/env bash
# Cổng chất lượng trước khi gộp.
#
#   scripts/check.sh api    ruff (lint + format) + TOÀN BỘ pytest (Postgres thật, CSDL test theo tên worktree)
#   scripts/check.sh web    bun run typecheck && bun run lint && bun run test
#   scripts/check.sh e2e    bun run e2e (Playwright)
#   scripts/check.sh        api + web
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
unset VIRTUAL_ENV

check_api() {
  echo "▶ api: hạ tầng"
  docker compose -f "$ROOT/docker-compose.yml" up -d --wait postgres redis >/dev/null
  cd "$ROOT/api"
  uv sync -q
  echo "▶ api: ruff"
  uv run ruff check .
  uv run ruff format --check .
  echo "▶ api: pytest"
  uv run pytest -p no:cacheprovider "$@"
}

check_web() {
  if [[ ! -f "$ROOT/web/package.json" ]]; then
    echo "• chưa có web/, bỏ qua"
    return 0
  fi
  cd "$ROOT/web"
  bun install --silent
  echo "▶ web: typecheck"
  bun run typecheck
  echo "▶ web: lint"
  bun run lint
  echo "▶ web: test"
  bun run test
}

check_e2e() {
  cd "$ROOT/web"
  bun run e2e
}

target="${1:-all}"
shift || true
case "$target" in
  api) check_api "$@" ;;
  web) check_web ;;
  e2e) check_e2e ;;
  all) (check_api) && (check_web) ;;
  *) echo "Dùng: $0 [api|web|e2e]" >&2; exit 2 ;;
esac
echo "✓ $target xanh"
