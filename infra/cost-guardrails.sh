#!/bin/bash
# AWS-side money guardrails. One-time, idempotent. NOT run automatically —
# execute it yourself from an operator session (`aws login`).
# See DEPLOYMENT.md "Pre-deploy checklist".
#
# Every existing dollar-guardrail (claude_service breaker, per-IP quotas, daily
# spend ceiling) lives in app code on the box — a bug, a compromised instance,
# or plain AWS drift (an EIP billing while unattached) bypasses all of it.
# These two controls live outside that blast radius:
#
#   1. AWS Budget "vac-monthly": $20/month (expected steady-state spend per
#      DEPLOYMENT.md — t3.small + gp3 + IPv4) with email alerts at 50% and 80%
#      actual and 100% forecasted. Override: BUDGET_LIMIT=25.
#   2. Cost Anomaly Detection: the per-service monitor + a daily email
#      subscription for anomalies with total impact >= $5.
#
# Both are free. The third guardrail — the Anthropic console monthly spend cap,
# the one budget.py's docstring calls "the one no bug of ours can defeat" — has
# no API and must be set by hand: https://console.anthropic.com -> Billing ->
# Limits (documented as a user step in DEPLOYMENT.md).
#
# Usage:  infra/cost-guardrails.sh you@example.com
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' AWS_PAGER=""

APP=${APP:-vac}
EMAIL=${1:?usage: infra/cost-guardrails.sh <alert-email>}
BUDGET_LIMIT=${BUDGET_LIMIT:-20}

command -v aws >/dev/null || { echo 'aws CLI not on PATH'; exit 1; }
ACCOUNT=$(aws sts get-caller-identity --query Account --output text) \
  || { echo "No active AWS session. Run: aws login"; exit 1; }
echo "==> Account $ACCOUNT · budget \$$BUDGET_LIMIT/month · alerts to $EMAIL"

# ----------------------------------------------------------------- monthly budget
BUDGET_NAME=$APP-monthly
if aws budgets describe-budget --account-id "$ACCOUNT" --budget-name "$BUDGET_NAME" >/dev/null 2>&1; then
  echo "==> Budget $BUDGET_NAME already exists — leaving it alone"
else
  echo "==> Creating budget $BUDGET_NAME"
  aws budgets create-budget --account-id "$ACCOUNT" \
    --budget "{
      \"BudgetName\": \"$BUDGET_NAME\",
      \"BudgetType\": \"COST\",
      \"TimeUnit\": \"MONTHLY\",
      \"BudgetLimit\": {\"Amount\": \"$BUDGET_LIMIT\", \"Unit\": \"USD\"}
    }" \
    --notifications-with-subscribers "[
      {\"Notification\": {\"NotificationType\": \"ACTUAL\",     \"ComparisonOperator\": \"GREATER_THAN\", \"Threshold\": 50,  \"ThresholdType\": \"PERCENTAGE\"},
       \"Subscribers\": [{\"SubscriptionType\": \"EMAIL\", \"Address\": \"$EMAIL\"}]},
      {\"Notification\": {\"NotificationType\": \"ACTUAL\",     \"ComparisonOperator\": \"GREATER_THAN\", \"Threshold\": 80,  \"ThresholdType\": \"PERCENTAGE\"},
       \"Subscribers\": [{\"SubscriptionType\": \"EMAIL\", \"Address\": \"$EMAIL\"}]},
      {\"Notification\": {\"NotificationType\": \"FORECASTED\", \"ComparisonOperator\": \"GREATER_THAN\", \"Threshold\": 100, \"ThresholdType\": \"PERCENTAGE\"},
       \"Subscribers\": [{\"SubscriptionType\": \"EMAIL\", \"Address\": \"$EMAIL\"}]}
    ]"
  echo "    created (50%/80% actual + 100% forecasted -> $EMAIL)"
fi

# ------------------------------------------------------- cost anomaly detection
MONITOR_NAME=$APP-services
MONITOR_ARN=$(aws ce get-anomaly-monitors \
  --query "AnomalyMonitors[?MonitorName=='$MONITOR_NAME'].MonitorArn | [0]" --output text 2>/dev/null || true)
if [ -z "$MONITOR_ARN" ] || [ "$MONITOR_ARN" = "None" ]; then
  echo "==> Creating anomaly monitor $MONITOR_NAME (per-service)"
  MONITOR_ARN=$(aws ce create-anomaly-monitor --anomaly-monitor \
    "{\"MonitorName\": \"$MONITOR_NAME\", \"MonitorType\": \"DIMENSIONAL\", \"MonitorDimension\": \"SERVICE\"}" \
    --query MonitorArn --output text)
else
  echo "==> Anomaly monitor $MONITOR_NAME already exists"
fi

SUB_NAME=$APP-anomaly-email
SUB_ARN=$(aws ce get-anomaly-subscriptions \
  --query "AnomalySubscriptions[?SubscriptionName=='$SUB_NAME'].SubscriptionArn | [0]" --output text 2>/dev/null || true)
if [ -z "$SUB_ARN" ] || [ "$SUB_ARN" = "None" ]; then
  echo "==> Creating anomaly subscription $SUB_NAME (daily email, impact >= \$5)"
  aws ce create-anomaly-subscription --anomaly-subscription "{
    \"SubscriptionName\": \"$SUB_NAME\",
    \"MonitorArnList\": [\"$MONITOR_ARN\"],
    \"Subscribers\": [{\"Type\": \"EMAIL\", \"Address\": \"$EMAIL\"}],
    \"Frequency\": \"DAILY\",
    \"ThresholdExpression\": {\"Dimensions\": {\"Key\": \"ANOMALY_TOTAL_IMPACT_ABSOLUTE\",
      \"MatchOptions\": [\"GREATER_THAN_OR_EQUAL\"], \"Values\": [\"5\"]}}
  }" >/dev/null
else
  echo "==> Anomaly subscription $SUB_NAME already exists"
fi

echo "==> Done. Remaining manual step: set the Anthropic console monthly spend cap"
echo "    (console.anthropic.com -> Billing -> Limits) — see DEPLOYMENT.md."
