"""The append-only ledger, exercised against a real database of its own: SQLite in memory.

Until 2026-09-07 no test ran the ledger's statements at all; every store sandbox turns it off, and a
docstring claimed a test file that did not exist. These tests point the ledger at an in-memory
SQLite database through `CONNECTION_FACTORY`, so the table creation, the insert, the history query
and the counts run for real, with SQLite's placeholder rather than MySQL's.
"""
import contextlib
import pathlib
import sqlite3
import sys

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.CacheStore import ledger   # noqa: E402


class _Conn:
    """The two things the ledger asks of a connection: a vendor name and a cursor context."""
    vendor = "sqlite"

    def __init__(self):
        self.raw = sqlite3.connect(":memory:")

    def cursor(self):
        return contextlib.closing(self.raw.cursor())


class _Sandbox:
    def __enter__(self):
        self.conn = _Conn()
        self._prev = (ledger.CONNECTION_FACTORY, ledger.ENABLED, ledger._ready)
        ledger.CONNECTION_FACTORY, ledger.ENABLED, ledger._ready = (lambda: self.conn), True, False
        return self.conn

    def __exit__(self, *exc):
        ledger.CONNECTION_FACTORY, ledger.ENABLED, ledger._ready = self._prev
        self.conn.raw.close()
        return False


def _meta(kind, n=0, participant="p1", chain=None):
    return {"written_utc": "2026-09-07T00:00:%02dZ" % n, "kind": kind, "participant_uid": participant,
            "signature_key": "k%d" % n, "writer": "biomarkers", "trigger": "test",
            "format": "parquet", "payload_bytes": 10 * n, "n_recordings": n,
            "provenance": chain or []}


def test_the_table_is_created_on_first_use_and_a_row_lands():
    with _Sandbox():
        assert ledger.record(_meta("redcap_reports", 1)) is True
        assert ledger.counts_by_kind() == {"redcap_reports": 1}


def test_history_is_newest_first_and_carries_the_chain_back_as_a_list():
    chain = [{"key": "raw_lsb_tiles/p1/abc", "kind": "raw_lsb_tiles", "writer": "biomarkers"}]
    with _Sandbox():
        ledger.record(_meta("therapy_settings", 1))
        ledger.record(_meta("therapy_pain_matched", 2, chain=chain))
        rows = ledger.history()
        assert [r["kind"] for r in rows] == ["therapy_pain_matched", "therapy_settings"]
        assert rows[0]["provenance"] == chain and rows[0]["n_inputs"] == 1
        assert rows[1]["provenance"] == [] and rows[1]["n_inputs"] == 0
        assert ledger.history(kind="therapy_settings")[0]["kind"] == "therapy_settings"
        assert ledger.history(participant="nobody") == []


def test_turned_off_it_records_nothing_and_answers_empty():
    with _Sandbox():
        ledger.ENABLED = False
        assert ledger.record(_meta("redcap_reports", 1)) is False
        assert ledger.history() == [] and ledger.counts_by_kind() == {}


def test_a_broken_connection_is_swallowed_never_raised():
    """Recording that a cache was written is bookkeeping; a failure must not fail a page."""
    with _Sandbox() as conn:
        ledger.record(_meta("redcap_reports", 1))
        conn.raw.close()                       # every later statement raises inside the ledger
        ledger._ready = False
        assert ledger.record(_meta("redcap_reports", 2)) is False
        assert ledger.history() == []
