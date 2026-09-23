"""The chosen closed-loop band is recorded on the server (the PI's ruling 8, decision 233).

Until 2026-09-23 the band chosen on the Closed-Loop page lived only in the browser that chose it
(`bandCandidateStore.js`, localStorage): another browser, another machine or a cleared browser
showed "No band has been committed", and nothing anywhere said which band had been chosen, when,
or by whom. The ruling: record it on the server and update it whenever a new band is chosen.

The record is append-only, like the store's ledger: a choice or a clear adds a row, nothing
rewrites one, and the current band is the newest row. So the history also answers "which band was
chosen on the day this sheet was signed".

Unlike the ledger, a failed save is REPORTED, never swallowed: the page must be able to say that a
choice lives in this browser only.

These tests run the real statements against an in-memory SQLite database of their own, the way
`CacheStore/tests/test_ledger.py` does.

Run on the host:
    cd BRAVO/modules && PYTHONPATH=. python -B -m pytest ClosedLoopDeployment/tests/test_chosen_band.py -q
"""
import contextlib
import sqlite3

import pytest

from ClosedLoopDeployment import chosen_band as CB

UID = "2e3c75c00d7f4f37b53a048d195f11da"
OTHER = "1111111111111111111111111111aaaa"


class _Conn:
    vendor = "sqlite"

    def __init__(self):
        self.raw = sqlite3.connect(":memory:")

    def cursor(self):
        return contextlib.closing(self.raw.cursor())


@pytest.fixture()
def db():
    conn = _Conn()
    prev = (CB.CONNECTION_FACTORY, CB._ready)
    CB.CONNECTION_FACTORY, CB._ready = (lambda: conn), False
    yield conn
    CB.CONNECTION_FACTORY, CB._ready = prev
    conn.raw.close()


def _band(contact="ONE_THREE_LEFT", centre=24.5, metric="left_leg_vas"):
    return {"schema_version": "bandcandidate_v1", "contact": contact,
            "center_freq_hz": centre, "band_width_hz": 5.0,
            "label": {"pro_metric": metric}}


def _rows(conn):
    cur = conn.raw.cursor()
    cur.execute(f"SELECT id, action FROM {CB.TABLE} ORDER BY id")
    return cur.fetchall()


def test_a_choice_is_read_back_as_the_current_band(db):
    out = CB.choose(UID, _band(), chosen_by="clinician@example.org", source="grid")
    assert out["saved"] is True and out["reason"] is None
    cur = CB.current(UID)
    assert cur["available"] is True
    rec = cur["record"]
    assert rec["band_candidate"] == _band()
    assert rec["participant_uid"] == UID
    assert rec["chosen_by"] == "clinician@example.org"
    assert rec["source"] == "grid"
    assert rec["committed_at"] == out["record"]["committed_at"]
    assert rec["saved_on_server"] is True
    # The same envelope shape the page already reads from browser storage.
    assert rec["schema"] == "bandcandidate_envelope_v1"


def test_a_new_choice_supersedes_and_both_stay_in_the_history(db):
    CB.choose(UID, _band(centre=22.5), chosen_by="a", source="grid")
    CB.choose(UID, _band(centre=24.5), chosen_by="b", source="grid")
    assert CB.current(UID)["record"]["band_candidate"]["center_freq_hz"] == 24.5
    hist = CB.history(UID)
    assert [h["band_candidate"]["center_freq_hz"] for h in hist] == [24.5, 22.5], "newest first"
    assert [h["chosen_by"] for h in hist] == ["b", "a"]


def test_a_clear_leaves_no_current_band_and_is_itself_recorded(db):
    CB.choose(UID, _band(), chosen_by="a", source="grid")
    out = CB.clear(UID, chosen_by="b")
    assert out["saved"] is True
    assert CB.current(UID)["record"] is None
    hist = CB.history(UID)
    assert [h["action"] for h in hist] == ["cleared", "chosen"]
    CB.choose(UID, _band(centre=20.5), chosen_by="c", source="upload")
    assert CB.current(UID)["record"]["band_candidate"]["center_freq_hz"] == 20.5


def test_nothing_is_ever_rewritten(db):
    CB.choose(UID, _band(centre=22.5), chosen_by="a", source="grid")
    CB.choose(UID, _band(centre=22.5), chosen_by="a", source="grid")   # the same band again
    CB.clear(UID, chosen_by="a")
    rows = _rows(db)
    assert [r[1] for r in rows] == ["chosen", "chosen", "cleared"]
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)


def test_one_participants_choice_never_reaches_another(db):
    CB.choose(UID, _band(), chosen_by="a", source="grid")
    assert CB.current(OTHER)["record"] is None
    assert CB.history(OTHER) == []
    CB.clear(OTHER, chosen_by="a")
    assert CB.current(UID)["record"] is not None


def test_a_malformed_band_is_refused_by_name_and_writes_nothing(db):
    for bad in (None, {}, {"contact": "ONE_THREE_LEFT"}, {"center_freq_hz": 24.5}, "24.5 Hz"):
        out = CB.choose(UID, bad, chosen_by="a", source="grid")
        assert out["saved"] is False and out["reason"], bad
    assert CB.history(UID) == []


def test_an_oversized_band_is_refused(db):
    big = dict(_band(), padding="x" * (CB.MAX_CANDIDATE_BYTES + 1))
    out = CB.choose(UID, big, chosen_by="a", source="grid")
    assert out["saved"] is False and "large" in out["reason"]
    assert CB.history(UID) == []


def test_a_choice_carried_over_from_browser_storage_keeps_its_own_time(db):
    """The first time the page opens after this change, a band chosen earlier and held only in the
    browser is sent to the server once; it must keep the time it was chosen, not today's."""
    out = CB.choose(UID, _band(), chosen_by="a", source="browser_storage",
                    committed_at="2026-09-20T17:03:00.000Z")
    assert out["saved"] is True
    rec = CB.current(UID)["record"]
    assert rec["committed_at"] == "2026-09-20T17:03:00.000Z"
    assert rec["source"] == "browser_storage"
    assert rec["recorded_utc"] != rec["committed_at"], "when the server heard of it is kept apart"


def test_an_unknown_source_is_refused(db):
    out = CB.choose(UID, _band(), chosen_by="a", source="somewhere")
    assert out["saved"] is False and "source" in out["reason"]


def test_with_no_database_a_save_says_so_rather_than_raising():
    prev = (CB.CONNECTION_FACTORY, CB._ready)
    CB.CONNECTION_FACTORY, CB._ready = (lambda: None), False
    try:
        out = CB.choose(UID, _band(), chosen_by="a", source="grid")
        assert out["saved"] is False and out["reason"]
        cur = CB.current(UID)
        assert cur["available"] is False and cur["record"] is None and cur["reason"]
        assert CB.clear(UID, chosen_by="a")["saved"] is False
    finally:
        CB.CONNECTION_FACTORY, CB._ready = prev
