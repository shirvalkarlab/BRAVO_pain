#!/bin/bash
# Every 10 minutes, work the remembered band answers out again for any participant whose data
# changed (decision 435, the PI 2026-10-04: "yes do 3b"). Started by boot.sh.
#
# The job (`python3 -m modules.ClosedLoopDeployment.refresh_saved_answers`) compares each participant's data
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
#   SAVED_ANSWERS_REFRESH_PASS_LIMIT_SECONDS=3600    a pass still running after this is stopped
set -u

BRAVO_DIR=/usr/src/BRAVO
LOG="$BRAVO_DIR/_agent_bridge/logs/saved_answers_refresh.log"
LOCK="$BRAVO_DIR/_agent_bridge/logs/.saved_answers_refresh.pid"
INTERVAL="${SAVED_ANSWERS_REFRESH_INTERVAL_SECONDS:-600}"
FIRST_DELAY="${SAVED_ANSWERS_REFRESH_FIRST_DELAY_SECONDS:-300}"
WORKERS="${SAVED_ANSWERS_REFRESH_WORKERS:-8}"
PASS_LIMIT="${SAVED_ANSWERS_REFRESH_PASS_LIMIT_SECONDS:-3600}"   # 60 min since every band is worked out (decision 463)

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
ERR="$BRAVO_DIR/_agent_bridge/logs/.saved_answers_refresh.stderr"
while true; do
  cd "$BRAVO_DIR" || { sleep "$INTERVAL"; continue; }
  # As a module from the code root: run by its path, the job's folder would come first on Python's
  # path and its `types.py` would hide the standard library's (every pass failed that way at first).
  # The job's JSON lines (one per participant) reach the log; on a failure, its last error lines.
  # A pass takes under a minute; one that locked up ran 6.5 hours (2026-10-05). Past the time limit
  # it is stopped, and its processes with it, and the next pass starts on time.
  OUT="$(timeout --kill-after=30 "$PASS_LIMIT" \
         python3 -B -W ignore -m modules.ClosedLoopDeployment.refresh_saved_answers --all \
         --workers "$WORKERS" 2> "$ERR")"
  RC=$?
  printf '%s\n' "$OUT" | grep '^{' >> "$LOG"
  if [ "$RC" -eq 124 ] || [ "$RC" -eq 137 ]; then
    say "PASS STOPPED: still running after the ${PASS_LIMIT}s limit"
  elif [ "$RC" -ne 0 ]; then
    say "PASS FAILED (exit $RC); its last error lines:"
    grep -v ' DEBUG ' "$ERR" | tail -n 20 >> "$LOG"
  elif ! printf '%s\n' "$OUT" | grep -q '^{'; then
    say "pass finished: no participant has remembered requests yet"
  fi
  sleep "$INTERVAL"
done
