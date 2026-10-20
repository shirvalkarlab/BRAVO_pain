"""The append-only ledger of what wrote each stored product, when, and from which inputs.

WHY A DATABASE TABLE AND NOT THE SIDECARS. The sidecar beside each entry answers "what is this
file". The ledger answers questions the sidecars cannot, because a sidecar is deleted when its
entry is superseded:

* Which module wrote this product, and how often has it been rebuilt?
* What was the state of the store on the day a figure was produced?
* When a verdict looks wrong, what did it derive from AT THE TIME, given that the inputs have since
  been swept?

**It is append-only and nothing in the platform updates or deletes a row.** A ledger that could be
rewritten would answer the third question with today's story rather than that day's.

WHY RAW STATEMENTS AND NOT A DJANGO MODEL. A model needs a migration, and a migration on this
platform is a deployment step that has to be run by hand in the container. The table is created on
first use with a statement that does nothing if it already exists, so the ledger starts working the
first time anything is stored and needs no separate step. The cost is that this file writes SQL by
hand; it is a single narrow table with fixed columns, which is the case where that is acceptable.

**A LEDGER OUTAGE MUST NEVER FAIL A PAGE.** Every function here swallows its own exceptions and
returns a value saying it did nothing. Recording that a cache was written is bookkeeping; refusing
to serve a clinician's analysis because the bookkeeping failed would be the wrong trade in every
instance.
"""

import json
import logging

_log = logging.getLogger(__name__)

TABLE = "cache_store_ledger"

#: Set False to turn recording off without touching a call site — used by the tests that run with
#: no database at all, and available as a switch if the table ever needs to be left alone.
ENABLED = True

_ready = False

#: MySQL and SQLite differ on the auto-incrementing key and on the timestamp type, and this project
#: runs MySQL in the container and SQLite when no database configuration file is present. Both are
#: supported because the tests must be runnable without MySQL.
_CREATE = {
    "mysql": f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id            BIGINT AUTO_INCREMENT PRIMARY KEY,
            written_utc   VARCHAR(40)  NOT NULL,
            kind          VARCHAR(64)  NOT NULL,
            participant   VARCHAR(64)      NULL,
            signature_key VARCHAR(48)  NOT NULL,
            writer        VARCHAR(32)      NULL,
            trigger_name  VARCHAR(64)      NULL,
            fmt           VARCHAR(16)      NULL,
            payload_bytes BIGINT           NULL,
            n_recordings  INT              NULL,
            n_inputs      INT              NULL,
            provenance    LONGTEXT         NULL,
            KEY idx_kind_participant (kind, participant),
            KEY idx_written (written_utc)
        ) CHARACTER SET utf8mb4
    """,
    "sqlite": f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            written_utc   TEXT NOT NULL,
            kind          TEXT NOT NULL,
            participant   TEXT,
            signature_key TEXT NOT NULL,
            writer        TEXT,
            trigger_name  TEXT,
            fmt           TEXT,
            payload_bytes INTEGER,
            n_recordings  INTEGER,
            n_inputs      INTEGER,
            provenance    TEXT
        )
    """,
}

_INSERT = f"""
    INSERT INTO {TABLE}
        (written_utc, kind, participant, signature_key, writer, trigger_name, fmt,
         payload_bytes, n_recordings, n_inputs, provenance)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


#: A callable returning a connection-like object (`.vendor`, `.cursor()` as a context manager),
#: for tests that must exercise the real statements against a database of their own. None means
#: Django's default connection, which is the production path.
CONNECTION_FACTORY = None


def _connection():
    """Django's default connection, or None when there is no configured database."""
    if CONNECTION_FACTORY is not None:
        try:
            return CONNECTION_FACTORY()
        except Exception:
            return None
    try:
        from django.db import connection
        # Touching the vendor forces the connection to be established, which is what makes a
        # missing database show up here as an exception rather than at the first statement.
        _ = connection.vendor
        return connection
    except Exception:
        return None


def _placeholder(conn, sql):
    """SQLite's driver wants a question mark where MySQL's wants a percent-s."""
    return sql.replace("%s", "?") if conn.vendor == "sqlite" else sql


def ensure_table():
    """Create the table if it is not there. True when the ledger is usable."""
    global _ready
    if not ENABLED:
        return False
    if _ready:
        return True
    conn = _connection()
    if conn is None:
        return False
    try:
        create = _CREATE.get(conn.vendor)
        if create is None:
            _log.info("CacheStore ledger: no table definition for %s; not recording", conn.vendor)
            return False
        with conn.cursor() as cur:
            cur.execute(create)
        _ready = True
        return True
    except Exception as exc:
        _log.info("CacheStore ledger: could not create %s (%r)", TABLE, exc)
        return False


def record(meta):
    """Append one row describing a stored product. True when a row landed.

    Takes the sidecar dictionary the store just wrote, so the ledger and the sidecar cannot
    disagree about what was stored — there is one source and it is passed in, not re-derived.
    """
    if not ENABLED:
        return False
    if not ensure_table():
        return False
    conn = _connection()
    if conn is None:
        return False
    chain = meta.get("provenance") or []
    try:
        with conn.cursor() as cur:
            cur.execute(_placeholder(conn, _INSERT), [
                str(meta.get("written_utc") or ""),
                str(meta.get("kind") or ""),
                meta.get("participant_uid"),
                str(meta.get("signature_key") or ""),
                meta.get("writer"),
                meta.get("trigger"),
                meta.get("format"),
                meta.get("payload_bytes"),
                meta.get("n_recordings"),
                len(chain),
                json.dumps(chain, sort_keys=True),
            ])
        return True
    except Exception as exc:
        _log.info("CacheStore ledger: could not record a %s row (%r)",
                  meta.get("kind"), exc)
        return False


def history(kind=None, participant=None, limit=50):
    """The most recent rows, newest first. An empty list when the ledger is unavailable.

    For the interface and for answering "when was this last rebuilt, and from what".
    """
    if not ensure_table():
        return []
    conn = _connection()
    if conn is None:
        return []
    where, params = [], []
    if kind:
        where.append("kind = %s")
        params.append(kind)
    if participant:
        where.append("participant = %s")
        params.append(participant)
    sql = (f"SELECT written_utc, kind, participant, signature_key, writer, trigger_name, fmt, "
           f"payload_bytes, n_recordings, n_inputs, provenance FROM {TABLE}")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(int(limit))
    cols = ("written_utc", "kind", "participant", "signature_key", "writer", "trigger", "format",
            "payload_bytes", "n_recordings", "n_inputs", "provenance")
    try:
        with conn.cursor() as cur:
            cur.execute(_placeholder(conn, sql), params)
            rows = cur.fetchall()
    except Exception as exc:
        _log.info("CacheStore ledger: could not read history (%r)", exc)
        return []
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        try:
            d["provenance"] = json.loads(d["provenance"] or "[]")
        except Exception:
            d["provenance"] = []
        out.append(d)
    return out


def counts_by_kind():
    """How many times each kind has been written, for the interface. Empty when unavailable."""
    if not ensure_table():
        return {}
    conn = _connection()
    if conn is None:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT kind, COUNT(*) FROM {TABLE} GROUP BY kind")
            return {k: int(n) for k, n in cur.fetchall()}
    except Exception as exc:
        _log.info("CacheStore ledger: could not count rows (%r)", exc)
        return {}
