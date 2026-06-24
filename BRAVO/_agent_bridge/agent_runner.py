#!/usr/bin/env python3
"""
BRAVO agent bridge — in-container command watcher.

Runs INSIDE the bravo-server container. Polls a mailbox directory that lives on
the ./BRAVO bind mount (host: ~/dev/BRAVO_pain/BRAVO/_agent_bridge, container:
/usr/src/BRAVO/_agent_bridge), so it is a shared filesystem with the host. The
Operon agent (which cannot reach the Docker socket or host ports) drops job
files here; this watcher executes them in the container and writes results back.

Launch (one command, from ~/dev/BRAVO_pain on the host):
    docker compose exec -d bravo-server python3 /usr/src/BRAVO/_agent_bridge/agent_runner.py

It runs until the container stops. Stdlib only.

Protocol
--------
Job   (host -> container):  inbox/<id>.job   JSON {id, cmd, cwd?, timeout?}
                            written as <id>.job.tmp then atomically renamed.
Result(container -> host):  outbox/<id>.out  JSON {id, rc, output, timed_out,
                            duration_s, started, finished}
                            written as <id>.out.tmp then atomically renamed.
Heartbeat:                  outbox/_status.json  {pid, started, last_poll,
                            jobs_done, alive}
"""
import json, os, signal, subprocess, sys, time, traceback
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(BASE, "inbox")
OUTBOX = os.path.join(BASE, "outbox")
PROCESSED = os.path.join(BASE, "processed")
LOGS = os.path.join(BASE, "logs")
DEFAULT_CWD = "/usr/src/BRAVO"
POLL_S = 1.0
DEFAULT_TIMEOUT = 1800  # 30 min ceiling per job

os.umask(0)  # bind-mounted files must be host-readable regardless of UID mapping


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs():
    for d in (INBOX, OUTBOX, PROCESSED, LOGS):
        os.makedirs(d, mode=0o777, exist_ok=True)
        try:
            os.chmod(d, 0o777)
        except OSError:
            pass


def _atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


def _log(msg):
    line = f"[{_utc()}] {msg}\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    try:
        with open(os.path.join(LOGS, "runner.log"), "a") as f:
            f.write(line)
    except OSError:
        pass


def _heartbeat(jobs_done, alive=True):
    _atomic_write_json(os.path.join(OUTBOX, "_status.json"), {
        "pid": os.getpid(),
        "started": STARTED,
        "last_poll": _utc(),
        "jobs_done": jobs_done,
        "alive": alive,
        "base": BASE,
    })


def _run_job(job):
    cmd = job["cmd"]
    cwd = job.get("cwd") or DEFAULT_CWD
    timeout = int(job.get("timeout") or DEFAULT_TIMEOUT)
    started = _utc()
    t0 = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        rc = proc.returncode
        output = proc.stdout
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rc = 124
        output = (e.output or "") + f"\n[bridge] TIMEOUT after {timeout}s"
    except Exception as e:  # never let a bad job kill the loop
        rc = 255
        output = f"[bridge] runner error: {e}\n{traceback.format_exc()}"
    return {
        "id": job["id"],
        "rc": rc,
        "output": output,
        "timed_out": timed_out,
        "duration_s": round(time.time() - t0, 3),
        "started": started,
        "finished": _utc(),
        "cwd": cwd,
    }


def _claim(job_path):
    """Atomically claim a job by renaming into processed/ before running, so a
    second runner (or a restart) never double-executes it."""
    claimed = os.path.join(PROCESSED, os.path.basename(job_path))
    try:
        os.rename(job_path, claimed)
        return claimed
    except OSError:
        return None


STARTED = _utc()
_running = True


def _stop(signum, frame):
    global _running
    _running = False


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    _ensure_dirs()
    _log(f"agent_runner up pid={os.getpid()} base={BASE}")
    jobs_done = 0
    _heartbeat(jobs_done)
    while _running:
        try:
            jobs = sorted(
                (f for f in os.listdir(INBOX) if f.endswith(".job")),
                key=lambda f: os.path.getmtime(os.path.join(INBOX, f)),
            )
        except FileNotFoundError:
            _ensure_dirs()
            jobs = []
        for jf in jobs:
            jpath = os.path.join(INBOX, jf)
            claimed = _claim(jpath)
            if not claimed:
                continue
            try:
                with open(claimed) as f:
                    job = json.load(f)
            except Exception as e:
                _log(f"bad job file {jf}: {e}")
                continue
            jid = job.get("id") or os.path.splitext(jf)[0]
            job["id"] = jid
            _log(f"run {jid}: {str(job.get('cmd'))[:120]}")
            result = _run_job(job)
            _atomic_write_json(os.path.join(OUTBOX, f"{jid}.out"), result)
            jobs_done += 1
            _log(f"done {jid} rc={result['rc']} {result['duration_s']}s")
        _heartbeat(jobs_done)
        time.sleep(POLL_S)
    _heartbeat(jobs_done, alive=False)
    _log("agent_runner stopped")


if __name__ == "__main__":
    main()
