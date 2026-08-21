#!/bin/bash
# On-box deploy (runs as root on the EC2 instance): refresh secrets from SSM Parameter
# Store, fast-forward the code, rebuild + restart the containers. Idempotent.
set -euo pipefail
APP_DIR=${APP_DIR:-/opt/vac}
PARAM_PREFIX=${PARAM_PREFIX:-/vac}
BRANCH=${BRANCH:-main}
cd "$APP_DIR"

# Region from instance metadata (IMDSv2) so the script needs no config of its own.
TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
export AWS_DEFAULT_REGION=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

echo "==> Secrets: SSM Parameter Store $PARAM_PREFIX/* -> backend/.env"
aws ssm get-parameters-by-path --path "$PARAM_PREFIX" --with-decryption --output json \
  | python3 -c '
import json, sys
prefix = sys.argv[1].rstrip("/") + "/"
for p in json.load(sys.stdin)["Parameters"]:
    print(p["Name"].removeprefix(prefix) + "=" + p["Value"])
' "$PARAM_PREFIX" > backend/.env.new
[ -s backend/.env.new ] || { echo "No parameters found under $PARAM_PREFIX — run infra/bootstrap.sh first"; exit 1; }
install -m 600 backend/.env.new backend/.env && rm backend/.env.new
echo "    $(grep -c = backend/.env) variables written"
# Compose reads ./.env for ${ORIGIN_SECRET} (the CloudFront origin shared secret for Caddy).
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' backend/.env | cut -d= -f2- || true)
install -m 600 /dev/null .env && printf 'ORIGIN_SECRET=%s\n' "$ORIGIN_SECRET" > .env

echo "==> Code: origin/$BRANCH"
git fetch --quiet origin "$BRANCH"
git reset --hard --quiet "origin/$BRANCH"
echo "    $(git rev-parse --short HEAD)  $(git log -1 --pretty=%s)"

echo "==> Containers: build + (re)start"
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null
docker builder prune -f --keep-storage 2g >/dev/null   # keep BuildKit cache bounded on the 20 GB disk

echo "==> Health"
for i in $(seq 1 45); do
  if curl -fsS -H "X-Origin-Verify: $ORIGIN_SECRET" http://localhost/api/ >/dev/null 2>&1; then
    echo "    API up: $(curl -fsS -H "X-Origin-Verify: $ORIGIN_SECRET" http://localhost/api/meta/status)"
    exit 0
  fi
  sleep 2
done
echo "API did not come up in 90s. Container state:"
docker compose ps -a
# Recent logs minus request lines: those carry player names, and this output can end up
# in the public GitHub Actions log.
docker compose logs --no-color --tail=60 api 2>&1 | grep -vE '"(GET|POST) /(riot|mental|claude)/' || true
exit 1
