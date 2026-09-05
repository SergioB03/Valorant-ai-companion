#!/bin/bash
# Restore the SQLite state from the nightly S3 backups (counterpart to backup.sh).
#
#   DRILL (safe anywhere, read-only against S3, touches no container):
#     infra/restore.sh --drill
#       downloads the newest backup into a temp dir, verifies integrity, prints
#       per-table row counts, and leaves the file there for inspection.
#
#   FULL RESTORE (on the box, as root, in a quiet hour):
#     sudo /opt/vac/infra/restore.sh
#       1. runs infra/backup.sh first, so "restoring over itself" rolls the DB
#          back minutes, not 24 hours of tilt_snapshots (skip: --no-pre-backup)
#       2. downloads + verifies the newest backup (or --key <s3-key>)
#       3. stops the api container
#       4. inside the state volume: sets the current db aside (timestamped) and
#          DELETES companion.sqlite3-wal/-shm — SQLite must never replay a
#          mismatched WAL over the restored file
#       5. copies the restored db in, restarts api, polls /api/health
#
#   RESTORE TO A DIRECTORY (no containers touched):
#     infra/restore.sh --target-dir /some/dir
#
# Credentials: on the box this uses the instance role — which needs s3:GetObject
# on the companion/* prefix (added to bootstrap.sh's write-backups policy;
# re-run infra/bootstrap.sh once to apply it). Anywhere else, use your operator
# session (`aws login`) and set BACKUP_BUCKET=vac-backups-<account-id> since
# there is no instance metadata to derive it from.
#
# See DEPLOYMENT.md ("Backups and restore") for the drill log and RTO notes.
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' AWS_PAGER=""   # Git Bash: keep args intact

APP_DIR=${APP_DIR:-/opt/vac}
PARAM_PREFIX=${PARAM_PREFIX:-/vac}
DB_NAME=companion.sqlite3

DRILL=0
KEY=""
TARGET_DIR=""
PRE_BACKUP=1
while [ $# -gt 0 ]; do
  case "$1" in
    --drill)          DRILL=1 ;;
    --key)            KEY=${2:?--key needs an s3 key}; shift ;;
    --target-dir)     TARGET_DIR=${2:?--target-dir needs a directory}; shift ;;
    --no-pre-backup)  PRE_BACKUP=0 ;;
    -h|--help)        sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1 (see --help)"; exit 2 ;;
  esac
  shift
done

# Windows/Git Bash note: bare `python` may be the MS Store stub — point PYTHON
# at a real interpreter (e.g. backend/venv/Scripts/python.exe) for a local drill.
PY=${PYTHON:-$(command -v python3 || command -v python)}
[ -n "$PY" ] || { echo "python3 not found — needed for the integrity check (set PYTHON=...)"; exit 1; }

# Region: instance metadata when on the box, else whatever the CLI session has.
if [ -z "${AWS_DEFAULT_REGION:-}" ] && [ -z "${AWS_REGION:-}" ]; then
  TOKEN=$(curl -fsS -m 2 -X PUT http://169.254.169.254/latest/api/token \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)
  if [ -n "$TOKEN" ]; then
    AWS_DEFAULT_REGION=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" \
      http://169.254.169.254/latest/meta-data/placement/region)
    export AWS_DEFAULT_REGION
  fi
fi

BUCKET=${BACKUP_BUCKET:-$(aws ssm get-parameter --name "$PARAM_PREFIX/BACKUP_BUCKET" \
  --query Parameter.Value --output text 2>/dev/null || true)}
if [ -z "$BUCKET" ] || [ "$BUCKET" = "None" ]; then
  echo "No bucket: set BACKUP_BUCKET=vac-backups-<account-id> or create $PARAM_PREFIX/BACKUP_BUCKET"
  exit 1
fi

# ---- 1. Pick the backup object
if [ -z "$KEY" ]; then
  KEY=$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix companion/ \
    --query 'sort_by(Contents,&LastModified)[-1].Key' --output text)
  [ -n "$KEY" ] && [ "$KEY" != "None" ] || { echo "No backups under s3://$BUCKET/companion/"; exit 1; }
fi
echo "==> Backup object: s3://$BUCKET/$KEY"

# ---- 2. Download + decompress + verify
WORK=$(mktemp -d "${TMPDIR:-/tmp}/vac-restore.XXXXXX")
echo "==> Working dir: $WORK"
# aws.exe is a native Windows program: with path conversion disabled above (to
# protect s3:// and /vac/* args) it would treat an MSYS /tmp path as C:\tmp.
# Give aws a Windows-native path on Git Bash; bash-side tools keep using $WORK.
AWS_WORK=$WORK
command -v cygpath >/dev/null 2>&1 && AWS_WORK=$(cygpath -w "$WORK")
aws s3 cp "s3://$BUCKET/$KEY" "$AWS_WORK/backup.sqlite3.gz" --only-show-errors
gzip -dc "$WORK/backup.sqlite3.gz" > "$WORK/$DB_NAME"

echo "==> Integrity check + row counts"
"$PY" - "$WORK/$DB_NAME" <<'PYEOF'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
ok = db.execute("PRAGMA integrity_check").fetchone()[0]
assert ok == "ok", f"integrity check failed: {ok}"
tables = [r[0] for r in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
assert tables, "backup contains no tables"
print("    integrity: ok")
for t in tables:
    n = db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"    {t}: {n} rows")
db.close()
PYEOF

# ---- 3a. Drill: stop here, leave the evidence
if [ "$DRILL" = 1 ]; then
  echo "==> DRILL OK — restored copy verified at $WORK/$DB_NAME (delete the dir when done)"
  exit 0
fi

# ---- 3b. Restore into a plain directory
if [ -n "$TARGET_DIR" ]; then
  mkdir -p "$TARGET_DIR"
  install -m 600 "$WORK/$DB_NAME" "$TARGET_DIR/$DB_NAME"
  rm -f "$TARGET_DIR/$DB_NAME-wal" "$TARGET_DIR/$DB_NAME-shm"
  echo "==> Restored to $TARGET_DIR/$DB_NAME (stale -wal/-shm removed)"
  rm -rf "$WORK"
  exit 0
fi

# ---- 3c. Full restore into the live docker volume (on the box)
cd "$APP_DIR"
[ -f docker-compose.yml ] || { echo "$APP_DIR/docker-compose.yml not found — is this the box?"; exit 1; }

if [ "$PRE_BACKUP" = 1 ]; then
  echo "==> Safety net: backing up the CURRENT database first (--no-pre-backup skips)"
  bash "$APP_DIR/infra/backup.sh"
fi

STAMP=$(date -u +%Y-%m-%dT%H-%M-%SZ)
echo "==> Stopping api"
docker compose stop api

echo "==> Swapping the database inside the state volume"
# `compose run` mounts the same state volume the api service uses (uid 1000
# owns it, matching the image's USER app). The old db is kept, timestamped,
# next to the new one; the -wal/-shm files MUST go so SQLite cannot replay a
# WAL that belongs to the old database over the restored file.
docker compose run --rm --no-deps -v "$WORK:/restore:ro" api sh -c "
  set -e
  cd /app/state
  if [ -f $DB_NAME ]; then cp -p $DB_NAME $DB_NAME.pre-restore-$STAMP; fi
  rm -f $DB_NAME-wal $DB_NAME-shm
  cp /restore/$DB_NAME $DB_NAME
  echo '    swapped; previous db kept as $DB_NAME.pre-restore-$STAMP'
"

echo "==> Starting api"
docker compose up -d api

ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' backend/.env 2>/dev/null | cut -d= -f2- || true)
echo "==> Waiting for /api/health"
for i in $(seq 1 45); do
  if curl -fsS -H "X-Origin-Verify: $ORIGIN_SECRET" http://localhost/api/health >/dev/null 2>&1; then
    echo "==> RESTORE OK — api is healthy. Restored from s3://$BUCKET/$KEY"
    rm -rf "$WORK"
    exit 0
  fi
  sleep 2
done
echo "RESTORE FAILED HEALTH CHECK — api did not come up in 90s."
echo "The previous database is preserved in the volume as $DB_NAME.pre-restore-$STAMP."
docker compose ps -a
exit 1
