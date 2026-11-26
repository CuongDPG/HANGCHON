#!/usr/bin/env bash
# Chạy TRÊN MÁY CHỦ RIÊNG, trong thư mục deploy (mặc định /opt/hangchon, cạnh .env + hai tệp compose).
# GitHub Actions chép tệp này lên rồi gọi sau mỗi lần dựng image; chạy tay được để quay về bản cũ:
#
#   ./server-deploy.sh sha-1a2b3c4      # ghim IMAGE_TAG trong .env → pull → up -d → chờ healthy
#   ./server-deploy.sh latest
#
# Lỗi (dịch vụ không healthy, API không trả /api/health) → thoát mã ≠ 0 và in log; KHÔNG tự quay về bản cũ
# (API có thể đã migrate CSDL). Lịch sử bản đã ghim: .deploy-history.
set -euo pipefail

cd "$(dirname "$0")"
TAG="${1:?Dùng: $0 <image tag, vd sha-1a2b3c4>}"
[[ "$TAG" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "tag không hợp lệ: $TAG" >&2; exit 2; }
[[ -f .env ]] || { echo "thiếu $(pwd)/.env (biến môi trường, xem docs/deployment.md)" >&2; exit 1; }

compose() { docker compose -f docker-compose.prod.yml -f docker-compose.server.yml "$@"; }
prefix="$(grep -E '^CONTAINER_PREFIX=' .env | tail -n1 | cut -d= -f2- || true)"
api="${prefix:-hangchon}-api"

prev="$(grep -E '^IMAGE_TAG=' .env | tail -n1 | cut -d= -f2- || true)"
tmp="$(mktemp .env.XXXXXX)"
grep -vE '^IMAGE_TAG=' .env >"$tmp" || true
echo "IMAGE_TAG=$TAG" >>"$tmp"
chmod --reference=.env "$tmp" 2>/dev/null || chmod 600 "$tmp"
mv "$tmp" .env
echo "$(date -u +%FT%TZ) ${prev:-<trống>} -> $TAG" >>.deploy-history
echo "▶ IMAGE_TAG: ${prev:-<trống>} → $TAG"

echo "▶ pull"
compose pull --quiet
echo "▶ up -d (chờ healthy, tối đa 420s)"
if ! compose up -d --remove-orphans --wait --wait-timeout 420; then
  compose ps -a || true
  compose logs --no-color --tail 80 api worker web || true
  echo "✗ có dịch vụ không healthy sau khi deploy $TAG (bản trước: ${prev:-<trống>})" >&2
  exit 1
fi
docker exec "$api" python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5); sys.exit(0 if b'ok' in r.read() else 1)" \
  || { echo "✗ /api/health không trả ok" >&2; exit 1; }
compose ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}'
docker image prune -f >/dev/null || true
echo "✓ deploy $TAG xanh"
