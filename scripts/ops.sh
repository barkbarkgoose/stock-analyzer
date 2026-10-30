#!/usr/bin/env bash
# Day-to-day operations on the production server. Run from the repo checkout
# (/opt/stonks) with sudo:
#
#   sudo scripts/ops.sh deploy              pull, back up, build, migrate, restart, health check
#   sudo scripts/ops.sh status              containers + health
#   sudo scripts/ops.sh add-user EMAIL --name "Name" [--admin]
#   sudo scripts/ops.sh backup              database dump to /var/backups/stonks
#   sudo scripts/ops.sh restore FILE.dump   replace the database with a dump (asks first)
#   sudo scripts/ops.sh rollback            restart on the previous image (code only)
#   sudo scripts/ops.sh backfill            fetch 5m history for the watchlist (timer runs this)
#   sudo scripts/ops.sh logs [service]      follow logs (app, paper, db)
#   sudo scripts/ops.sh manage ARGS...      any manage.py command, e.g. changepassword EMAIL
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${STONKS_ENV_FILE:-/etc/stonks/app.env}"
STATE_DIR="/var/lib/stonks"
BACKUP_DIR="${STONKS_BACKUP_DIR:-/var/backups/stonks}"
BACKUP_KEEP="${STONKS_BACKUP_KEEP:-14}"
LOCK_FILE="/run/lock/stonks-ops.lock"

die() { echo "error: $*" >&2; exit 1; }
log() { echo "==> $*"; }

[[ $EUID -eq 0 ]] || die "run with sudo (Docker access is root-only on this host)"
[[ -r "$ENV_FILE" ]] || die "$ENV_FILE not found; run scripts/server-setup.sh first"

compose() {
  docker compose --project-directory "$REPO_DIR" -f "$REPO_DIR/compose.production.yaml" \
    --env-file "$ENV_FILE" "$@"
}

# One mutating operation at a time (deploy, backup, restore, backfill).
take_lock() {
  exec 9>"$LOCK_FILE"
  flock -w "${1:-900}" 9 || die "another stonks operation is still running"
}

wait_healthy() {
  local tries=40
  log "waiting for the app to report healthy"
  until curl -fsS --max-time 5 http://127.0.0.1:8000/health/ >/dev/null 2>&1; do
    tries=$((tries - 1))
    [[ $tries -gt 0 ]] || { compose logs --tail=60 app >&2; die "app did not become healthy"; }
    sleep 3
  done
  log "healthy"
}

# The checkout belongs to the admin user (who holds the GitHub deploy key);
# git refuses to run as root in another user's repo, so run it as the owner.
git_as_owner() {
  sudo -u "$(stat -c %U "$REPO_DIR")" git -C "$REPO_DIR" "$@"
}

db_running() {
  [[ -n "$(compose ps --status running -q db 2>/dev/null)" ]]
}

do_backup() {
  db_running || { log "database is not running; skipping backup"; return 0; }
  # setgid dir: dumps inherit the admin group so they can be scp'd off the box.
  [[ -d "$BACKUP_DIR" ]] || install -d -m 2750 "$BACKUP_DIR"
  local file="$BACKUP_DIR/stonks-$(date -u +%Y%m%dT%H%M%SZ)-${1:-manual}.dump"
  log "dumping database to $file"
  ( umask 0137; compose exec -T db pg_dump -U stonks -d stonks -Fc > "$file.partial" )
  # A dump that pg_restore cannot list is not a backup.
  compose exec -T db pg_restore --list < "$file.partial" >/dev/null \
    || { rm -f "$file.partial"; die "backup failed verification"; }
  mv "$file.partial" "$file"
  ln -sfn "$(basename "$file")" "$BACKUP_DIR/latest.dump"
  # Keep the newest $BACKUP_KEEP dumps.
  ls -1t "$BACKUP_DIR"/stonks-*.dump 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | xargs -r rm -f
  log "backup ok ($(du -h "$file" | cut -f1))"
}

cmd_deploy() {
  take_lock
  cd "$REPO_DIR"
  if [[ "${1:-}" != "--no-pull" ]]; then
    log "pulling latest code"
    git_as_owner pull --ff-only
  fi
  local rev; rev="$(git_as_owner rev-parse --short HEAD)"

  log "building image stonks-app:$rev"
  docker build -t "stonks-app:$rev" "$REPO_DIR"

  do_backup "predeploy-$rev"

  install -d -m 0755 "$STATE_DIR"
  local previous=""
  [[ -f "$STATE_DIR/current" ]] && previous="$(cat "$STATE_DIR/current")"

  compose up -d db
  log "running migrations"
  APP_TAG="$rev" compose run --rm --no-deps app python manage.py migrate --noinput

  docker tag "stonks-app:$rev" stonks-app:current
  compose up -d --remove-orphans app paper
  wait_healthy

  if [[ -n "$previous" && "$previous" != "$rev" ]]; then
    echo "$previous" > "$STATE_DIR/previous"
  fi
  echo "$rev" > "$STATE_DIR/current"

  # Keep the current and previous images; drop older releases and build cache.
  local keep_prev; keep_prev="$(cat "$STATE_DIR/previous" 2>/dev/null || true)"
  docker images --format '{{.Repository}}:{{.Tag}}' stonks-app \
    | grep -vE ":(current|$rev${keep_prev:+|$keep_prev})$" | xargs -r docker rmi >/dev/null 2>&1 || true
  docker builder prune -f --filter until=168h >/dev/null 2>&1 || true
  log "deployed $rev"
}

cmd_rollback() {
  take_lock
  local previous; previous="$(cat "$STATE_DIR/previous" 2>/dev/null || true)"
  [[ -n "$previous" ]] || die "no previous release recorded"
  docker image inspect "stonks-app:$previous" >/dev/null 2>&1 || die "image stonks-app:$previous is gone"
  echo "Rolling back code to $previous. Database migrations are NOT reversed:"
  echo "only do this if the newer release did not change the schema."
  read -r -p "Type 'rollback' to continue: " answer
  [[ "$answer" == "rollback" ]] || die "cancelled"
  docker tag "stonks-app:$previous" stonks-app:current
  compose up -d app paper
  wait_healthy
  cat "$STATE_DIR/current" > "$STATE_DIR/previous"
  echo "$previous" > "$STATE_DIR/current"
  log "now running $previous"
}

cmd_restore() {
  local file="${1:-}"
  [[ -f "$file" ]] || die "usage: ops.sh restore /var/backups/stonks/FILE.dump"
  # Resolve now: the safety backup below re-points latest.dump at itself.
  file="$(readlink -f "$file")"
  take_lock
  echo "This REPLACES the live database with $file."
  read -r -p "Type 'restore' to continue: " answer
  [[ "$answer" == "restore" ]] || die "cancelled"
  do_backup "before-restore"
  compose stop app paper
  compose exec -T db pg_restore -U stonks -d stonks --clean --if-exists --no-owner --exit-on-error < "$file"
  compose up -d app paper
  wait_healthy
  log "restored $file"
}

cmd_backfill() {
  take_lock 3600
  compose exec -T app python manage.py backfill_intraday --watchlist --days 58
}

case "${1:-}" in
  deploy) shift; cmd_deploy "$@" ;;
  status) compose ps; curl -fsS --max-time 5 http://127.0.0.1:8000/health/ && echo ;;
  backup) take_lock; do_backup "${2:-manual}" ;;
  restore) shift; cmd_restore "$@" ;;
  rollback) cmd_rollback ;;
  backfill) cmd_backfill ;;
  add-user) shift; compose exec app python manage.py add_user "$@" ;;
  manage) shift; compose exec app python manage.py "$@" ;;
  logs) shift; compose logs -f --tail=200 "${@:-app}" ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
