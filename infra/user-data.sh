#!/bin/bash
# EC2 user data — runs once on first boot (Amazon Linux 2023). Installs Docker + Compose,
# clones the repo and runs the first deploy. Every later deploy comes from GitHub Actions
# via SSM (.github/workflows/deploy.yml -> infra/deploy.sh).
# infra/bootstrap.sh substitutes the __PLACEHOLDERS__ before launching the instance, and
# re-runs this script over SSM when it has to re-sync an existing instance — so every
# step here must be safe to repeat.
set -euxo pipefail
exec > >(tee -a /var/log/vac-bootstrap.log | logger -t vac-bootstrap) 2>&1

REPO_URL="__REPO_URL__"
BRANCH="__BRANCH__"
APP_DIR=/opt/vac

# bootstrap.sh swaps the auto-assigned public IP for an Elastic IP seconds after launch,
# which can drop connections mid-flight. Wait for the network to settle, and retry the
# steps below that don't retry on their own.
until curl -fsS --max-time 5 https://github.com >/dev/null 2>&1; do sleep 3; done

# 2 GB swap: t3.small has 2 GB RAM and the image builds appreciate headroom.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

dnf install -y docker git
systemctl enable --now docker

# Compose v2 isn't packaged for AL2023 — install the official CLI plugin binary.
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL --retry 5 --retry-all-errors --retry-delay 3 \
  "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version

if [ ! -d "$APP_DIR/.git" ]; then
  for attempt in 1 2 3 4 5; do
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR" && break
    echo "git clone failed (attempt $attempt) — retrying"
    rm -rf "$APP_DIR"; sleep 5
  done
  [ -d "$APP_DIR/.git" ] || { echo "git clone kept failing"; exit 1; }
fi
chmod +x "$APP_DIR"/infra/*.sh
BRANCH="$BRANCH" "$APP_DIR/infra/deploy.sh"
