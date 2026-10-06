"""Whole answers saved on the server, under everything that can change them (the PI, 2026-10-04,
decision 423: "save report and summary on the server").

WHY. The Closed-Loop report (about 22 s) and the deployment summary (about 9 s) were worked out
afresh on every request, in whichever worker took it, and kept only in the browser tab that asked.
Going back to a band, or a second reader asking for it, paid the whole cost again.

WHAT KEEPS A SAVED ANSWER CORRECT. It is filed under a label built from:

* the request itself (band, pain score, matching settings -- everything the page sends);
* the data fingerprints the caller supplies: the recordings, the stimulation-settings files, the
  pain reports (fetched fresh on every request, so a new or corrected rating changes the label),
  the clinic sheets, and the stored tables the answer reads;
* `code_digest()`: the analysis code itself, so any edit to it makes every saved answer miss.

These answers depend on pain ratings, and that is allowed: the project's rule (CLAUDE.md §7.5)
keeps ratings out of products derived from RECORDINGS alone, because a rating saved there goes
stale with no symptom. Here the pain reports are in the label, so a changed rating is a miss.

An answer that is not available is never saved. Fields named `volatile` (read fresh each time,
such as the band grid inside the report) are left out of the saved copy and attached on serving.
Every answer carries `saved_answer`: whether it was served, and when it was written.
"""
import hashlib
import json
import os
import threading

from . import store as _store

#: The analysis code the label covers: every module file but tests and the scratch area.
_SKIP_DIRS = {"tests", "__pycache__", "_agent_bridge", "node_modules"}
#: The refresh job's own files decide WHICH answers are worked out ahead, never what is in one (the
#: request is in the label already), so editing them keeps every saved answer (decision 464).
_SKIP_FILES = {"refresh_saved_answers.py", "all_band_requests.py"}
_CODE_DIGEST = {}
_CODE_DIGEST_LOCK = threading.Lock()

#: Bumped when what is saved, or how the label is built, changes.
FORMAT = "saved_answers_v1"


def _modules_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def code_digest(root=None, *, cache=True):
    """A fingerprint of every analysis source file under ``root`` (the modules folder): their
    paths and contents, tests excluded. Worked out once per process unless ``cache`` is False; a
    reload of the server (which follows every code change) starts new processes."""
    root = str(root or _modules_root())
    if cache:
        with _CODE_DIGEST_LOCK:
            hit = _CODE_DIGEST.get(root)
        if hit is not None:
            return hit
    h = hashlib.blake2b(digest_size=16)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if not name.endswith(".py") or name.startswith("test_") or name in _SKIP_FILES:
                continue
            path = os.path.join(dirpath, name)
            h.update(os.path.relpath(path, root).encode("utf8"))
            try:
                with open(path, "rb") as fh:
                    h.update(fh.read())
            except OSError:
                h.update(b"<unreadable>")
    out = h.hexdigest()
    if cache:
        with _CODE_DIGEST_LOCK:
            _CODE_DIGEST[root] = out
    return out


def label(kind, participant_uid, inputs):
    """The signature an answer is saved under (see the module docstring)."""
    blob = json.dumps(inputs, sort_keys=True, default=str)
    return (FORMAT, str(kind), str(participant_uid), code_digest(),
            hashlib.blake2b(blob.encode("utf8"), digest_size=20).hexdigest())


def serve_or_build(kind, participant_uid, inputs, build, *, writer, volatile=(), refresh=None,
                   provenance=None, root=None):
    """The saved answer for ``inputs`` when there is one, otherwise ``build()``'s, saved when it is
    available. ``refresh()`` returns the ``volatile`` fields, worked out fresh, for a served answer."""
    sig = label(kind, participant_uid, inputs)

    def _served():
        got = _store.load(kind, participant_uid, sig, root=root)
        if got is None:
            return None
        out = dict(got)
        if volatile and refresh is not None:
            out.update(refresh() or {})
        stamp = _store.read_stamp(kind, participant_uid, sig, root=root) or {}
        out["saved_answer"] = {"served": True, "written_utc": stamp.get("written_utc"),
                               "key": _store.product_key(kind, participant_uid, sig)}
        return out

    hit = _served()
    if hit is not None:
        return hit
    # ONE BUILD AT A TIME PER ANSWER (decision 425): a request arriving while another worker builds
    # the same answer (a neighbour being pre-computed, then clicked) waits for it and is served,
    # instead of doing the same 20 s of work twice. Redis down or a long wait: built as before.
    from . import locks as _locks
    name = "cachestore:build:%s:%s:%s" % (kind, participant_uid, _store.signature_key(sig))
    with _locks.build_lock(name, ttl_s=BUILD_LOCK_TTL_S, wait_s=BUILD_LOCK_WAIT_S,
                           ready=lambda: _store.read_stamp(kind, participant_uid, sig,
                                                           root=root) is not None) as lk:
        if lk.role == "served":
            hit = _served()
            if hit is not None:
                return hit
        return _build_and_save(kind, participant_uid, sig, inputs, build, writer=writer,
                               volatile=volatile, provenance=provenance, root=root)


#: How long one answer's build may hold its lock, and how long another request waits for it.
BUILD_LOCK_TTL_S = 300.0
BUILD_LOCK_WAIT_S = 240.0


def _build_and_save(kind, participant_uid, sig, inputs, build, *, writer, volatile, provenance,
                    root):
    out = build()
    if isinstance(out, dict) and out.get("available") is True:
        saved = {k: v for k, v in out.items() if k not in set(volatile) and k != "saved_answer"}
        _store.store(kind, participant_uid, sig, saved, writer=writer,
                     provenance=list(provenance or []), trigger="request", root=root,
                     extra={"inputs": {k: (v if isinstance(v, (str, int, float, bool)) or v is None
                                           else str(v)[:200]) for k, v in sorted(inputs.items())}})
    if isinstance(out, dict):
        out = dict(out)
        out["saved_answer"] = {"served": False, "written_utc": None,
                               "key": _store.product_key(kind, participant_uid, sig)}
    return out
