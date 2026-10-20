#!/bin/sh
set -eu
# Explicit operator action only; never launched at web-server startup.
exec timeout --signal=TERM --kill-after=10s "${SAVED_ANSWERS_REFRESH_PASS_LIMIT_SECONDS:-3600}s" python -m modules.ClosedLoopDeployment.refresh_saved_answers "$@"
