#!/usr/bin/env bash
# One-time AWS bootstrap for Valorant AI Companion.
#
# Run from a bash shell (Git Bash on Windows) with the AWS CLI and the GitHub CLI (`gh`)
# on PATH and an active AWS session (`aws login`). Idempotent: re-running reuses
# everything it already created and only fills in what's missing.
#
# What it creates (everything named "vac"):
#   - SSM Parameter Store: the backend secrets, copied from backend/.env (SecureString)
#   - IAM: an EC2 instance role (Systems Manager access + read those parameters)
#   - EC2: a security group that only admits CloudFront, one t3.small running Docker
#     Compose (Amazon Linux 2023), and an Elastic IP so the origin address never changes
#   - CloudFront: HTTPS in front of the box — a free *.cloudfront.net URL now, your own
#     domain later via infra/add-domain.sh
#   - IAM: a GitHub Actions OIDC deploy role + the repo variables the workflow reads, so
#     every push to main deploys with no long-lived AWS keys anywhere
#
# Rough cost (us-east-1, on-demand): t3.small ~$15/mo + 20 GB gp3 ~$1.60 + public IPv4
# ~$3.65; CloudFront and Parameter Store sit inside the always-free tier at this scale.
#
# Tunables (env vars): APP, AWS_REGION, INSTANCE_TYPE, VOLUME_GB, REPO, BRANCH, ENV_FILE
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' AWS_PAGER=""   # Git Bash: keep /paths intact

APP=${APP:-vac}
REGION=${AWS_REGION:-$(aws configure get region 2>/dev/null || true)}; REGION=${REGION:-us-east-1}
INSTANCE_TYPE=${INSTANCE_TYPE:-t3.small}
VOLUME_GB=${VOLUME_GB:-20}
REPO=${REPO:-SergioB03/Valorant-ai-companion}
BRANCH=${BRANCH:-main}
ENV_FILE=${ENV_FILE:-backend/.env}
PARAM_PREFIX=/$APP
export AWS_DEFAULT_REGION=$REGION

cd "$(dirname "${BASH_SOURCE[0]}")/.."

log()  { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

command -v aws >/dev/null || die 'aws CLI not on PATH (Windows: add "C:\Program Files\Amazon\AWSCLIV2" or open a new terminal)'
command -v gh  >/dev/null || die "GitHub CLI (gh) not on PATH"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found — copy backend/.env.example and fill in the keys"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  || die "No active AWS session. Run:  aws login   and then re-run this script."
log "AWS account $ACCOUNT · region $REGION · app \"$APP\" · repo $REPO"

# ----------------------------------------------------------------------------- secrets
log "Secrets -> SSM Parameter Store ($PARAM_PREFIX/*)"
while IFS= read -r -u 3 line || [ -n "$line" ]; do
  line=${line%$'\r'}
  [[ -z "$line" || "$line" == \#* ]] && continue
  key=${line%%=*}; value=${line#*=}
  [[ "$key" == CORS_ORIGINS ]] && continue      # derived from the public URL further down
  [ -n "$value" ] || continue                   # Parameter Store rejects empty values
  aws ssm put-parameter --name "$PARAM_PREFIX/$key" --value "$value" --type SecureString --overwrite >/dev/null
  note "$key"
done 3< "$ENV_FILE"
ADMIN_TOKEN=""
if ! aws ssm get-parameter --name "$PARAM_PREFIX/ADMIN_TOKEN" >/dev/null 2>&1; then
  ADMIN_TOKEN=$(openssl rand -hex 32)
  aws ssm put-parameter --name "$PARAM_PREFIX/ADMIN_TOKEN" --value "$ADMIN_TOKEN" --type SecureString >/dev/null
  note "ADMIN_TOKEN (generated; unlocks GET /api/analytics/summary — printed at the end)"
fi
# Shared secret CloudFront stamps on every origin request (X-Origin-Verify); Caddy rejects
# anything without it, so the box is reachable only through *our* distribution.
if ! aws ssm get-parameter --name "$PARAM_PREFIX/ORIGIN_SECRET" >/dev/null 2>&1; then
  aws ssm put-parameter --name "$PARAM_PREFIX/ORIGIN_SECRET" --value "$(openssl rand -hex 32)" --type SecureString >/dev/null
  note "ORIGIN_SECRET (generated)"
fi
ORIGIN_SECRET=$(aws ssm get-parameter --name "$PARAM_PREFIX/ORIGIN_SECRET" --with-decryption --query Parameter.Value --output text)

# ----------------------------------------------------------------------------- backups
log "S3 bucket for nightly SQLite backups"
BUCKET="$APP-backups-$ACCOUNT"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  note "reusing $BUCKET"
else
  if [ "$REGION" = us-east-1 ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"       --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
  fi
  note "created $BUCKET"
fi
# Private, encrypted, versioned, and self-expiring. tilt_snapshots is the only
# data here that cannot be regenerated, and the root volume it lives on is
# created with DeleteOnTermination=true.
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration   BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration   '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration   '{"Rules":[{"ID":"expire-old-backups","Status":"Enabled","Filter":{"Prefix":"companion/"},"Expiration":{"Days":90},"NoncurrentVersionExpiration":{"NoncurrentDays":30}}]}' >/dev/null
aws ssm put-parameter --name "$PARAM_PREFIX/BACKUP_BUCKET" --value "$BUCKET" --type String --overwrite >/dev/null

# ----------------------------------------------------------------------------- instance role
log "IAM instance role"
ROLE=$APP-ec2-role
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  note "created $ROLE"
else
  note "reusing $ROLE"
fi
# SSM agent / Run Command / Session Manager permissions. The "default" managed policy
# deliberately lacks ssm:GetParameter*, so the box can read only the /vac/* parameters
# granted below (AmazonSSMManagedInstanceCore would allow reading every parameter).
aws iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedEC2InstanceDefaultPolicy
aws iam detach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore 2>/dev/null || true
# GetParametersByPath is authorized against the path itself (parameter/vac); the others
# against each parameter (parameter/vac/NAME) — so the policy needs both ARNs.
aws iam put-role-policy --role-name "$ROLE" --policy-name read-app-parameters --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"ssm:GetParametersByPath\",\"ssm:GetParameters\",\"ssm:GetParameter\"],\"Resource\":[\"arn:aws:ssm:$REGION:$ACCOUNT:parameter$PARAM_PREFIX\",\"arn:aws:ssm:$REGION:$ACCOUNT:parameter$PARAM_PREFIX/*\"]}]}"
# Write-only, and only to this one bucket.
aws iam put-role-policy --role-name "$ROLE" --policy-name write-backups --policy-document   "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:PutObject\",\"s3:ListBucket\",\"s3:DeleteObject\"],\"Resource\":[\"arn:aws:s3:::$BUCKET\",\"arn:aws:s3:::$BUCKET/*\"]}]}"
if ! aws iam get-instance-profile --instance-profile-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
fi
if [ "$(aws iam get-instance-profile --instance-profile-name "$ROLE" --query 'InstanceProfile.Roles[0].RoleName' --output text)" != "$ROLE" ]; then
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
  note "waiting for IAM to propagate"; sleep 15
fi

# ----------------------------------------------------------------------------- network
log "Security group (port 80 from CloudFront only — no SSH; use SSM Session Manager)"
VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
[ "$VPC_ID" != None ] || die "No default VPC in $REGION"
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$APP-web" "Name=vpc-id,Values=$VPC_ID" \
          --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = None ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$APP-web" --description "$APP web: HTTP from CloudFront only" \
            --vpc-id "$VPC_ID" --query GroupId --output text)
  note "created $SG_ID"
else
  note "reusing $SG_ID"
fi
CF_PL=$(aws ec2 describe-managed-prefix-lists --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
          --query 'PrefixLists[0].PrefixListId' --output text)
[ "$CF_PL" != None ] || die "CloudFront origin-facing prefix list not found in $REGION"
if ! aws ec2 describe-security-groups --group-ids "$SG_ID" \
       --query "SecurityGroups[0].IpPermissions[?FromPort==\`80\`].PrefixListIds[].PrefixListId" --output text | grep -q "$CF_PL"; then
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --ip-permissions \
    "[{\"IpProtocol\":\"tcp\",\"FromPort\":80,\"ToPort\":80,\"PrefixListIds\":[{\"PrefixListId\":\"$CF_PL\",\"Description\":\"CloudFront origin-facing\"}]}]" >/dev/null
  note "ingress: tcp/80 from $CF_PL (CloudFront)"
fi

# ----------------------------------------------------------------------------- instance
log "EC2 instance ($INSTANCE_TYPE, Amazon Linux 2023, ${VOLUME_GB} GB)"
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$APP-web" Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$INSTANCE_ID" = None ]; then
  AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
          --query Parameter.Value --output text)
  USER_DATA=$(sed -e "s|__REPO_URL__|https://github.com/$REPO.git|" -e "s|__BRANCH__|$BRANCH|" infra/user-data.sh)
  # A freshly created instance profile can take a minute to become visible to EC2.
  for attempt in 1 2 3 4 5 6 7 8; do
    if OUT=$(aws ec2 run-instances \
        --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
        --security-group-ids "$SG_ID" --iam-instance-profile "Name=$ROLE" \
        --user-data "$USER_DATA" \
        --metadata-options HttpTokens=required,HttpEndpoint=enabled \
        --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":$VOLUME_GB,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$APP-web}]" "ResourceType=volume,Tags=[{Key=Name,Value=$APP-web}]" \
        --query 'Instances[0].InstanceId' --output text 2>&1); then
      INSTANCE_ID=$OUT; break
    fi
    case "$OUT" in
      *"Invalid IAM Instance Profile"*) note "instance profile not visible to EC2 yet — retrying ($attempt/8)"; sleep 10 ;;
      *) printf '%s\n' "$OUT" >&2; die "run-instances failed" ;;
    esac
  done
  [ "$INSTANCE_ID" != None ] || die "EC2 kept rejecting the instance profile — wait a minute and re-run"
  note "launched $INSTANCE_ID — first boot installs Docker and builds the app (~5-8 min)"
  aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
  RESYNC=0
else
  note "reusing $INSTANCE_ID"
  STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].State.Name' --output text)
  if [ "$STATE" != running ]; then
    aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
  fi
  RESYNC=1   # re-run the first-boot script below so a failed/partial first boot gets repaired
fi

# ----------------------------------------------------------------------------- elastic ip
log "Elastic IP"
EIP_ALLOC=$(aws ec2 describe-addresses --filters "Name=tag:Name,Values=$APP-web" --query 'Addresses[0].AllocationId' --output text)
if [ "$EIP_ALLOC" = None ]; then
  EIP_ALLOC=$(aws ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$APP-web}]" --query AllocationId --output text)
fi
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$EIP_ALLOC" --allow-reassociation >/dev/null
PUBLIC_IP=$(aws ec2 describe-addresses --allocation-ids "$EIP_ALLOC" --query 'Addresses[0].PublicIp' --output text)
ORIGIN_DNS=None
for _ in 1 2 3 4 5 6; do
  ORIGIN_DNS=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicDnsName' --output text)
  [[ "$ORIGIN_DNS" == ec2-${PUBLIC_IP//./-}.* ]] && break
  sleep 5
done
[[ "$ORIGIN_DNS" == ec2-* ]] || die "Instance has no public DNS name (VPC needs DNS hostnames enabled)"
note "$PUBLIC_IP  ($ORIGIN_DNS)"

if [ "$RESYNC" = 1 ]; then
  log "Re-syncing the existing instance over SSM (re-runs infra/user-data.sh; idempotent)"
  RESYNC_CMD="curl -fsSL https://raw.githubusercontent.com/$REPO/$BRANCH/infra/user-data.sh | sed -e 's|__REPO_URL__|https://github.com/$REPO.git|' -e 's|__BRANCH__|$BRANCH|' | bash"
  for attempt in 1 2 3 4 5 6; do
    if CMD_ID=$(aws ssm send-command --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
          --comment "$APP bootstrap re-sync" --timeout-seconds 600 \
          --parameters "{\"commands\":[\"$RESYNC_CMD\"],\"executionTimeout\":[\"1800\"]}" \
          --query Command.CommandId --output text 2>/dev/null); then
      note "SSM command $CMD_ID  (follow along on the box: sudo tail -f /var/log/vac-bootstrap.log)"; break
    fi
    note "SSM agent not registered yet — retrying ($attempt/6)"; sleep 15
  done
fi

# ----------------------------------------------------------------------------- cloudfront
log "CloudFront distribution"
DIST_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='$APP'].Id | [0]" --output text)
if [ "$DIST_ID" = None ]; then
  CACHE_OPTIMIZED=$(aws cloudfront list-cache-policies --type managed \
    --query "CachePolicyList.Items[?CachePolicy.CachePolicyConfig.Name=='Managed-CachingOptimized'].CachePolicy.Id | [0]" --output text)
  CACHE_DISABLED=$(aws cloudfront list-cache-policies --type managed \
    --query "CachePolicyList.Items[?CachePolicy.CachePolicyConfig.Name=='Managed-CachingDisabled'].CachePolicy.Id | [0]" --output text)
  ORP_ID=$(aws cloudfront list-origin-request-policies --type custom \
    --query "OriginRequestPolicyList.Items[?OriginRequestPolicy.OriginRequestPolicyConfig.Name=='$APP-api'].OriginRequestPolicy.Id | [0]" --output text)
  if [ "$ORP_ID" = None ]; then
    # Forward the whole viewer request plus CloudFront-Viewer-Address, which the backend
    # uses as its per-IP rate-limit key (backend/app/limiter.py).
    ORP_ID=$(aws cloudfront create-origin-request-policy --origin-request-policy-config \
      "{\"Name\":\"$APP-api\",\"Comment\":\"viewer request + CloudFront-Viewer-Address\",\"HeadersConfig\":{\"HeaderBehavior\":\"allViewerAndWhitelistCloudFront\",\"Headers\":{\"Quantity\":1,\"Items\":[\"CloudFront-Viewer-Address\"]}},\"CookiesConfig\":{\"CookieBehavior\":\"none\"},\"QueryStringsConfig\":{\"QueryStringBehavior\":\"all\"}}" \
      --query OriginRequestPolicy.Id --output text)
  fi
  DIST_CONFIG=$(cat <<JSON
{
  "CallerReference": "$APP-$(date +%s)",
  "Comment": "$APP",
  "Enabled": true,
  "HttpVersion": "http2and3",
  "IsIPV6Enabled": true,
  "PriceClass": "PriceClass_100",
  "Origins": { "Quantity": 1, "Items": [ {
    "Id": "ec2", "DomainName": "$ORIGIN_DNS",
    "CustomHeaders": { "Quantity": 1, "Items": [ { "HeaderName": "X-Origin-Verify", "HeaderValue": "$ORIGIN_SECRET" } ] },
    "ConnectionAttempts": 1,
    "CustomOriginConfig": { "HTTPPort": 80, "HTTPSPort": 443, "OriginProtocolPolicy": "http-only",
      "OriginReadTimeout": 60, "OriginKeepaliveTimeout": 5,
      "OriginSslProtocols": { "Quantity": 1, "Items": ["TLSv1.2"] } }
  } ] },
  "DefaultCacheBehavior": {
    "TargetOriginId": "ec2", "ViewerProtocolPolicy": "redirect-to-https", "Compress": true,
    "AllowedMethods": { "Quantity": 3, "Items": ["GET","HEAD","OPTIONS"], "CachedMethods": { "Quantity": 2, "Items": ["GET","HEAD"] } },
    "CachePolicyId": "$CACHE_OPTIMIZED"
  },
  "CacheBehaviors": { "Quantity": 1, "Items": [ {
    "PathPattern": "/api/*", "TargetOriginId": "ec2", "ViewerProtocolPolicy": "redirect-to-https", "Compress": true,
    "AllowedMethods": { "Quantity": 7, "Items": ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"], "CachedMethods": { "Quantity": 2, "Items": ["GET","HEAD"] } },
    "CachePolicyId": "$CACHE_DISABLED", "OriginRequestPolicyId": "$ORP_ID"
  } ] }
}
JSON
)
  DIST_ID=$(aws cloudfront create-distribution --distribution-config "$DIST_CONFIG" --query Distribution.Id --output text)
  note "created $DIST_ID (global rollout takes ~5-10 min)"
else
  note "reusing $DIST_ID"
fi
CF_DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query Distribution.DomainName --output text)
APP_URL="https://$CF_DOMAIN"
if ! aws ssm get-parameter --name "$PARAM_PREFIX/CORS_ORIGINS" >/dev/null 2>&1; then
  aws ssm put-parameter --name "$PARAM_PREFIX/CORS_ORIGINS" --value "$APP_URL" --type String >/dev/null
fi

# ----------------------------------------------------------------------------- github actions
log "GitHub Actions deploy role (OIDC — no stored AWS keys)"
OIDC_ARN="arn:aws:iam::$ACCOUNT:oidc-provider/token.actions.githubusercontent.com"
if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" >/dev/null 2>&1; then
  aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 1c58a3a8518e8759bf075b76b750d4f2df264fcd >/dev/null
  note "created OIDC provider"
fi
DEPLOY_ROLE=$APP-github-deploy
TRUST="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Federated\":\"$OIDC_ARN\"},\"Action\":\"sts:AssumeRoleWithWebIdentity\",\"Condition\":{\"StringEquals\":{\"token.actions.githubusercontent.com:aud\":\"sts.amazonaws.com\",\"token.actions.githubusercontent.com:sub\":\"repo:$REPO:ref:refs/heads/$BRANCH\"}}}]}"
if aws iam get-role --role-name "$DEPLOY_ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$DEPLOY_ROLE" --policy-document "$TRUST"
  note "reusing $DEPLOY_ROLE"
else
  aws iam create-role --role-name "$DEPLOY_ROLE" --assume-role-policy-document "$TRUST" >/dev/null
  note "created $DEPLOY_ROLE"
fi
aws iam put-role-policy --role-name "$DEPLOY_ROLE" --policy-name deploy --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"ssm:SendCommand\",\"Resource\":[\"arn:aws:ec2:$REGION:$ACCOUNT:instance/$INSTANCE_ID\",\"arn:aws:ssm:$REGION::document/AWS-RunShellScript\"]},{\"Effect\":\"Allow\",\"Action\":[\"ssm:GetCommandInvocation\",\"ssm:ListCommandInvocations\"],\"Resource\":\"*\"},{\"Effect\":\"Allow\",\"Action\":\"cloudfront:CreateInvalidation\",\"Resource\":\"arn:aws:cloudfront::$ACCOUNT:distribution/$DIST_ID\"}]}"
DEPLOY_ROLE_ARN="arn:aws:iam::$ACCOUNT:role/$DEPLOY_ROLE"

log "GitHub repo variables ($REPO) for .github/workflows/deploy.yml"
gh variable set AWS_REGION                 --repo "$REPO" --body "$REGION"
gh variable set AWS_ROLE_ARN               --repo "$REPO" --body "$DEPLOY_ROLE_ARN"
gh variable set EC2_INSTANCE_ID            --repo "$REPO" --body "$INSTANCE_ID"
gh variable set CLOUDFRONT_DISTRIBUTION_ID --repo "$REPO" --body "$DIST_ID"
if [ "$(gh variable get APP_URL --repo "$REPO" 2>/dev/null || true)" = "" ]; then
  gh variable set APP_URL --repo "$REPO" --body "$APP_URL"
fi

# ----------------------------------------------------------------------------- wait
log "Waiting for the first deploy + CloudFront rollout (up to 20 min): $APP_URL"
READY=0
for i in $(seq 1 120); do
  if curl -fsS --max-time 10 "$APP_URL/api/" >/dev/null 2>&1; then READY=1; break; fi
  if [ $((i % 6)) -eq 0 ]; then note "still waiting ($((i / 6)) min)..."; fi
  sleep 10
done

echo
echo "======================================================================"
if [ $READY = 1 ]; then
  echo "  LIVE       $APP_URL"
  echo "  API docs   $APP_URL/api/docs"
else
  echo "  Not reachable yet: $APP_URL"
  echo "  Inspect the box:  aws ssm start-session --target $INSTANCE_ID"
  echo "                    sudo tail -f /var/log/vac-bootstrap.log"
fi
echo "  Instance   $INSTANCE_ID  ($PUBLIC_IP)"
echo "  Deploys    push to '$BRANCH' -> GitHub Actions -> SSM -> infra/deploy.sh"
echo "  Domain     infra/add-domain.sh <your-domain>   (after registering it in Route 53)"
if [ -n "$ADMIN_TOKEN" ]; then
  echo "  ADMIN_TOKEN (save it — not shown again):  $ADMIN_TOKEN"
fi
echo "======================================================================"
