#!/bin/bash
# Daily: copy new Percept exports from Dropbox and ingest them (ingest_new_exports.sh), at 2 pm
# California time. Cron starts this at 21:00 and 22:00 UTC; it runs only in the start that falls at
# 14:00 in Los Angeles, so daylight saving needs no edit. Pass --now to skip that check.
#
# Order: dry run; if anything is new, back up the database, then ingest. One run at a time (lock),
# whole run limited to 5 hours. The log masks export file names (they carry the patient's name).
set -uo pipefail

REPO=/media/volume/pnlstore/BRAVO_pain
LOGDIR=/media/volume/pnlstore/ingest_logs
BACKUPS=/media/volume/pnlstore/backups
INGEST="$REPO/BRAVO/_agent_bridge/ingest_new_exports.sh"
export PATH="$HOME/bin:/usr/local/bin:/usr/bin:/bin"

if [ "${1:-}" != "--now" ] && [ "$(TZ=America/Los_Angeles date +%H)" != "14" ]; then
  exit 0
fi

mkdir -p "$LOGDIR"
LOG="$LOGDIR/daily_ingest_$(date -u +%Y-%m-%d).log"
exec 9>"$LOGDIR/.daily_ingest.lock"
if ! flock -n 9; then
  echo "$(date -u '+%F %T') UTC: previous run still going; skipped" >>"$LOG"
  exit 0
fi
mask() { sed -E 's/[^ /]*\.json/<export>.json/g'; }
say() { echo "$(date -u '+%F %T') UTC: $*" >>"$LOG"; }

say "start"
DRY=$(timeout 1800 bash "$INGEST" 2>&1)
echo "$DRY" | mask >>"$LOG"
NEW=$(echo "$DRY" | sed -nE 's/^ *NEW to ingest *: *([0-9]+).*/\1/p')
if [ -z "$NEW" ]; then say "dry run gave no count; stopped (see above)"; exit 1; fi
if [ "$NEW" = "0" ]; then say "nothing new"; exit 0; fi

DUMP="$BACKUPS/bravo_db_before_daily_ingest_$(date -u +%Y-%m-%d).sql.gz"
say "$NEW new exports; backing up the database to $(basename "$DUMP")"
if ! timeout 1800 docker exec bravo_pain-mysql-1 sh -c \
     'mysqldump --single-transaction -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" 2>/dev/null' \
     | gzip >"$DUMP" || [ "$(stat -c %s "$DUMP")" -lt 10000000 ]; then
  say "BACKUP FAILED or too small ($(stat -c %s "$DUMP" 2>/dev/null) bytes); nothing ingested"
  exit 1
fi
say "backup $(stat -c %s "$DUMP") bytes"

timeout 18000 bash "$INGEST" --ingest 2>&1 | mask >>"$LOG"
say "ingest finished, exit ${PIPESTATUS[0]}"
find "$BACKUPS" -name 'bravo_db_before_daily_ingest_*.sql.gz' -mtime +30 -delete
find "$LOGDIR" -name 'daily_ingest_*.log' -mtime +90 -delete
