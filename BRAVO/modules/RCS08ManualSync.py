"""Coordinate manual RCS08 sync requests through shared appliance storage."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from uuid import uuid4

from filelock import FileLock


STORAGE_PATH = Path(os.environ.get("DATASERVER_PATH", "/usr/src/BRAVO/BRAVOStorage"))
ACTIVE_STATUSES = frozenset({"queued", "running"})


class ManualSyncAlreadyActive(RuntimeError):
    def __init__(self, state: dict):
        super().__init__("An RCS08 sync is already queued or running.")
        self.state = state


def _paths() -> tuple[Path, Path]:
    state_path = STORAGE_PATH / "sync-state" / "rcs08-manual.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    return state_path, state_path.with_suffix(".lock")


def scheduler_lock() -> FileLock:
    state_path, _ = _paths()
    return FileLock(str(state_path.parent / "rcs08-scheduler.lock"), timeout=0)


def _read_unlocked(state_path: Path) -> dict:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "idle"}
    return payload if isinstance(payload, dict) else {"status": "idle"}


def _write_unlocked(state_path: Path, payload: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, state_path)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def public_state(state: dict) -> dict:
    allowed = {
        "request_id",
        "status",
        "requested_at_utc",
        "started_at_utc",
        "finished_at_utc",
        "results",
        "error",
    }
    return {key: value for key, value in state.items() if key in allowed}


def queue_request(requested_by: str) -> dict:
    state_path, lock_path = _paths()
    with FileLock(str(lock_path)):
        current = _read_unlocked(state_path)
        if current.get("status") in ACTIVE_STATUSES:
            raise ManualSyncAlreadyActive(public_state(current))
        queued = {
            "request_id": uuid4().hex,
            "status": "queued",
            "requested_at_utc": _now(),
            "requested_by": requested_by,
        }
        _write_unlocked(state_path, queued)
    return public_state(queued)


def get_state() -> dict:
    state_path, lock_path = _paths()
    with FileLock(str(lock_path)):
        return public_state(_read_unlocked(state_path))


def claim_request() -> dict | None:
    state_path, lock_path = _paths()
    with FileLock(str(lock_path)):
        current = _read_unlocked(state_path)
        if current.get("status") != "queued":
            return None
        current["status"] = "running"
        current["started_at_utc"] = _now()
        _write_unlocked(state_path, current)
        return current


def complete_request(request_id: str, results: dict) -> None:
    _finish_request(request_id, status="completed", results=results)


def fail_request(request_id: str, error: str) -> None:
    _finish_request(request_id, status="failed", error=error[:1000])


def _finish_request(request_id: str, **updates) -> None:
    state_path, lock_path = _paths()
    with FileLock(str(lock_path)):
        current = _read_unlocked(state_path)
        if current.get("request_id") != request_id:
            return
        current.update(updates)
        current["finished_at_utc"] = _now()
        _write_unlocked(state_path, current)


def fail_interrupted_request() -> None:
    """Release a request left running when the scheduler process restarted."""
    state_path, lock_path = _paths()
    with FileLock(str(lock_path)):
        current = _read_unlocked(state_path)
        if current.get("status") != "running":
            return
        current.update(
            {
                "status": "failed",
                "finished_at_utc": _now(),
                "error": "The sync scheduler restarted before this request completed. Please retry.",
            }
        )
        _write_unlocked(state_path, current)
