#!/bin/bash
# CloudWatch alarms for instance death — the failure mode no in-app alerting
# can report (alerts.py runs inside the app; a dead box notifies no one).
# One-time, idempotent (put-metric-alarm overwrites in place). NOT run
# automatically — execute it yourself from an operator session (`aws login`).
# See DEPLOYMENT.md "Pre-deploy checklist".
#
# Creates:
#   - SNS topic "vac-alarms" + an email subscription (confirm the email AWS sends!)
#   - Alarm vac-instance-status-failed: StatusCheckFailed_Instance -> SNS.
#     Software-level death (kernel panic, OOM, full disk wedging the OS).
#   - Alarm vac-system-status-failed:   StatusCheckFailed_System -> SNS + EC2
#     auto-recover. Hardware/hypervisor failure; recover migrates the instance
#     to healthy hardware keeping volume, Elastic IP and instance id (works for
#     t3: EBS-only, no instance store).
#
# All of this sits in CloudWatch's always-free tier at this scale.
#
# Usage:  infra/ec2-alarms.sh you@example.com
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' AWS_PAGER=""

APP=${APP:-vac}
EMAIL=${1:?usage: infra/ec2-alarms.sh <alert-email>}

command -v aws >/dev/null || { echo 'aws CLI not on PATH'; exit 1; }
ACCOUNT=$(aws sts get-caller-identity --query Account --output text) \
  || { echo "No active AWS session. Run: aws login"; exit 1; }
REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || echo us-east-1)}}
export AWS_DEFAULT_REGION=$REGION

INSTANCE_ID=${INSTANCE_ID:-$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$APP-web" Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)}
[ -n "$INSTANCE_ID" ] && [ "$INSTANCE_ID" != "None" ] \
  || { echo "No running instance tagged Name=$APP-web (override with INSTANCE_ID=...)"; exit 1; }
echo "==> Instance $INSTANCE_ID · region $REGION · account $ACCOUNT"

echo "==> SNS topic $APP-alarms + email subscription"
TOPIC_ARN=$(aws sns create-topic --name "$APP-alarms" --query TopicArn --output text)
if ! aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" \
     --query "Subscriptions[?Endpoint=='$EMAIL']" --output text | grep -q .; then
  aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email --notification-endpoint "$EMAIL" >/dev/null
  echo "    subscribed $EMAIL — CONFIRM THE EMAIL AWS JUST SENT or alarms go nowhere"
else
  echo "    $EMAIL already subscribed"
fi

echo "==> Alarm: instance status check failed -> email"
aws cloudwatch put-metric-alarm \
  --alarm-name "$APP-instance-status-failed" \
  --alarm-description "$APP box failing its instance status check (OS-level death)" \
  --namespace AWS/EC2 --metric-name StatusCheckFailed_Instance \
  --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
  --statistic Maximum --period 60 --evaluation-periods 3 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data breaching \
  --alarm-actions "$TOPIC_ARN" --ok-actions "$TOPIC_ARN"

echo "==> Alarm: system status check failed -> email + EC2 auto-recover"
aws cloudwatch put-metric-alarm \
  --alarm-name "$APP-system-status-failed" \
  --alarm-description "$APP box on failed hardware — auto-recover keeps volume/EIP/instance-id" \
  --namespace AWS/EC2 --metric-name StatusCheckFailed_System \
  --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
  --statistic Maximum --period 60 --evaluation-periods 2 \
  --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions "arn:aws:automate:$REGION:ec2:recover" "$TOPIC_ARN"

echo "==> Done. Verify: aws cloudwatch describe-alarms --alarm-name-prefix $APP- --query 'MetricAlarms[].{name:AlarmName,state:StateValue}'"
