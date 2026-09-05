#!/bin/bash
# On-box watchdog for the two ways the box dies with nobody watching
# (docker-compose.yml's own comment: disk-fill is "the most likely way this app
# dies unattended"; and `restart: unless-stopped` never acts on a hung-but-alive
# container, only on process exit):
#
#   1. Root volume > DISK_THRESHOLD% used  ->  Discord webhook alert
#   2. Any compose service reporting unhealthy  ->  restart it + Discord alert
#
# Installed by infra/deploy.sh as a systemd timer (vac-watchdog.timer, every
# 5 minutes). Run by hand: sudo /opt/vac/infra/disk-watch.sh
#
# The webhook comes from $DISCORD_WEBHOOK_URL or backend/.env (which
# infra/deploy.sh refreshes from SSM /vac/* on every deploy) — the same
# convention backend/app/alerts.py uses. No webhook = the restart still
# happens, silently.
set -uo pipefail   # deliberately no -e: one failed check must not skip the others

APP_DIR=${APP_DIR:-/opt/vac}
DISK_THRESHOLD=${DISK_THRESHOLD:-85}
ALERT_STAMP=${ALERT_STAMP:-/var/run/vac-disk-alert.stamp}
REALERT_SECONDS=${REALERT_SECONDS:-21600}   # re-alert on a still-full disk every 6 h, not every 5 min
cd "$APP_DIR" || exit 1

if [ -z "${DISCORD_WEBHOOK_URL:-}" ] && [ -f backend/.env ]; then
  DISCORD_WEBHOOK_URL=$(grep '^DISCORD_WEBHOOK_URL=' backend/.env | cut -d= -f2- || true)
fi

notify() {
  # Best-effort, never fails the script. Message only — no player data ever
  # flows through here.
  [ -n "${DISCORD_WEBHOOK_URL:-}" ] || return 0
  curl -fsS -m 10 -H 'Content-Type: application/json' \
    -d "{\"content\": \"[vac-watchdog] $1\"}" "$DISCORD_WEBHOOK_URL" >/dev/null 2>&1 || true
}

# ---- 1. Disk usage on the root volume
USED=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ -n "$USED" ] && [ "$USED" -ge "$DISK_THRESHOLD" ]; then
  NOW=$(date +%s)
  LAST=0
  [ -f "$ALERT_STAMP" ] && LAST=$(stat -c %Y "$ALERT_STAMP" 2>/dev/null || echo 0)
  if [ $((NOW - LAST)) -ge "$REALERT_SECONDS" ]; then
    echo "disk ${USED}% >= ${DISK_THRESHOLD}% — alerting"
    notify "Disk at ${USED}% on the vac box (threshold ${DISK_THRESHOLD}%). Try: docker system prune, check /var/lib/docker."
    touch "$ALERT_STAMP"
  else
    echo "disk ${USED}% >= ${DISK_THRESHOLD}% — already alerted recently"
  fi
else
  echo "disk ${USED:-?}% ok"
  rm -f "$ALERT_STAMP" 2>/dev/null || true
fi

# ---- 2. Hung containers (healthcheck failing while the process still runs)
# Plain `docker ps` rather than `docker compose ps`: the health filter is
# supported on every docker version, compose's filter support varies. The box
# runs only this one stack, so every unhealthy container here is ours.
UNHEALTHY=$(docker ps --filter health=unhealthy --format '{{.Names}}' 2>/dev/null | grep -v '^$' || true)
if [ -n "$UNHEALTHY" ]; then
  for name in $UNHEALTHY; do
    echo "restarting unhealthy container: $name"
    docker restart "$name" >/dev/null 2>&1 \
      && notify "Restarted unhealthy container '$name' (healthcheck failing)." \
      || notify "Container '$name' is unhealthy and the restart FAILED — needs a human."
  done
else
  echo "containers ok"
fi
