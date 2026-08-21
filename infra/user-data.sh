#!/bin/bash
# EC2 user data — runs once on first boot (Amazon Linux 2023). Installs Docker + Compose,
# clones the repo and runs the first deploy. Every later deploy comes from GitHub Actions
# via SSM (.github/workflows/deploy.yml -> infra/deploy.sh).
# infra/bootstrap.sh substitutes the __PLACEHOLDERS__ before launching the instance.
set -euxo pipefail
exec > >(tee /var/log/vac-bootstrap.log | logger -t vac-bootstrap) 2>&1

REPO_URL="__REPO_URL__"
BRANCH="__BRANCH__"
APP_DIR=/opt/vac

# 2 GB swap: t3.small has 2 GB RAM and the embedding model + Chroma appreciate headroom.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

dnf install -y docker git
systemctl enable --now docker

# Compose v2 isn't packaged for AL2023 — install the official CLI plugin binary.
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version

if [ ! -d "$APP_DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
chmod +x "$APP_DIR"/infra/*.sh
BRANCH="$BRANCH" "$APP_DIR/infra/deploy.sh"
