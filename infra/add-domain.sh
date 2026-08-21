#!/usr/bin/env bash
# Put the app on your own domain.
#
#   infra/add-domain.sh example.com
#
# Prerequisite: the domain is registered in Route 53 (console -> Route 53 -> Registered
# domains -> Register domain; that creates its hosted zone automatically), or its DNS is
# otherwise served by a Route 53 hosted zone.
#
# Requests a free ACM certificate (DNS-validated), attaches it and the domain aliases to
# the CloudFront distribution, points apex + www at CloudFront, updates the backend's
# CORS list, and makes the domain the deploy workflow's APP_URL. Idempotent.
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' AWS_PAGER=""   # Git Bash: keep /paths intact

DOMAIN=${1:?usage: infra/add-domain.sh <domain>}
APP=${APP:-vac}
REPO=${REPO:-SergioB03/Valorant-ai-companion}
PARAM_PREFIX=/$APP
REGION=${AWS_REGION:-$(aws configure get region 2>/dev/null || true)}; REGION=${REGION:-us-east-1}
export AWS_DEFAULT_REGION=$REGION
cd "$(dirname "${BASH_SOURCE[0]}")/.."

log()  { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# A working Python for the one JSON edit below (Windows: the Store stub fails the probe).
PY=""
for c in python3 python py backend/venv/Scripts/python.exe; do
  if "$c" -c 'import json' >/dev/null 2>&1; then PY=$c; break; fi
done
[ -n "$PY" ] || die "Need a Python 3 interpreter on PATH"

aws sts get-caller-identity >/dev/null 2>&1 || die "No active AWS session. Run:  aws login"

ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN." --max-items 1 \
            --query "HostedZones[?Name=='$DOMAIN.'].Id | [0]" --output text)
[ "$ZONE_ID" != None ] || die "No Route 53 hosted zone for $DOMAIN — register the domain in Route 53 first"
ZONE_ID=${ZONE_ID##*/}
DIST_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='$APP'].Id | [0]" --output text)
[ "$DIST_ID" != None ] || die "No CloudFront distribution for \"$APP\" — run infra/bootstrap.sh first"
CF_DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query Distribution.DomainName --output text)
log "$DOMAIN -> CloudFront $DIST_ID ($CF_DOMAIN), hosted zone $ZONE_ID"

# ----------------------------------------------------------------------------- certificate
log "ACM certificate for $DOMAIN + www.$DOMAIN (us-east-1, as CloudFront requires)"
CERT_ARN=$(aws acm list-certificates --region us-east-1 --certificate-statuses ISSUED PENDING_VALIDATION \
             --query "CertificateSummaryList[?DomainName=='$DOMAIN'].CertificateArn | [0]" --output text)
if [ "$CERT_ARN" = None ]; then
  CERT_ARN=$(aws acm request-certificate --region us-east-1 --domain-name "$DOMAIN" \
               --subject-alternative-names "www.$DOMAIN" --validation-method DNS \
               --query CertificateArn --output text)
  note "requested $CERT_ARN"
else
  note "reusing $CERT_ARN"
fi
RECORDS=""
for _ in $(seq 1 12); do
  RECORDS=$(aws acm describe-certificate --region us-east-1 --certificate-arn "$CERT_ARN" \
              --query 'Certificate.DomainValidationOptions[].ResourceRecord.[Name,Value]' --output text | tr -d '\r' | sort -u)
  # (tr: the Windows AWS CLI writes CRLF, and a stray \r inside the JSON below would be rejected)
  [[ -n "$RECORDS" && "$RECORDS" != *None* ]] && break
  sleep 5
done
[[ -n "$RECORDS" && "$RECORDS" != *None* ]] || die "ACM did not publish DNS validation records"
while read -r name value; do
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch \
    "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$name\",\"Type\":\"CNAME\",\"TTL\":300,\"ResourceRecords\":[{\"Value\":\"$value\"}]}}]}" >/dev/null </dev/null
done <<< "$RECORDS"
note "validation records in place; waiting for issuance (usually 5-15 min, can be ~40)"
# Not `aws acm wait certificate-validated`: that waiter gives up after 5 minutes.
STATUS=PENDING_VALIDATION
for _ in $(seq 1 80); do
  STATUS=$(aws acm describe-certificate --region us-east-1 --certificate-arn "$CERT_ARN" --query Certificate.Status --output text)
  case "$STATUS" in
    ISSUED) break ;;
    FAILED|VALIDATION_TIMED_OUT|REVOKED|INACTIVE|EXPIRED) die "certificate ended up $STATUS — check ACM (us-east-1) in the console" ;;
  esac
  sleep 30
done
[ "$STATUS" = ISSUED ] || die "certificate still $STATUS after 40 min — DNS may not have propagated yet; re-run later"
note "issued"

# ----------------------------------------------------------------------------- cloudfront
log "CloudFront: aliases + certificate"
TMP=$(mktemp -d ./.add-domain.XXXXXX); trap 'rm -rf "$TMP"' EXIT
ETAG=$(aws cloudfront get-distribution-config --id "$DIST_ID" --query ETag --output text)
aws cloudfront get-distribution-config --id "$DIST_ID" --query DistributionConfig --output json > "$TMP/dist.json"
"$PY" - "$TMP/dist.json" "$DOMAIN" "$CERT_ARN" <<'PY'
import json, sys
path, domain, cert = sys.argv[1:4]
with open(path) as f:
    cfg = json.load(f)
aliases = sorted(set(cfg.get("Aliases", {}).get("Items") or []) | {domain, "www." + domain})
cfg["Aliases"] = {"Quantity": len(aliases), "Items": aliases}
cfg["ViewerCertificate"] = {
    "ACMCertificateArn": cert, "SSLSupportMethod": "sni-only", "MinimumProtocolVersion": "TLSv1.2_2021",
}
with open(path, "w") as f:
    json.dump(cfg, f)
PY
aws cloudfront update-distribution --id "$DIST_ID" --if-match "$ETAG" \
  --distribution-config "$(cat "$TMP/dist.json")" >/dev/null
note "updated (rollout ~5 min)"

# ----------------------------------------------------------------------------- dns
log "Route 53: $DOMAIN and www.$DOMAIN -> CloudFront"
for name in "$DOMAIN" "www.$DOMAIN"; do
  for type in A AAAA; do   # Z2FDTNDATAQYW2 is CloudFront's fixed alias hosted-zone id
    aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch \
      "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$name\",\"Type\":\"$type\",\"AliasTarget\":{\"HostedZoneId\":\"Z2FDTNDATAQYW2\",\"DNSName\":\"$CF_DOMAIN\",\"EvaluateTargetHealth\":false}}}]}" >/dev/null
  done
done

# ----------------------------------------------------------------------------- app config
log "Backend CORS list + deploy workflow APP_URL"
aws ssm put-parameter --name "$PARAM_PREFIX/CORS_ORIGINS" --type String --overwrite \
  --value "https://$DOMAIN,https://www.$DOMAIN,https://$CF_DOMAIN" >/dev/null
gh variable set APP_URL --repo "$REPO" --body "https://$DOMAIN"
gh workflow run deploy.yml --repo "$REPO" >/dev/null 2>&1 && note "redeploy triggered so the box picks up CORS_ORIGINS" || true

echo
echo "======================================================================"
echo "  https://$DOMAIN  (and https://www.$DOMAIN)"
echo "  Live once the CloudFront update finishes (~5 min) and DNS propagates."
echo "  $CF_DOMAIN keeps working as well."
echo "======================================================================"
