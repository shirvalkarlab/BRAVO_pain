#!/bin/bash
# Daily at 2 pm California time: bring all the new data in (decision 473). Cron starts this at 21:00
# and 22:00 UTC; it runs only in the start that falls at 14:00 in Los Angeles, so daylight saving
# needs no edit. Pass --now to skip that check.
#
#   1. the clinic sheets from Google Drive (sync_clinic_sheets);
#   2. new Percept exports from Dropbox (ingest_new_exports.sh): a dry run, and if anything is new a
#      database backup, then the ingest;
#   3. the daily live-record tests.
# Steps 1 and 2 write under a note (_agent_bridge/.ingest_running) that makes the server's 10-minute
# loop wait, so it rebuilds everything once, on all of today's new data. The rebuild itself (heat
# maps, stability column, session-report summary, the pages' answers) is the loop's job, not this
# script's; it also catches what arrives without this script: pain ratings, code, hand uploads.
#
# One run at a time (lock); every step has a time limit. The log masks file names (patient names).
set -uo pipefail

REPO=/media/volume/pnlstore/BRAVO_pain
LOGDIR=/media/volume/pnlstore/ingest_logs
BACKUPS=/media/volume/pnlstore/backups
INGEST="$REPO/BRAVO/_agent_bridge/ingest_new_exports.sh"
NOTE="$REPO/BRAVO/_agent_bridge/.ingest_running"
C="docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1"
PARTICIPANT=2e3c75c00d7f4f37b53a048d195f11da          # RCS08: the clinic-sheet folder is its
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
mask() { sed -E 's/[^ /"]*\.(json|xlsx)/<file>.\1/g'; }
say() { echo "$(date -u '+%F %T') UTC: $*" >>"$LOG"; }

say "start"
touch "$NOTE"; trap 'rm -f "$NOTE"' EXIT

# 1. Clinic sheets. Exit 2: no signed-in Google client; exit 1: a sheet could not be fetched (its
# previous copy is kept). Either way the exports still come in.
timeout --kill-after=30 900 $C python3 manage.py sync_clinic_sheets --participant "$PARTICIPANT" --json \
  2>/dev/null | grep '^{' | mask >>"$LOG"
say "clinic-sheet sync finished, exit ${PIPESTATUS[0]}"

# 2. Exports.
DRY=$(timeout 1800 bash "$INGEST" 2>&1)
echo "$DRY" | mask >>"$LOG"
NEW=$(echo "$DRY" | sed -nE 's/^ *NEW to ingest *: *([0-9]+).*/\1/p')
if [ -z "$NEW" ]; then
  say "EXPORT DRY RUN GAVE NO COUNT; nothing ingested (see above)"
elif [ "$NEW" = "0" ]; then
  say "no new exports"
else
  DUMP="$BACKUPS/bravo_db_before_daily_ingest_$(date -u +%Y-%m-%d).sql.gz"
  say "$NEW new exports; backing up the database to $(basename "$DUMP")"
  if ! timeout 1800 docker exec bravo_pain-mysql-1 sh -c \
       'mysqldump --single-transaction -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" 2>/dev/null' \
       | gzip >"$DUMP" || [ "$(stat -c %s "$DUMP")" -lt 10000000 ]; then
    say "BACKUP FAILED or too small ($(stat -c %s "$DUMP" 2>/dev/null) bytes); nothing ingested"
  else
    say "backup $(stat -c %s "$DUMP") bytes"
    timeout 18000 bash "$INGEST" --ingest 2>&1 | mask >>"$LOG"
    say "ingest finished, exit ${PIPESTATUS[0]}"
  fi
fi
rm -f "$NOTE"
say "data in; the 10-minute loop rebuilds within 10 minutes if anything changed"

# 3. The live-record tests (read the live RCS08 record through the real service, about a minute).
LIVE=$(timeout --kill-after=30 1800 $C sh _agent_bridge/run_both_suites.sh --live 2>&1)
say "live tests: $(printf '%s' "$LIVE" | tr '\n' ' ' | cut -c1-400)"
if printf '%s' "$LIVE" | grep -q -E ' failed| error|FAIL=[1-9]'; then
  say "LIVE TESTS FINISHED WITH FAILURES: see _agent_bridge/_suite_logs/host_live.log and container_live.log"
fi

find "$BACKUPS" -name 'bravo_db_before_daily_ingest_*.sql.gz' -mtime +30 -delete
find "$LOGDIR" -name 'daily_ingest_*.log' -mtime +90 -delete
say "done"
