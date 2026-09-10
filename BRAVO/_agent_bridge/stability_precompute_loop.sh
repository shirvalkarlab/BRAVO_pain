#!/bin/bash
# The daily precompute pass (DEV ONLY, started by boot.sh).
#
# THE FILE'S NAME IS NARROWER THAN WHAT IT DOES, and that is deliberate rather than an oversight.
# It began as the stability column's pass (decision 97) and now runs the band-by-length grid for
# EVERY pain score first (open item 7), then the stability column. It is not renamed because
# boot.sh, decision 97 and the environment-variable names all say "stability", and renaming a
# dev-only loop to tidy a name is a chance to break the one line that starts it for no gain.
#
# THE ORDER MATTERS: the sweeps run first, because the stability column is computed for the points
# of a grid that has to exist before it can be asked about.
#
# WHY THIS EXISTS ALONGSIDE THE AFTER-THE-PAGE-LANDS RUN. The PI asked for both: computed in the
# background so whoever opens the page is not held up, AND precomputed off the request path on a
# schedule, so the answer is usually already there before anyone opens anything. The page-triggered
# run only helps the person who happens to open the page first; this one means nobody has to be that
# person.
#
# IT IS CHEAP TO RUN OFTEN, because the key decides whether any work happens (decision 26). A pass
# whose inputs have not moved since the last one loads the stored entry and stops -- measured on
# RCS08 at about 3-5 s per participant against 11-13 s for a real rebuild. That is what makes a daily
# pass over every participant reasonable rather than wasteful.
#
# BEST-EFFORT AND NEVER FATAL. A failure here must not affect the server: the loop logs it, sleeps,
# and tries again on the next pass. `--json` is used so a real scheduler could parse the log; a
# participant with no recordings reports "nothing stored" and is NOT counted as a failure, while a
# run that stopped early and kept the previous answer IS -- that is the case nothing on any page
# would ever show, because the page keeps serving the older answer and looks fine.
#
# Switches, all read from the environment so nothing needs editing to change them:
#   STABILITY_PRECOMPUTE=0                      turn the loop off entirely
#   STABILITY_PRECOMPUTE_INTERVAL_SECONDS=86400 how long between passes (default one day)
#   STABILITY_PRECOMPUTE_FIRST_DELAY_SECONDS=600  wait before the first pass, so container start,
#                                               migrations and the first page loads are not competing
#                                               with a whole-machine job
#   BAND_SWEEP_PRECOMPUTE=0                     skip the every-pain-score half only, and still run
#                                               the stability half
set -u

BRAVO_DIR=/usr/src/BRAVO
# The log carries Django's own DEBUG logging as well as this loop's lines, because the whole
# command's output is redirected into it. The lines that matter are greppable: this loop's own read
# "[stability-precompute <time>] ...", and the command's per-participant results are JSON objects.
LOG="$BRAVO_DIR/_agent_bridge/logs/stability_precompute.log"
LOCK="$BRAVO_DIR/_agent_bridge/logs/.stability_precompute.pid"

INTERVAL="${STABILITY_PRECOMPUTE_INTERVAL_SECONDS:-86400}"
FIRST_DELAY="${STABILITY_PRECOMPUTE_FIRST_DELAY_SECONDS:-600}"

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true

say() { echo "[stability-precompute $(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" >> "$LOG"; }

if [ "${STABILITY_PRECOMPUTE:-1}" = "0" ]; then
  say "switched off by STABILITY_PRECOMPUTE=0; not starting"
  exit 0
fi

# ONE LOOP, NOT SEVERAL. A stacked second loop would mean two whole-machine jobs at once. The lock
# holds a pid and is ignored when that process is gone, so a hard container kill does not wedge it.
if [ -f "$LOCK" ]; then
  OLD_PID="$(cat "$LOCK" 2>/dev/null || echo '')"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    say "another loop is already running (pid $OLD_PID); not starting a second"
    exit 0
  fi
  say "found a stale lock for pid ${OLD_PID:-unknown}; taking it over"
fi
echo "$$" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

say "started (pid $$); first pass in ${FIRST_DELAY}s, then every ${INTERVAL}s"
sleep "$FIRST_DELAY"

while true; do
  say "pass starting"
  cd "$BRAVO_DIR" || { say "cannot enter $BRAVO_DIR; sleeping"; sleep "$INTERVAL"; continue; }

  # EVERY PAIN SCORE, FIRST (open item 7). The pain score is part of the grid's key, so each score
  # is a separate answer and reading a second one has always cost a whole rebuild on the request
  # path. This pass pays for all of them off it. Cheap when nothing has moved, for the same reason
  # the stability half is: the key decides whether any work happens.
  #
  # ITS FAILURE IS REPORTED BUT DOES NOT SKIP THE STABILITY HALF, because the two are independent
  # and a reader denied one of them is worse off than a reader denied neither.
  if [ "${BAND_SWEEP_PRECOMPUTE:-1}" = "0" ]; then
    say "the every-pain-score half is switched off by BAND_SWEEP_PRECOMPUTE=0"
  elif python3 manage.py precompute_band_sweeps --all --json >> "$LOG" 2>&1; then
    say "pain-score pass finished, every participant and score either stored an answer or had nothing to store"
  else
    # Exit status 1 here means at least one grid was COMPUTED and could not be kept -- invisible on
    # the page, which simply rebuilds it on every single request and looks entirely fine.
    say "PAIN-SCORE PASS FINISHED WITH FAILURES — see the lines above for which participant and score"
  fi

  if python3 manage.py compute_stability_grid --all --json >> "$LOG" 2>&1; then
    say "pass finished, every participant either stored an answer or had nothing to store"
  else
    # Exit status 1 means at least one participant computed an answer and could not keep it, or
    # stopped early and kept the previous one. Both are real and both are invisible on the page.
    say "PASS FINISHED WITH FAILURES — see the lines above for which participant"
  fi
  sleep "$INTERVAL"
done
