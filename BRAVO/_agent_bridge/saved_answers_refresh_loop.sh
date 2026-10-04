#!/bin/bash
# Every 10 minutes, work the remembered band answers out again for any participant whose data
# changed (decision 435, the PI 2026-10-04: "yes do 3b"). Started by boot.sh.
#
# The job (`modules/ClosedLoopDeployment/refresh_saved_answers.py`) compares each participant's data
# fingerprint -- recordings, settings files, pain reports fetched fresh from REDCap, clinic sheets,
# code -- with the one of its last pass, and only when it moved replays the requests the pages sent
# (summary, the three Closed-Loop panels, the Closed-Loop report, including those sent ahead), at most
# 8 at once. An unchanged pass costs one pain-report download per participant.
#
# Switches, read from the environment:
#   SAVED_ANSWERS_REFRESH=0                          turn the loop off
#   SAVED_ANSWERS_REFRESH_INTERVAL_SECONDS=600       time between passes
#   SAVED_ANSWERS_REFRESH_FIRST_DELAY_SECONDS=300    wait before the first pass after a start
#   SAVED_ANSWERS_REFRESH_WORKERS=8                  replays at once (never more than 8)
set -u

BRAVO_DIR=/usr/src/BRAVO
LOG="$BRAVO_DIR/_agent_bridge/logs/saved_answers_refresh.log"
LOCK="$BRAVO_DIR/_agent_bridge/logs/.saved_answers_refresh.pid"
INTERVAL="${SAVED_ANSWERS_REFRESH_INTERVAL_SECONDS:-600}"
FIRST_DELAY="${SAVED_ANSWERS_REFRESH_FIRST_DELAY_SECONDS:-300}"
WORKERS="${SAVED_ANSWERS_REFRESH_WORKERS:-8}"

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
say() { echo "[saved-answers-refresh $(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" >> "$LOG"; }

if [ "${SAVED_ANSWERS_REFRESH:-1}" = "0" ]; then
  say "switched off by SAVED_ANSWERS_REFRESH=0; not starting"
  exit 0
fi

# ONE LOOP: a lock holding a pid, ignored when that process is gone.
if [ -f "$LOCK" ]; then
  OLD_PID="$(cat "$LOCK" 2>/dev/null || echo '')"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    say "another loop is already running (pid $OLD_PID); not starting a second"
    exit 0
  fi
fi
echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

say "started (pid $$); first pass in ${FIRST_DELAY}s, then every ${INTERVAL}s, ${WORKERS} replays at once"
sleep "$FIRST_DELAY"
while true; do
  cd "$BRAVO_DIR" || { sleep "$INTERVAL"; continue; }
  # Only the job's JSON lines (one per participant) and failures reach the log.
  if python3 -B -W ignore modules/ClosedLoopDeployment/refresh_saved_answers.py --all \
       --workers "$WORKERS" 2>/dev/null | grep --line-buffered '^{' >> "$LOG"; then
    :
  else
    say "pass finished with no participant line (no remembered requests, or the job failed)"
  fi
  sleep "$INTERVAL"
done
