#!/usr/bin/env bash
# Chuẩn bị một máy chủ Ubuntu 24.04 (arm64 hoặc amd64) để chạy Hàng Chọn bằng image dựng sẵn. Chạy lại bao nhiêu lần
# cũng được (idempotent). Chạy bằng root:
#
#   sudo DEPLOY_PUBKEY="ssh-ed25519 AAAA… github-deploy" bash server-bootstrap.sh
#
# Biến tuỳ chọn:
#   DEPLOY_USER=deploy         user GitHub Actions SSH vào (thuộc nhóm docker)
#   DEPLOY_PATH=/opt/hangchon  thư mục chứa .env + tệp compose
#   DEPLOY_PUBKEY=…            khoá công khai thêm vào ~DEPLOY_USER/.ssh/authorized_keys (khoá riêng để ở GitHub secret)
#   SWAP_SIZE=2G               swapfile (/swapfile); máy nhỏ 1–2 GB RAM nên 2G–4G. 0 = không tạo
#   SSH_PORT=22                cổng SSH mở trên ufw
#   OPEN_WEB_PORTS=0           1 = mở thêm 80/443 (chỉ khi KHÔNG dùng Cloudflare Tunnel)
#
# Làm: Docker Engine + compose plugin (kho chính thức của Docker), xoay log Docker, user deploy, swapfile, ufw (chặn mọi
# cổng vào trừ SSH), unattended-upgrades. Không đổi cấu hình sshd.
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/hangchon}"
DEPLOY_PUBKEY="${DEPLOY_PUBKEY:-}"
SWAP_SIZE="${SWAP_SIZE:-2G}"
SSH_PORT="${SSH_PORT:-22}"
OPEN_WEB_PORTS="${OPEN_WEB_PORTS:-0}"

say() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "chạy bằng root (sudo)" >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu ]] || echo "cảnh báo: script viết cho Ubuntu 24.04, máy này là $PRETTY_NAME" >&2
export DEBIAN_FRONTEND=noninteractive

say "Gói nền"
apt-get update -q
apt-get install -y -q ca-certificates curl ufw unattended-upgrades

say "Docker Engine + compose plugin ($(dpkg --print-architecture))"
install -m 0755 -d /etc/apt/keyrings
if [[ ! -s /etc/apt/keyrings/docker.asc ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
  >/etc/apt/sources.list.d/docker.list
apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
if [[ ! -f /etc/docker/daemon.json ]]; then
  # đĩa nhỏ: giữ tối đa 3 × 10 MB log mỗi container
  printf '{\n  "log-driver": "json-file",\n  "log-opts": { "max-size": "10m", "max-file": "3" }\n}\n' >/etc/docker/daemon.json
  systemctl restart docker
fi
systemctl enable --now docker
docker --version
docker compose version

say "User $DEPLOY_USER (nhóm docker) và $DEPLOY_PATH"
id "$DEPLOY_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
home="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$home/.ssh"
touch "$home/.ssh/authorized_keys"
if [[ -n "$DEPLOY_PUBKEY" ]] && ! grep -qxF "$DEPLOY_PUBKEY" "$home/.ssh/authorized_keys"; then
  echo "$DEPLOY_PUBKEY" >>"$home/.ssh/authorized_keys"
  echo "  đã thêm khoá công khai"
fi
chown "$DEPLOY_USER:$DEPLOY_USER" "$home/.ssh/authorized_keys"
chmod 600 "$home/.ssh/authorized_keys"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_PATH"

say "Swap ($SWAP_SIZE)"
if [[ "$SWAP_SIZE" == 0 ]]; then
  echo "  bỏ qua"
elif swapon --show=NAME --noheadings | grep -qx /swapfile; then
  echo "  /swapfile đã bật"
else
  [[ -f /swapfile ]] || { fallocate -l "$SWAP_SIZE" /swapfile || dd if=/dev/zero of=/swapfile bs=1M count="$(numfmt --from=iec "$SWAP_SIZE" | awk '{print int($1/1048576)}')"; }
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi
echo 'vm.swappiness=10' >/etc/sysctl.d/90-hangchon-swap.conf
sysctl -q -p /etc/sysctl.d/90-hangchon-swap.conf
swapon --show

say "Tường lửa ufw"
# Lưu ý: cổng Docker publish (ports:) đi vòng qua ufw. Bộ compose máy chủ không publish cổng nào.
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "$SSH_PORT/tcp" >/dev/null
if [[ "$OPEN_WEB_PORTS" == 1 ]]; then
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
fi
ufw --force enable >/dev/null
ufw status verbose

say "Tự cập nhật bản vá bảo mật"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades >/dev/null

say "✓ xong. Bước tiếp: đặt $DEPLOY_PATH/.env (chủ $DEPLOY_USER, chmod 600) rồi chạy GitHub Actions (docs/deployment.md)"
