#!/bin/bash
# Arm the production configuration in SSM Parameter Store. One-time, idempotent.
# NOT run automatically — execute it yourself from an operator session
# (`aws login`), then deploy. See DEPLOYMENT.md "Pre-deploy checklist".
#
# What it does (and why):
#
#   1. /vac/ENVIRONMENT = production
#      main.py gates HSTS and the CORS-wildcard refusal on ENVIRONMENT, which
#      defaults to "development" — without this parameter both protections are
#      inert in prod. infra/deploy.sh copies every /vac/* parameter into
#      backend/.env on each deploy, and docker-compose's env_file hands it to
#      the container: creating the parameter is the entire wiring.
#
#   2. /vac/HENRIK_API_KEY = (copied from the existing /vac/RIOT_API_KEY)
#      The provider is HenrikDev, not Riot; riot_service.py already prefers the
#      new name and falls back to the old one. This script only ADDS the new
#      parameter — deleting /vac/RIOT_API_KEY happens by hand AFTER a verified
#      deploy (step in DEPLOYMENT.md), so the running app never sees a gap.
#
# Usage:  infra/arm-production.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' AWS_PAGER=""   # Git Bash: keep /vac/* intact

PARAM_PREFIX=${PARAM_PREFIX:-/vac}

command -v aws >/dev/null || { echo 'aws CLI not on PATH'; exit 1; }
aws sts get-caller-identity --query Account --output text >/dev/null \
  || { echo "No active AWS session. Run: aws login"; exit 1; }

echo "==> $PARAM_PREFIX/ENVIRONMENT = production"
aws ssm put-parameter --name "$PARAM_PREFIX/ENVIRONMENT" --value production \
  --type String --overwrite >/dev/null
echo "    done (arms HSTS + the CORS-wildcard refusal in backend/app/main.py)"

echo "==> $PARAM_PREFIX/HENRIK_API_KEY (copy of $PARAM_PREFIX/RIOT_API_KEY)"
if aws ssm get-parameter --name "$PARAM_PREFIX/HENRIK_API_KEY" >/dev/null 2>&1; then
  echo "    already exists — leaving it alone"
else
  OLD=$(aws ssm get-parameter --name "$PARAM_PREFIX/RIOT_API_KEY" --with-decryption \
    --query Parameter.Value --output text 2>/dev/null || true)
  if [ -z "$OLD" ] || [ "$OLD" = "None" ]; then
    echo "    $PARAM_PREFIX/RIOT_API_KEY not found — nothing to copy (set HENRIK_API_KEY manually)"
    exit 1
  fi
  aws ssm put-parameter --name "$PARAM_PREFIX/HENRIK_API_KEY" --value "$OLD" \
    --type SecureString >/dev/null
  echo "    created as SecureString ($PARAM_PREFIX/RIOT_API_KEY left in place)"
fi

cat <<'EOF'

Next steps:
  1. Deploy:            gh workflow run deploy.yml   (or push to main)
  2. Verify readiness:  curl -s https://rebuy.gg/api/health/ready
                        -> "status": "ready", "environment": "production"
  3. Only then retire the legacy name:
                        aws ssm delete-parameter --name /vac/RIOT_API_KEY
     (and remove the fallback in backend/app/services/riot_service.py at leisure)
EOF
