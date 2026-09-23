"""The band chosen on the Closed-Loop page, recorded on the server (the PI's ruling 8, decision 233).

WHY. Until 2026-09-23 the chosen band lived only in the browser that chose it (the page's
`bandCandidateStore.js`, browser storage): another browser, another machine or a cleared browser
opened the page on "No band has been committed", and nothing anywhere recorded which band had been
chosen, when, or by whom. The ruling: record it on the server, and update it whenever a new band
is chosen.

APPEND-ONLY, like the store's ledger (`CacheStore/ledger.py`). A choice adds a row, a clear adds a
row, nothing rewrites or deletes one, and the current band is the newest row. So the table also
answers "which band was chosen on the day this sheet was signed", which a single overwritten value
could not.

WHY RAW STATEMENTS AND NOT A DJANGO MODEL: the ledger's reason. A model needs a migration, and a
migration here is a manual step in the container; the table is created on first use with a
statement that does nothing if it exists.

THE ONE DIFFERENCE FROM THE LEDGER: A FAILED SAVE IS REPORTED. The ledger swallows its failures
because it is bookkeeping. This is the record of a clinical choice, and the page must be able to say
"saved in this browser only" when the server did not take it, so every function returns what
happened, with a reason, and none raises.

Nothing here reads a pain rating or a recording; the band candidate is stored exactly as the page
sent it (after a shape check), so the server copy and the browser copy are the same object.
"""

import datetime as _dt
import json
import logging

_log = logging.getLogger(__name__)

TABLE = "closed_loop_chosen_band"

#: A band candidate is a few hundred bytes; this bound only stops a request from filling the table.
MAX_CANDIDATE_BYTES = 64 * 1024

#: Where a choice came from: the "Choose a band" grid, an uploaded candidate file, or a band held
#: only in the browser from before this record existed, sent to the server once.
SOURCES = ("grid", "upload", "browser_storage")

ENVELOPE_SCHEMA = "bandcandidate_envelope_v1"

_ready = False

_CREATE = {
    "mysql": f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id             BIGINT AUTO_INCREMENT PRIMARY KEY,
            recorded_utc   VARCHAR(40)  NOT NULL,
            committed_at   VARCHAR(40)  NOT NULL,
            participant    VARCHAR(64)  NOT NULL,
            action         VARCHAR(16)  NOT NULL,
            source         VARCHAR(32)      NULL,
            chosen_by      VARCHAR(255)     NULL,
            band_candidate LONGTEXT         NULL,
            KEY idx_participant (participant, id)
        ) CHARACTER SET utf8mb4
    """,
    "sqlite": f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_utc   TEXT NOT NULL,
            committed_at   TEXT NOT NULL,
            participant    TEXT NOT NULL,
            action         TEXT NOT NULL,
            source         TEXT,
            chosen_by      TEXT,
            band_candidate TEXT
        )
    """,
}

_INSERT = f"""
    INSERT INTO {TABLE}
        (recorded_utc, committed_at, participant, action, source, chosen_by, band_candidate)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

_COLS = ("id", "recorded_utc", "committed_at", "participant", "action", "source", "chosen_by",
         "band_candidate")

#: For tests that run the real statements against a database of their own. None means Django's
#: default connection, the production path.
CONNECTION_FACTORY = None


def _connection():
    if CONNECTION_FACTORY is not None:
        try:
            return CONNECTION_FACTORY()
        except Exception:                                        # noqa: BLE001
            return None
    try:
        from django.db import connection
        _ = connection.vendor
        return connection
    except Exception:                                            # noqa: BLE001
        return None


def _placeholder(conn, sql):
    return sql.replace("%s", "?") if conn.vendor == "sqlite" else sql


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ensure_table():
    """(connection, None) when the table is usable, else (None, reason)."""
    global _ready
    conn = _connection()
    if conn is None:
        return None, "no database is reachable from the server"
    if _ready:
        return conn, None
    create = _CREATE.get(getattr(conn, "vendor", None))
    if create is None:
        return None, f"no table definition for the {getattr(conn, 'vendor', '?')} database"
    try:
        with conn.cursor() as cur:
            cur.execute(create)
        _ready = True
        return conn, None
    except Exception as exc:                                     # noqa: BLE001
        _log.warning("chosen band: could not create %s", TABLE, exc_info=True)
        return None, f"the record table could not be created ({exc!r})"


def _append(participant_uid, action, *, committed_at, source, chosen_by, band_candidate):
    conn, reason = _ensure_table()
    if conn is None:
        return {"saved": False, "reason": reason, "record": None}
    recorded = _now_iso()
    row = [recorded, str(committed_at or recorded), str(participant_uid), action, source,
           (str(chosen_by)[:255] if chosen_by else None),
           (json.dumps(band_candidate, sort_keys=True) if band_candidate is not None else None)]
    try:
        with conn.cursor() as cur:
            cur.execute(_placeholder(conn, _INSERT), row)
    except Exception as exc:                                     # noqa: BLE001
        _log.warning("chosen band: could not record a %s row for %s", action, participant_uid,
                     exc_info=True)
        return {"saved": False, "reason": f"the server could not record it ({exc!r})",
                "record": None}
    return {"saved": True, "reason": None,
            "record": _as_record(dict(zip(_COLS, [None] + row)))}


def _as_record(d):
    """A table row as the envelope the page already reads from browser storage, plus who, from
    where, and when the server heard of it."""
    try:
        band = json.loads(d.get("band_candidate")) if d.get("band_candidate") else None
    except Exception:                                            # noqa: BLE001
        band = None
    return {"schema": ENVELOPE_SCHEMA, "participant_uid": d.get("participant"),
            "committed_at": d.get("committed_at"), "band_candidate": band,
            "action": d.get("action"), "source": d.get("source"), "chosen_by": d.get("chosen_by"),
            "recorded_utc": d.get("recorded_utc"), "saved_on_server": True}


def _shape_problem(band_candidate):
    if not isinstance(band_candidate, dict):
        return "the band candidate is not an object"
    if not band_candidate.get("contact"):
        return "the band candidate names no sensing contact pair"
    try:
        float(band_candidate.get("center_freq_hz"))
    except (TypeError, ValueError):
        return "the band candidate has no band centre"
    try:
        size = len(json.dumps(band_candidate))
    except (TypeError, ValueError):
        return "the band candidate cannot be written as JSON"
    if size > MAX_CANDIDATE_BYTES:
        return f"the band candidate is too large to record ({size} bytes)"
    return None


def choose(participant_uid, band_candidate, *, chosen_by, source, committed_at=None):
    """Record a chosen band. `{"saved", "reason", "record"}`; never raises.

    `committed_at` is honoured only for a band carried over from browser storage, which keeps the
    time it was actually chosen; any other choice is dated now."""
    if source not in SOURCES:
        return {"saved": False, "reason": f"unknown source {source!r}; expected one of {SOURCES}",
                "record": None}
    problem = _shape_problem(band_candidate)
    if problem:
        return {"saved": False, "reason": problem, "record": None}
    when = str(committed_at) if (source == "browser_storage" and committed_at) else None
    return _append(participant_uid, "chosen", committed_at=when, source=source,
                   chosen_by=chosen_by, band_candidate=band_candidate)


def clear(participant_uid, *, chosen_by):
    """Record that no band is chosen any more. Same return shape as `choose`."""
    return _append(participant_uid, "cleared", committed_at=None, source=None,
                   chosen_by=chosen_by, band_candidate=None)


def history(participant_uid, limit=50):
    """This participant's rows, newest first, as records. Empty when unavailable."""
    conn, _reason = _ensure_table()
    if conn is None:
        return []
    sql = (f"SELECT {', '.join(_COLS)} FROM {TABLE} WHERE participant = %s "
           f"ORDER BY id DESC LIMIT %s")
    try:
        with conn.cursor() as cur:
            cur.execute(_placeholder(conn, sql), [str(participant_uid), int(limit)])
            rows = cur.fetchall()
    except Exception:                                            # noqa: BLE001
        _log.warning("chosen band: could not read the history for %s", participant_uid,
                     exc_info=True)
        return []
    return [_as_record(dict(zip(_COLS, r))) for r in rows]


def current(participant_uid):
    """`{"available", "record", "reason"}`: the band chosen now, or `record` None when none has been
    chosen or the last row is a clear. `available` False means the server could not be asked,
    which the page must not read as "no band chosen"."""
    conn, reason = _ensure_table()
    if conn is None:
        return {"available": False, "record": None, "reason": reason}
    sql = (f"SELECT {', '.join(_COLS)} FROM {TABLE} WHERE participant = %s "
           f"ORDER BY id DESC LIMIT 1")
    try:
        with conn.cursor() as cur:
            cur.execute(_placeholder(conn, sql), [str(participant_uid)])
            row = cur.fetchone()
    except Exception as exc:                                     # noqa: BLE001
        _log.warning("chosen band: could not read the current band for %s", participant_uid,
                     exc_info=True)
        return {"available": False, "record": None,
                "reason": f"the server could not read the record ({exc!r})"}
    if not row:
        return {"available": True, "record": None, "reason": None}
    rec = _as_record(dict(zip(_COLS, row)))
    return {"available": True, "record": rec if rec["action"] == "chosen" else None,
            "reason": None}
