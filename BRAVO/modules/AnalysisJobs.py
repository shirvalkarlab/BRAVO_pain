"""Persistent, deduplicated jobs for expensive read-only analysis responses.

Callers supply the complete input/configuration/permission identity and a callable
returning a JSON dictionary. Repeating that request polls the same job. A changed
identity creates a new job; old results never match new inputs implicitly.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import BoundedSemaphore
import time

from filelock import FileLock, Timeout


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bravo-analysis")
_SLOTS = BoundedSemaphore(8)
_FAILURE_RETRY_SECONDS = 5


def _directory():
    root = Path(os.environ["DATASERVER_PATH"]) / "analysis-jobs"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def _write(path, value):
    # Validate before creating a temporary file. Never publish partial results.
    serialized = json.dumps(value, allow_nan=False, separators=(",", ":"))
    descriptor, temporary = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _pending(job_id, status="queued", busy=False):
    return 202, {"status": status, "job_id": job_id,
                 "message": "Analysis capacity is busy. Please retry shortly." if busy else
                            "Analysis is running. Please retry shortly." if status == "running" else
                            "Analysis is queued. Please retry shortly."}


def _failed(job_id):
    return 500, {"status": "failed", "job_id": job_id,
                 "message": "Analysis could not be completed. Please retry shortly."}


def _finished(saved, job_id):
    if saved.get("status") == "complete" and isinstance(saved.get("payload"), dict):
        return 200, saved["payload"]
    if saved.get("status") == "failed" and time.time() - saved.get("finished_at", 0) < _FAILURE_RETRY_SECONDS:
        return _failed(job_id)
    return None


def _run(path, job_id, job_lock, compute):
    try:
        # One heavy calculation across all server workers. Waiting happens only
        # in the background executor, never in an HTTP request.
        with FileLock(str(path.parent / "compute.lock"), mode=0o600):
            _write(path, {"status": "running", "job_id": job_id})
            payload = compute()
            if not isinstance(payload, dict):
                raise TypeError("Analysis computation must return a JSON dictionary")
            _write(path, {"status": "complete", "job_id": job_id,
                          "finished_at": time.time(), "payload": payload})
    except Exception:
        # Raw exception text may contain data or credentials. Never send it to
        # the client or persist it in a public-facing job status.
        _write(path, {"status": "failed", "job_id": job_id, "finished_at": time.time()})
    finally:
        job_lock.release()
        _SLOTS.release()


def get_or_start(identity: dict, compute) -> tuple[int, dict]:
    """Return cached 200, pending 202, or a failed 500 with a short retry cooldown.

    Saved queued/running flags are advisory: an available job lock always permits
    restart recovery. At most eight jobs are admitted in each worker process.
    The caller must check its input manifest before/after computation and reject
    a result whose scientific inputs changed while it ran.
    """
    canonical = json.dumps(identity, sort_keys=True, allow_nan=False, separators=(",", ":"))
    job_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path = _directory() / (job_id + ".json")
    answer = _finished(_read(path), job_id)
    if answer:
        return answer
    job_lock = FileLock(str(path.with_suffix(".lock")), timeout=0, mode=0o600, thread_local=False)
    try:
        job_lock.acquire()
    except Timeout:
        saved = _read(path)
        return _finished(saved, job_id) or _pending(job_id, "running" if saved.get("status") == "running" else "queued")

    # A completion or another worker's failure may have occurred since first read.
    answer = _finished(_read(path), job_id)
    if answer:
        job_lock.release()
        return answer
    if not _SLOTS.acquire(blocking=False):
        job_lock.release()
        return _pending(job_id, busy=True)
    try:
        _write(path, {"status": "queued", "job_id": job_id})
        _EXECUTOR.submit(_run, path, job_id, job_lock, compute)
    except Exception:
        job_lock.release()
        _SLOTS.release()
        return _failed(job_id)
    return _pending(job_id)
