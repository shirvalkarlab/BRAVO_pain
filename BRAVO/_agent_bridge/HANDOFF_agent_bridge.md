# Handoff — Operon agent bridge into the bravo-server container

**TL;DR:** The sandboxed Operon agent now has zero-click command execution **inside** the running
`bravo-server` container, and it **auto-starts on every container boot**. You don't need to do
anything — it's wired into `docker-compose.override.yml`.

## Why this exists
The agent's sandbox cannot reach the Docker socket (OrbStack publishes it through a virtualized
path that isn't passed into the sandbox; `.docker`/`.orbstack` access doesn't help — the socket
node simply isn't there) and host localhost ports are blocked. The one bidirectional channel is the
existing dev bind mount `./BRAVO ↔ /usr/src/BRAVO`. The bridge rides that mount.

## How it works
A tiny stdlib watcher (`BRAVO/_agent_bridge/agent_runner.py`) runs **inside** the container and
polls a mailbox dir on the bind mount. The agent drops a job file on the host side; the watcher
runs it in-container (real MySQL, Django, gunicorn env, migrations) and writes the result back.

- **Mailbox:** `BRAVO/_agent_bridge/{inbox,outbox,processed,logs}/` — gitignored (runtime only).
- **Agent's client:** `BRAVO/_agent_bridge/bridge_client.py` (host side).
- **Tracked in git:** `agent_runner.py`, `bridge_client.py`, `boot.sh`, `.gitignore`. Runtime
  mailbox dirs are ignored.

## Auto-start (NEW — the change this session)
`docker-compose.override.yml` (dev layer only — prod image untouched) now sets:
```yaml
    command: ["bash", "/usr/src/BRAVO/_agent_bridge/boot.sh"]
```
`boot.sh` launches the watcher in the background, then **execs the identical base startup**
(`nginx → migrate → gunicorn`, same flags). App behavior is unchanged; the watcher is just
launched first.

**Takes effect on container CREATE, not restart.** `docker compose up -d` (recreate) picks it up;
`docker compose restart` does **not**. Verified this session: after `up -d`, watcher came up as
PID 8, gunicorn as PID 1, from a single command with no manual launch.

## What it changes for you
- **Nothing operationally** — gunicorn runs exactly as before (16 uvicorn workers, `--reload`,
  `--timeout 600`).
- If you ever need to relaunch the watcher manually (e.g. it was killed):
  ```bash
  cd ~/dev/BRAVO_pain && docker compose exec -d bravo-server python3 /usr/src/BRAVO/_agent_bridge/agent_runner.py
  ```
- To check it's alive: the agent reads `_agent_bridge/outbox/_status.json` (heartbeat w/ pid,
  last_poll, jobs_done).

## First real result obtained through it
Migrations on the **live MySQL** are confirmed applied (the prior handoff could only *assume* this,
since the sandbox couldn't reach Docker):
```
[X] 0007_sourcefile_unique_hashed
[X] 0008_recording_content_fingerprint
[X] 0009_sourcefile_device_institute
```

## Two things the live container surfaced (FYI, not yet fixed)
1. **sklearn version skew (correctness risk).** Container runs scikit-learn **1.5.2**, but several
   pickled classifiers (`DecisionTreeClassifier`, `RandomForestClassifier`, `LabelBinarizer`,
   `MLPClassifier`) were saved under **1.6.1**. They load with `InconsistentVersionWarning` —
   cross-version unpickling can silently mispredict. If these are in the pain-biomarker decode
   path, pin sklearn to 1.6.1 in the image or re-fit + re-save under 1.5.2.
2. **Missing static dir.** `STATICFILES_DIRS` references `/usr/src/BRAVO/static`, which doesn't
   exist (`staticfiles.W004`). Harmless for the API.

## Caveat
The bridge is **dev-only** and grants in-container shell execution to whatever can write the
mailbox dir on the bind mount. Fine for local dev; do **not** carry the override `command` or the
`_agent_bridge/` mailbox into any shared/prod deployment.
