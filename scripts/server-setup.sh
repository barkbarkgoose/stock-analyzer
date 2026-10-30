#!/usr/bin/env bash
# One-time (re-runnable) setup for a fresh Ubuntu 24.04 droplet. Run from the
# repo checkout, normally /opt/stonks, as your sudo user:
#
#   sudo scripts/server-setup.sh [--domain stonks.allbarker.com] [--ssh-from CIDR] [--proxy caddy|none]
#   sudo scripts/server-setup.sh --harden-ssh      # later, after key login is confirmed
#
# Installs Docker, Caddy and firewall rules, adds swap, writes /etc/stonks/app.env
# with fresh secrets (never overwrites an existing one), installs the Caddy
# site and the backup/backfill timers. It does not deploy; run
# `sudo scripts/ops.sh deploy` afterwards.
#
# --proxy none skips Caddy and keeps 80/443 closed, for when something else
# terminates HTTPS and forwards to 127.0.0.1:8000 (e.g. Tailscale Funnel).
# --ssh-from 100.64.0.0/10 limits SSH to your Tailscale devices.
# See docs/DEPLOY.md for the DigitalOcean, Google Cloud and home setups.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="stonks.allbarker.com"
SSH_FROM=""
ADMIN_USER="${SUDO_USER:-}"
HARDEN_SSH=0
PROXY="caddy"

die() { echo "error: $*" >&2; exit 1; }
log() { echo; echo "==> $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --ssh-from) SSH_FROM="$2"; shift 2 ;;
    --admin-user) ADMIN_USER="$2"; shift 2 ;;
    --harden-ssh) HARDEN_SSH=1; shift ;;
    --proxy) PROXY="$2"; shift 2 ;;
    *) sed -n '2,12p' "$0"; exit 1 ;;
  esac
done

[[ "$PROXY" == caddy || "$PROXY" == none ]] || die "--proxy must be caddy or none"
[[ $EUID -eq 0 ]] || die "run with sudo"
[[ -n "$ADMIN_USER" && "$ADMIN_USER" != root ]] || die "run via sudo from your admin user (or pass --admin-user NAME)"
id "$ADMIN_USER" >/dev/null 2>&1 || die "user $ADMIN_USER does not exist"
grep -q 'Ubuntu' /etc/os-release || die "this script targets Ubuntu 24.04"

# --- SSH hardening (separate, deliberate step) --------------------------------
if [[ $HARDEN_SSH -eq 1 ]]; then
  keys="$(getent passwd "$ADMIN_USER" | cut -d: -f6)/.ssh/authorized_keys"
  [[ -s "$keys" ]] || die "$keys is empty; you would lock yourself out"
  cat > /etc/ssh/sshd_config.d/00-stonks.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
EOF
  sshd -t || { rm -f /etc/ssh/sshd_config.d/00-stonks.conf; die "sshd config invalid; reverted"; }
  systemctl reload ssh
  echo "SSH now accepts keys only and refuses root. Keep this session open and"
  echo "confirm 'ssh $ADMIN_USER@$DOMAIN' works from a NEW terminal before closing it."
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

log "base packages and automatic security updates"
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg git ufw unattended-upgrades python3 >/dev/null
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

log "Docker"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
fi
systemctl enable --now docker >/dev/null
docker compose version

if [[ "$PROXY" == caddy ]] && ! command -v caddy >/dev/null 2>&1; then
  log "Caddy"
  apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy >/dev/null
fi

log "swap"
if [[ -z "$(swapon --show --noheadings)" && ! -e /swapfile ]]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon --show

log "firewall (ufw)"
# Docker-published ports bypass ufw, which is why the app only binds 127.0.0.1.
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
if [[ -n "$SSH_FROM" ]]; then
  ufw allow from "$SSH_FROM" to any port 22 proto tcp >/dev/null
  # Narrowing SSH must actually close the wide-open rule from an earlier run.
  ufw delete allow OpenSSH >/dev/null 2>&1 || true
else
  ufw allow OpenSSH >/dev/null
fi
if [[ "$PROXY" == caddy ]]; then
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
else
  # Nothing public listens here; drop rules a previous caddy-mode run added.
  ufw delete allow 80/tcp >/dev/null 2>&1 || true
  ufw delete allow 443/tcp >/dev/null 2>&1 || true
fi
ufw --force enable >/dev/null
ufw status verbose

log "runtime secrets (/etc/stonks/app.env)"
install -d -m 0700 /etc/stonks
if [[ -e /etc/stonks/app.env ]]; then
  echo "exists; leaving it untouched"
else
  ( umask 0077
    python3 - "$DOMAIN" "$REPO_DIR/deploy/stonks/app.env.example" > /etc/stonks/app.env <<'PY'
import base64, os, secrets, sys
domain, template = sys.argv[1], sys.argv[2]
values = {
    "SECRET_KEY": secrets.token_urlsafe(50),
    "SETTINGS_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
    "ALLOWED_HOSTS": domain,
}
for line in open(template):
    key = line.split("=", 1)[0]
    if "=" in line and not line.startswith("#") and key in values:
        line = f"{key}={values[key]}\n"
    sys.stdout.write(line)
PY
  )
  echo "written with fresh secrets. Copy SECRET_KEY, SETTINGS_ENCRYPTION_KEY and"
  echo "POSTGRES_PASSWORD into your password manager: sudo cat /etc/stonks/app.env"
fi

if [[ "$PROXY" == caddy ]]; then
  log "Caddy site for $DOMAIN"
  tmp="$(mktemp)"
  sed "s/^stonks\.allbarker\.com {/$DOMAIN {/" "$REPO_DIR/deploy/stonks/Caddyfile" > "$tmp"
  if ! cmp -s "$tmp" /etc/caddy/Caddyfile 2>/dev/null; then
    [[ -f /etc/caddy/Caddyfile ]] && cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%Y%m%d%H%M%S)"
    install -m 0644 "$tmp" /etc/caddy/Caddyfile
  fi
  rm -f "$tmp"
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
  systemctl enable caddy >/dev/null
  systemctl reload-or-restart caddy
elif systemctl is-active --quiet caddy 2>/dev/null; then
  log "stopping Caddy (--proxy none)"
  systemctl disable --now caddy >/dev/null
fi

log "backups directory and timers"
install -d -m 2750 -o root -g "$ADMIN_USER" /var/backups/stonks
for unit in "$REPO_DIR"/deploy/stonks/systemd/*; do
  sed "s#/opt/stonks#$REPO_DIR#g" "$unit" > "/etc/systemd/system/$(basename "$unit")"
done
systemctl daemon-reload
systemctl enable --now stonks-backup.timer stonks-backfill.timer >/dev/null
systemctl list-timers 'stonks-*' --no-pager

ip="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I | cut -d' ' -f1)"
if [[ "$PROXY" == caddy ]]; then
  first="DNS: point an A record for $DOMAIN at $ip
     (check with: dig +short A $DOMAIN). Caddy fetches the certificate once it resolves."
else
  first="Publish 127.0.0.1:8000 as https://$DOMAIN, e.g.: sudo tailscale funnel --bg 8000"
fi
cat <<EOF

Setup complete. Next:
  1. $first
  2. Deploy:          sudo scripts/ops.sh deploy
  3. Create a login:  sudo scripts/ops.sh add-user you@example.com --name "Your Name"
  4. When key login works from a new terminal:  sudo scripts/server-setup.sh --harden-ssh
EOF
