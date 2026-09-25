"""Saved control-analysis results: one JSON file per run, kept, never replaced (2026-09-24).

Layout: `<root>/<participant>/<analysis key>/<run time>.json`. The root is the data server's own
folder (`DATASERVER_PATH`), beside the recordings, because these are records: the cache store keeps
only the newest entry of a kind and can be switched off, which is right for a cache and wrong here.
A file is written to a temporary name and moved into place, so a reader sees a whole run or none.
Only aggregates are saved -- counts, correlations, intervals, date ranges -- never a rating.
"""
import json
import os
import re
from datetime import datetime, timezone

try:
    from . import registry as RG
except ImportError:                                           # pragma: no cover
    import registry as RG


def default_root():
    base = os.environ.get("DATASERVER_PATH") or ""
    return os.path.join(base, "control_analyses") if base else None


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(name))


def save(participant_uid, key, result, *, settings, data_through, data_from=None, reading=None,
         run_at=None, run_by=None, root=None):
    """Save one run; returns the saved record. An analysis the registry does not name is refused."""
    if key not in RG.ANALYSES:
        raise KeyError(f"no control analysis named {key!r}")
    root = root or default_root()
    if not root:
        raise RuntimeError("no data server path to save control analyses under")
    run_at = run_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    a = RG.ANALYSES[key]
    rec = dict(key=key, title=a["title"], page=a["page"], what=a["what"], run_at=run_at,
               run_by=run_by, data_from=data_from, data_through=data_through, settings=settings,
               reading=list(reading or []), result=result)
    d = os.path.join(root, _safe(participant_uid), _safe(key))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, _safe(run_at) + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, sort_keys=True, default=float)
    os.replace(tmp, path)
    return rec


def _runs(participant_uid, key, root):
    d = os.path.join(root, _safe(participant_uid), _safe(key))
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".json"))


def load_newest(participant_uid, key, root=None):
    root = root or default_root()
    runs = _runs(participant_uid, key, root) if root else []
    if not runs:
        return None, 0
    with open(os.path.join(root, _safe(participant_uid), _safe(key), runs[-1])) as f:
        return json.load(f), len(runs)


def page_payload(participant_uid, page, root=None):
    """Every analysis the page shows, in order, each with its newest saved run (or none yet), how
    many runs are kept, what it does and its literature."""
    out = []
    for key, a in sorted(RG.ANALYSES.items(), key=lambda kv: kv[1]["order"]):
        if a["page"] != page:
            continue
        snap, n = load_newest(participant_uid, key, root)
        out.append(dict(key=key, title=a["title"], what=a["what"], literature=a["literature"],
                        snapshot=snap, n_runs=n))
    return {"page": page, "analyses": out}
