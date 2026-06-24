#!/usr/bin/env python3
"""
BRAVO agent bridge — host-side client (run by the Operon agent).

Submits a command into the in-container watcher's mailbox and blocks until the
result file appears, then prints it. The watcher (agent_runner.py) must be
running inside the container.

Usage:
    python3 bridge_client.py "python3 manage.py showmigrations Server | tail"
    python3 bridge_client.py --cwd /usr/src/BRAVO --timeout 120 "pytest -q"
    python3 bridge_client.py --status        # check the watcher heartbeat
"""
import argparse, json, os, sys, time, uuid

BASE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(BASE, "inbox")
OUTBOX = os.path.join(BASE, "outbox")


def _ensure():
    for d in (INBOX, OUTBOX):
        os.makedirs(d, exist_ok=True)


def status():
    p = os.path.join(OUTBOX, "_status.json")
    if not os.path.exists(p):
        print("NO HEARTBEAT — watcher not running (no _status.json).")
        return 3
    with open(p) as f:
        s = json.load(f)
    age = "?"
    try:
        from datetime import datetime, timezone
        lp = datetime.fromisoformat(s["last_poll"])
        age = round((datetime.now(timezone.utc) - lp).total_seconds(), 1)
    except Exception:
        pass
    print(json.dumps({**s, "heartbeat_age_s": age}, indent=2))
    return 0


def submit(cmd, cwd=None, timeout=None, wait=600, poll=0.5):
    _ensure()
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    job = {"id": jid, "cmd": cmd}
    if cwd:
        job["cwd"] = cwd
    if timeout:
        job["timeout"] = int(timeout)
    tmp = os.path.join(INBOX, jid + ".job.tmp")
    final = os.path.join(INBOX, jid + ".job")
    with open(tmp, "w") as f:
        json.dump(job, f)
    os.replace(tmp, final)  # atomic: watcher never sees a partial file

    out = os.path.join(OUTBOX, jid + ".out")
    t0 = time.time()
    while time.time() - t0 < wait:
        if os.path.exists(out):
            with open(out) as f:
                res = json.load(f)
            print(f"--- job {jid}  rc={res['rc']}  {res['duration_s']}s"
                  + ("  [TIMED OUT]" if res.get("timed_out") else ""))
            sys.stdout.write(res["output"])
            if res["output"] and not res["output"].endswith("\n"):
                sys.stdout.write("\n")
            return res["rc"]
        time.sleep(poll)
    print(f"--- job {jid}: no result after {wait}s (is the watcher alive? "
          f"run --status). The job may still be running in-container.")
    return 4


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", help="shell command to run in-container")
    ap.add_argument("--cwd", default=None)
    ap.add_argument("--timeout", default=None, help="in-container job timeout (s)")
    ap.add_argument("--wait", default=600, type=float, help="host-side wait for result (s)")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        sys.exit(status())
    if not a.cmd:
        ap.error("provide a command, or --status")
    sys.exit(submit(a.cmd, cwd=a.cwd, timeout=a.timeout, wait=a.wait))
