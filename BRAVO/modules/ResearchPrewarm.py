"""Prepare two inexpensive research views through their actual authenticated API views.

This mirrors ReportCache's APIRequestFactory/resolve pattern: internal Django
view invocation, not an HTTP call and not a mocked service. The API owns request
validation, data/code/permission identity and AnalysisJobs deduplication. Only the
unmodified browser defaults are prepared; candidate bands and parameter grids
remain on demand. Each poll is non-blocking and the supervising worker enforces the nightly cutoff.
"""
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time

from filelock import FileLock, Timeout

log = logging.getLogger(__name__)
POLL_SECONDS = 60
MAX_POLL_SECONDS = 2 * 60 * 60


def default_requests(participant_uid):
    """Exact first-visit request bodies in Biomarkers and StimOptimizer views."""
    return [
        ("queryPainScores", {"ParticipantId": participant_uid}),
        ("queryDataAvailability", {"ParticipantId": participant_uid}),
    ]


def _path(participant_uid):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(participant_uid)):
        raise ValueError("Invalid participant identifier")
    path = Path(os.environ["DATASERVER_PATH"]) / "sync-state" / f"research-prewarm-{participant_uid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, payload):
    descriptor, temporary = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _eligible_users(participant):
    from Server import models
    from modules import Database
    seen = set()
    for user in models.PlatformUser.objects.filter(institute=participant.institute, is_active=1):
        permission = Database.checkAccessPermission(user, participant.uid,
                                                    study_uid=user.configuration.get("ActiveStudy"))
        if not permission:
            continue
        processing, _ = Database.retrieveProcessingSettings(user.configuration)
        identity = json.dumps([processing, permission], sort_keys=True, allow_nan=False)
        if identity not in seen:
            seen.add(identity)
            yield user


def _invoke(user, operation, payload):
    from django.urls import resolve
    from rest_framework.test import APIRequestFactory, force_authenticate
    path = "/api/" + operation
    request = APIRequestFactory().post(path, payload, format="json")
    force_authenticate(request, user=user)
    response = resolve(path).func(request)
    return response.status_code, response.data


def _submit(entry, user):
    try:
        status, payload = _invoke(user, entry["operation"], entry["request"])
        if status == 202:
            entry.update(status="pending", message=payload.get("message", "Research preparation is pending."),
                         job_id=payload.get("job_id"))
        elif status == 200:
            available = payload.get("available", payload.get("availability", True))
            entry.update(status="unavailable" if available is False else "complete",
                         message=(str(payload.get("reason", "This view has insufficient data."))[:500]
                                  if available is False else "Prepared."))
        else:
            entry.update(status="failed", message=f"Research preparation returned HTTP {status}.")
        entry["http_status"] = status
    except Exception:
        log.exception("Research prewarm view failed: %s", entry["operation"])
        entry.update(status="failed", message="Research preparation failed; retry after checking the server log.")


def _summary(state):
    entries = state.get("entries", [])
    pending = any(item["status"] == "pending" for item in entries)
    failed = any(item["status"] == "failed" for item in entries)
    status = ("pending" if pending else "failed" if failed else
              "incomplete" if any(item["status"] == "pending_after_deadline" for item in entries) else
              "complete" if entries else "not_applicable")
    return {"status": status, "configuration_groups": state.get("configuration_groups", 0),
            "views": [{"view": item["operation"], "status": item["status"], "message": item["message"]}
                      for item in entries],
            "scope": "Pain scores and data availability only; full biomarker, optimizer and closed-loop analyses remain on demand.",
            "deadline": state.get("deadline")}


def queue_defaults(participant, *, deadline=None):
    """Queue/reuse default results and return immediately without waiting for fits.

    Permission-equivalent users share preparation, just as their API results do.
    Saved status contains user identifiers internally; returned summaries omit them.
    """
    path = _path(participant.uid)
    try:
        with FileLock(str(path.with_suffix(".lock")), timeout=0):
            now = time.time()
            state = {"participant_uid": participant.uid, "started_at": now,
                     "next_poll_at": now + POLL_SECONDS, "deadline": min(now + MAX_POLL_SECONDS, deadline or now + MAX_POLL_SECONDS),
                     "entries": [], "configuration_groups": 0}
            if state["deadline"] - now < 90:
                return {"status": "skipped_budget", "views": [], "message": "Less than 90 seconds remain; optional research preparation was skipped."}
            for user in _eligible_users(participant):
                state["configuration_groups"] += 1
                for operation, payload in default_requests(participant.uid):
                    entry = {"operation": operation, "request": payload, "user_uid": user.uid}
                    if state["deadline"] - time.time() < 90:
                        entry.update(status="pending_after_deadline", message="Optional preparation skipped because the nightly budget is nearly exhausted.")
                    else:
                        _submit(entry, user)
                    state["entries"].append(entry)
            _write(path, state)
            return _summary(state)
    except Timeout:
        return _summary(_read(path))


def poll_pending():
    """Scheduler heartbeat: refresh due requests once, never sleep or await fits.

    Existing API results recover across restarts. A failed request is reported,
    not automatically retried in a hot loop. The next scheduled/manual preparation
    can retry it. At the deadline, polling stops and the supervisor terminates
    its worker group. Independently started browser jobs are not cancelled.
    """
    from Server import models
    directory = Path(os.environ["DATASERVER_PATH"]) / "sync-state"
    changed = []
    for path in directory.glob("research-prewarm-*.json"):
        try:
            with FileLock(str(path.with_suffix(".lock")), timeout=0):
                state = _read(path)
                pending = [entry for entry in state.get("entries", []) if entry.get("status") == "pending"]
                if not pending or time.time() < state.get("next_poll_at", 0):
                    continue
                before = _summary(state)
                if time.time() >= state["deadline"]:
                    for entry in pending:
                        entry.update(status="pending_after_deadline", message="Preparation window ended; unfinished views remain on demand. The supervised worker stops at its deadline.")
                else:
                    participant = models.Participant.find(uid=state["participant_uid"])
                    users = {user.uid: user for user in _eligible_users(participant)} if participant else {}
                    for entry in pending:
                        if entry["operation"] not in {name for name, _ in default_requests(state["participant_uid"])}:
                            entry.update(status="failed", message="This operation is excluded from nightly preparation and remains on demand.")
                            continue
                        user = users.get(entry["user_uid"])
                        if user is None:
                            entry.update(status="failed", message="The original user configuration is no longer authorized for preparation.")
                        else:
                            _submit(entry, user)
                state["next_poll_at"] = time.time() + POLL_SECONDS
                _write(path, state)
                summary = _summary(state)
                if summary != before:
                    changed.append(summary)
        except Timeout:
            continue
    return changed
