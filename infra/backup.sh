#!/bin/bash
# Nightly backup of the SQLite state to S3.
#
# Installed on the instance by infra/deploy.sh as a cron job. Run by hand any
# time: sudo /opt/vac/infra/backup.sh
#
# Why this exists: companion.sqlite3 holds tilt_snapshots — the only data in
# this system that cannot be regenerated from anywhere else. It lives on a
# docker volume on the root EBS volume, which is created with
# DeleteOnTermination=true. Terminating the instance destroys it.
#
# Uses SQLite's own backup API rather than copying the file: the database runs
# in WAL mode and is written while the app serves traffic, so a plain `cp` can
# capture a torn database. The API is safe against a live writer. It also runs
# inside the api container, which already has python and the volume mounted —
# the host has no sqlite3 CLI installed.
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/vac}
PARAM_PREFIX=${PARAM_PREFIX:-/vac}
RETAIN_DAYS=${RETAIN_DAYS:-90}
cd "$APP_DIR"

TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
export AWS_DEFAULT_REGION=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

BUCKET=$(aws ssm get-parameter --name "$PARAM_PREFIX/BACKUP_BUCKET" --query Parameter.Value --output text 2>/dev/null || true)
if [ -z "$BUCKET" ] || [ "$BUCKET" = "None" ]; then
  echo "No $PARAM_PREFIX/BACKUP_BUCKET parameter — run infra/bootstrap.sh to create the bucket. Skipping."
  exit 0
fi

STAMP=$(date -u +%Y-%m-%dT%H-%M-%SZ)
TMP=/tmp/vac-backup-$STAMP.sqlite3

# Consistent snapshot of a live, WAL-mode database.
docker compose exec -T api python -c "
import sqlite3, os
src = sqlite3.connect(os.environ['VAC_STATE_DIR'] + '/companion.sqlite3')
dst = sqlite3.connect('/tmp/backup.sqlite3')
with dst:
    src.backup(dst)
dst.close(); src.close()
print('snapshot ok')
"
docker compose cp api:/tmp/backup.sqlite3 "$TMP"
docker compose exec -T api rm -f /tmp/backup.sqlite3

# Verify the copy is a readable database before trusting it. A backup nobody
# checked is a backup you find out about during the restore.
python3 - "$TMP" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity check failed"
n = db.execute("SELECT COUNT(*) FROM tilt_snapshots").fetchone()[0]
print(f"verified: integrity ok, {n} tilt snapshots")
db.close()
PY

gzip -f "$TMP"
KEY="companion/$(date -u +%Y/%m)/companion-$STAMP.sqlite3.gz"
aws s3 cp "$TMP.gz" "s3://$BUCKET/$KEY" --only-show-errors
rm -f "$TMP.gz"
echo "uploaded s3://$BUCKET/$KEY ($(date -u +%FT%TZ))"

# Bucket lifecycle also expires old objects; this is belt and braces for the
# case where the lifecycle rule is ever removed.
CUTOFF=$(date -u -d "-$RETAIN_DAYS days" +%Y-%m-%d 2>/dev/null || true)
if [ -n "$CUTOFF" ]; then
  aws s3api list-objects-v2 --bucket "$BUCKET" --prefix companion/ \
    --query "Contents[?LastModified<'$CUTOFF'].Key" --output text 2>/dev/null \
    | tr '\t' '\n' | grep -v '^$' | while read -r k; do
        aws s3 rm "s3://$BUCKET/$k" --only-show-errors
      done || true
fi
