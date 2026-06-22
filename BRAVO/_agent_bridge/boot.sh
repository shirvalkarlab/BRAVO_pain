#!/bin/bash
# BRAVO agent bridge — container boot wrapper (DEV ONLY, launched by
# docker-compose.override.yml). Starts the in-container command watcher in the
# background, then execs the normal bravo-server startup (nginx + migrate +
# gunicorn). The watcher survives gunicorn --reload because it is a separate
# process; a container restart relaunches it fresh.
#
# The watcher launch is best-effort: if it fails, startup still proceeds so the
# app is never blocked by the dev bridge.
set -u

BRIDGE=/usr/src/BRAVO/_agent_bridge
mkdir -p "$BRIDGE/logs" "$BRIDGE/inbox" "$BRIDGE/outbox" "$BRIDGE/processed" 2>/dev/null || true

if [ -f "$BRIDGE/agent_runner.py" ]; then
  # nohup + & so it outlives this shell; log to a boot log on the bind mount.
  nohup python3 "$BRIDGE/agent_runner.py" \
      >> "$BRIDGE/logs/runner.boot.log" 2>&1 &
  echo "[bridge] agent_runner launched (pid $!)"
else
  echo "[bridge] agent_runner.py not found at $BRIDGE — skipping (app still starts)"
fi

# --- normal bravo-server startup (mirrors docker-compose.yml base command) ---
env >> /etc/environment
service nginx start
python3 manage.py migrate
exec gunicorn BRAVO.asgi:application -k uvicorn.workers.UvicornWorker -w "$(nproc)" \
  -b 0.0.0.0:27286 --timeout 600 --graceful-timeout 30 --reload \
  --access-logfile - --error-logfile -
