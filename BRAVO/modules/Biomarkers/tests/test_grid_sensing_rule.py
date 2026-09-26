"""The heat-map grid's response states the device's sensing rule with today's contacts (2026-09-26).

WHY. While a lead stimulates, the device senses only on the two contacts immediately flanking the
stimulating contacts (decisions 217, 243, 247). The Stim Optimizer's readiness card and the
Closed-Loop page's rule D52 apply it; the heat maps showed six pairs as if any of them could drive
closed loop. The page marks the pairs the device refuses, reading a `sensing_rule` block in the Stim
Optimizer's shape (`BiomarkerHeatmapGrids.refusedPairs`), and invents nothing when the block is
absent. The rule's one home is `DecodeCommon.sensing_rule`; the contacts in force are read from the
device's own dated settings (the raw kind `therapy_settings`, as consumer "biomarkers", the same
read `routines/stim_current.py` makes for the current).

ATTACHED AFTER THE STORED GRID IS READ, never inside its key or payload: the contacts change
independently of the recordings and the ratings, so a grid filed before a reprogramming must still
be served, and must be served with TODAY's contacts, not the ones in force when it was built.

Same bench as test_band_sweep_store.py: no Django, no database, a store root of its own. Run inside
the container: python3 _agent_bridge/run_tests.py
"""
import json
import os
import unittest.mock as mock

from modules.Biomarkers.tests.test_band_sweep_store import B, REQ, _Bench   # noqa: E402

try:
    from modules.DecodeCommon import sensing_rule as SR
except ImportError:                                                         # pragma: no cover
    from DecodeCommon import sensing_rule as SR

#: RCS08 since 2026-09-03: left C+2-, right C+1-2- (decision 247).
_TODAY = {"by_side": {"Left": {"rings": {2}, "cathode": "2a-2b-2c", "newest_row_utc": "2026-09-03T18:00:00+00:00"},
                      "Right": {"rings": {1, 2}, "cathode": "1a-1b-1c-2a-2b-2c",
                                "newest_row_utc": "2026-09-03T18:00:00+00:00"}},
          "store_key": "therapy_settings/u/abc"}
#: An earlier programming: left C+1-, right C+2-.
_EARLIER = {"by_side": {"Left": {"rings": {1}, "cathode": "1a-1b-1c", "newest_row_utc": "2026-08-12T17:00:00+00:00"},
                        "Right": {"rings": {2}, "cathode": "2a-2b-2c", "newest_row_utc": "2026-08-12T17:00:00+00:00"}},
            "store_key": "therapy_settings/u/old"}


def _contacts(value):
    return mock.patch.object(B.stim_current, "contacts_in_force", lambda uid: value)


def test_a_freshly_built_grid_carries_the_rule_with_todays_contacts_in_the_stim_optimizers_shape():
    with _Bench(), _contacts(_TODAY):
        out = B.band_time_sweep_for_participant(dict(REQ))
    assert out["served_from_store"] is False
    rule = out["sensing_rule"]
    assert rule["available"] is True
    left, right = rule["by_side"]["Left"], rule["by_side"]["Right"]
    assert (left["rule_applied"], left["allowed_channel"], left["allowed_pair"]) == (True, "ONE_THREE_LEFT", [1, 3])
    assert (right["rule_applied"], right["allowed_channel"], right["allowed_pair"]) == (True, "ZERO_THREE_RIGHT", [0, 3])
    assert left["allowed_display"] == "L 1⁻3⁺" and right["allowed_display"] == "R 0⁻3⁺"
    assert left["stim_rings"] == [2] and right["stim_rings"] == [1, 2]
    assert "flanking" in left["why"]
    assert left["stim_cathode_raw"] == "2a-2b-2c"
    assert rule["store_key"] == "therapy_settings/u/abc"
    assert rule["sentence"].startswith("While today's contacts are stimulating, the device allows one "
                                       "sensing pair per lead: L 1⁻3⁺ and R 0⁻3⁺.")
    # the per-side fields the page reads are exactly the one home's
    want = SR.sensing_rule_block({"Left": {2}, "Right": {1, 2}},
                                 display_of=lambda ch: B.analytics.format_channel(ch, region="")["short"])
    for side in ("Left", "Right"):
        for k, v in want["by_side"][side].items():
            assert rule["by_side"][side][k] == v, (side, k)


def test_the_rule_is_in_neither_the_stored_payload_nor_the_key_and_a_served_grid_reads_todays_contacts():
    with _Bench() as b:
        with _contacts(_EARLIER):
            first = B.band_time_sweep_for_participant(dict(REQ))
        with _contacts(_TODAY):
            second = B.band_time_sweep_for_participant(dict(REQ))
        # the contacts changed and the grid did not: served, same key, no second build
        assert b.sweep_calls == 1
        assert second["served_from_store"] is True
        assert second["sweep_key"] == first["sweep_key"]
        assert first["sensing_rule"]["by_side"]["Left"]["allowed_channel"] == "ZERO_TWO_LEFT"
        assert second["sensing_rule"]["by_side"]["Left"]["allowed_channel"] == "ONE_THREE_LEFT"
        # nothing about the contacts on disk: the stored payload read back, and its sidecar
        from modules.CacheStore import store as st
        payload, stamp = st.load_newest("biomarker_band_sweep", "u", consumer="biomarkers",
                                        root=b._dir)
        assert isinstance(payload, dict) and payload.get("band_time_sweep")
        assert "sensing_rule" not in payload
        assert "sensing_rule" not in json.dumps(stamp, default=str)
        d = os.path.join(b._dir, "biomarker_band_sweep")
        assert [f for f in os.listdir(d) if f.endswith(".meta.json")]


def test_with_no_dated_settings_on_record_the_block_says_so_and_refuses_nothing():
    with _Bench(), _contacts(None):
        out = B.band_time_sweep_for_participant(dict(REQ))
    rule = out["sensing_rule"]
    assert rule["available"] is False
    assert rule["reason"]
    for side in ("Left", "Right"):
        assert rule["by_side"][side]["rule_applied"] is False
        assert rule["by_side"][side]["allowed_channel"] is None


def test_a_failed_read_never_fails_the_grid():
    def boom(uid):
        raise RuntimeError("store unreachable")
    with _Bench(), mock.patch.object(B.stim_current, "contacts_in_force", boom):
        out = B.band_time_sweep_for_participant(dict(REQ))
    assert out["band_time_sweep"]
    assert out["sensing_rule"]["available"] is False
    assert "store unreachable" in out["sensing_rule"]["reason"]


def test_the_contacts_come_from_the_stored_settings_stream_as_the_biomarkers_consumer():
    import pandas as pd
    df = pd.DataFrame({"t": pd.to_datetime(["2026-08-12 17:00", "2026-09-03 18:00", "2026-09-03 18:00"], utc=True),
                       "hemi": ["Left", "Left", "Right"], "amp": [4.5, 3.0, 3.2],
                       "cathode": ["1a-1b-1c", "2a-2b-2c", "1a-1b-1c-2a-2b-2c"]})
    seen = {}

    def load_newest(kind, uid, consumer=None, **kw):
        seen.update(kind=kind, uid=uid, consumer=consumer)
        return df, {"signature_key": "therapy_settings/u/abc"}
    from modules.CacheStore import store as st
    with mock.patch.object(st, "load_newest", load_newest):
        got = B.stim_current.contacts_in_force("u")
    assert seen == {"kind": "therapy_settings", "uid": "u", "consumer": "biomarkers"}
    assert got["by_side"]["Left"]["rings"] == {2}
    assert got["by_side"]["Right"]["rings"] == {1, 2}
    assert got["store_key"] == "therapy_settings/u/abc"
