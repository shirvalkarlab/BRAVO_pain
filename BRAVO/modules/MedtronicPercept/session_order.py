"""The order a folder of Percept exports is ingested in: one at a time, oldest session first (the PI,
2026-10-05; CLAUDE.md section 11). File names need not follow the session, so the order comes from
each export's own top-level `SessionDate`, which is on the tablet's clock (`TabletClock.py`)."""
import json
import os
from datetime import datetime


def _session_time(path):
    try:
        with open(path, "rb") as fh:
            value = json.load(fh).get("SessionDate")
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:                                          # noqa: BLE001 -- unreadable: goes last
        return None


def in_session_order(paths):
    """`paths` oldest session first; a file whose SessionDate cannot be read goes last, in name order."""
    timed = [(_session_time(p), os.path.basename(p), p) for p in paths]
    return [p for t, _, p in sorted(timed, key=lambda r: (r[0] is None, r[0] or 0.0, r[1]))]
