"""Track A step 6: the band-by-length sweep writes its results back, and the key decides.

WHAT THESE TESTS HOLD. After one computation the two tidy tables and the response are in the store
with the tile entry and the pain-report snapshot in their provenance. A second request with the
same inputs is served from the store and does not run the sweep again. A newly filed report, a
different pain score or a moved setting is a new key and a fresh computation. Reports handed in
through the request body, or a participant with no tile key, are computed and never stored. With
the store off nothing is written and every request computes.

Everything expensive is stood in for: the recordings, the tile cache and the sweep arithmetic. What
runs for real is the endpoint's own wiring, the table builders and the store. No Django and no
database, same stubbing as test_redcap_snapshot.py. Run inside the container:
    python3 _agent_bridge/run_tests.py

Merged here 2026-10-05: test_grid_rule_on_sidecar.py, test_grid_sensing_rule.py.
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest.mock as mock
import numpy as np
import pandas as pd
_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _import_service():
    for mod in ("Server", "Server.models", "modules.Database"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    for mod in ("modules.Biomarkers.pipeline", "modules.Biomarkers.adapter"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    import modules.Biomarkers.bravo_service as bs
    return bs


B = _import_service()
from modules.Biomarkers.routines import analytics as A                 # noqa: E402
from modules.CacheStore import store as st                              # noqa: E402
UID = "u"


def _reports(key="redcap_reports/u/abc", n=30):
    rows = [{"date_time_s1_daily": "2025-09-%02d 09:00" % (i % 28 + 1), "nrs": float(i % 9),
             "vas": float((i % 9) * 10)}
            for i in range(n)]
    df = pd.DataFrame(rows)
    if key:
        df.attrs[B.PRO_STORE_KEY_ATTR] = key
    return df


def _sweep_stub(channel):
    centres = [8.5, 9.5]
    seconds = [1.0, 5.0]
    return {
        "answer": "not_resolved", "channel": channel, "center_freqs_hz": centres,
        "band_width_hz": 5.0, "band_fully_inside_8_to_30_hz": [False, False],
        "integration_seconds_requested": seconds, "integration_seconds_delivered": [3.0, 6.0],
        "integration_tiles": [1, 2], "correlation_grid": [[0.1, 0.2], [0.3, 0.4]],
        "auc_grid": [[0.6, 0.55], [0.45, 0.7]], "auc_direction_folded_grid": [[0.6, 0.55], [0.55, 0.7]],
        "n_grid": [[10, 10], [10, 10]], "auc_n_high_grid": [[5, 5], [5, 5]],
        "auc_n_low_grid": [[5, 5], [5, 5]],
        "best_correlation_rows": [{"band_center_hz": 8.5, "integration_seconds_requested": 5.0,
                                   "pearson_r": 0.3, "answer": "not_resolved"}],
        "best_auc_rows": [{"band_center_hz": 9.5, "integration_seconds_requested": 5.0,
                           "auc": 0.7, "answer": "not_resolved"}],
        "pain_split_rule": "median split", "pain_low_cut": 4.0, "pain_high_cut": 4.0,
        "matched_seconds": 0.01, "total_seconds": 0.02,
    }


class _Bench:
    """A store root of this test's own, the ledger off, and every expensive step stubbed."""

    def __init__(self, reports=None, tiles_sig=("ident", "abcd", 98, "consts")):
        self.reports = _reports() if reports is None else reports
        self.tiles_sig = tiles_sig
        self.sweep_calls = 0

    def _channels(self, raw_by_channel, pro_times, **kw):
        self.sweep_calls += 1
        return {ch: _sweep_stub(ch) for ch in raw_by_channel}

    def __enter__(self):
        from modules.CacheStore import ledger
        self._dir = tempfile.mkdtemp(prefix="bravo_sweep_store_")
        self._prev = (B._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED, st.ENABLED)
        B._SHARED_CACHE_DIR_OVERRIDE = self._dir
        ledger.ENABLED = False
        self._patches = [
            mock.patch.object(B.models.Participant, "find", lambda **k: object()),
            mock.patch.object(B, "_load_recordings", lambda uid, types: [{"Data": np.zeros(3)}]),
            mock.patch.object(B, "_load_pros", lambda req, p: self.reports.copy()),
            mock.patch.object(B, "_build_sensing_config_index", lambda td: {}),
            mock.patch.object(B, "_event_psd_lsb_blocks", lambda uid, sensing_index=None: []),
            mock.patch.object(B, "_montage_psd_lsb_blocks", lambda uid, montage_recordings=None: []),
            mock.patch.object(B, "_derive_chan_order", lambda td: ["ZERO_THREE_RIGHT", "ONE_THREE_LEFT"]),
            mock.patch.object(B, "_stamp_td_product", lambda td: None),
            mock.patch.object(B, "_raw_lsb_cache_cached",
                              lambda uid, ch, recs, ev, montage_psd_blocks=None, **kw:
                              {c: {"stub": True} for c in ch}),
            mock.patch.object(B, "_raw_lsb_shared_signature",
                              lambda uid, centers, identity=None: self.tiles_sig),
            mock.patch.object(B, "_band_time_sweep_channels", self._channels),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        from modules.CacheStore import ledger
        for p in reversed(self._patches):
            p.stop()
        B._SHARED_CACHE_DIR_OVERRIDE, ledger.ENABLED, st.ENABLED = self._prev
        shutil.rmtree(self._dir, ignore_errors=True)
        return False

    def kinds(self):
        """The kinds holding at least one payload; a miss creates an empty directory."""
        out = []
        for d in sorted(os.listdir(self._dir)):
            full = os.path.join(self._dir, d)
            if os.path.isdir(full) and any(f.endswith((".parquet", ".pkl", ".npz"))
                                           for f in os.listdir(full)):
                out.append(d)
        return out

    def sidecar(self, kind):
        d = os.path.join(self._dir, kind)
        metas = [f for f in os.listdir(d) if f.endswith(".meta.json")]
        assert len(metas) == 1, metas
        with open(os.path.join(d, metas[0])) as fh:
            return json.load(fh)


REQ = {"ParticipantId": UID}


def test_one_computation_writes_the_two_tables_and_the_response_with_both_inputs_cited():
    with _Bench() as b:
        out = B.band_time_sweep_for_participant(dict(REQ))
        assert b.sweep_calls == 1
        assert out["served_from_store"] is False
        assert set(out["store_keys"]) == {"response", "correlation", "discrimination"}
        assert b.kinds() == sorted(["biomarker_band_correlation", "biomarker_band_discrimination",
                                    "biomarker_band_sweep"])
        for kind in b.kinds():
            meta = b.sidecar(kind)
            assert meta["writer"] == "biomarkers"
            assert {c["kind"] for c in meta["provenance"]} == {"raw_lsb_tiles", "redcap_reports"}
            assert meta["n_recordings"] == 1
        # the tables are the response's numbers, value for value
        d = os.path.join(b._dir, "biomarker_band_correlation")
        corr = pd.read_parquet(os.path.join(d, [f for f in os.listdir(d) if f.endswith(".parquet")][0]))
        assert len(corr) == 2 * 2 * 2
        from modules.Biomarkers.routines import band_results_tables as BT
        assert BT.count_matches(corr, out["band_time_sweep"], "pearson_r", "correlation_grid") == (8, 0)


def test_the_same_inputs_are_served_from_the_store_without_running_the_sweep():
    with _Bench() as b:
        first = B.band_time_sweep_for_participant(dict(REQ))
        second = B.band_time_sweep_for_participant(dict(REQ))
        assert b.sweep_calls == 1, "the sweep ran again although nothing feeding it had changed"
        assert second["served_from_store"] is True and second["stored_utc"]
        assert second["store_keys"] == first["store_keys"]
        for k in first:
            if k in ("served_from_store", "store_keys", "stored_utc", "store_written") \
                    or k in B.BAND_SWEEP_TIMING_FIELDS:
                continue
            assert second[k] == first[k], k
        assert first["store_written"] == {"correlation": True, "discrimination": True,
                                          "response": True}
        assert second["store_written"]["response"] is True


def test_a_newly_filed_report_is_a_new_key_and_a_fresh_computation():
    with _Bench() as b:
        B.band_time_sweep_for_participant(dict(REQ))
        b.reports = _reports(key="redcap_reports/u/def", n=31)
        out = B.band_time_sweep_for_participant(dict(REQ))
        assert b.sweep_calls == 2
        assert out["served_from_store"] is False


def test_a_different_pain_score_or_setting_is_a_new_key():
    with _Bench() as b:
        B.band_time_sweep_for_participant(dict(REQ))
        B.band_time_sweep_for_participant(dict(REQ, SweepMetric="vas"))
        B.band_time_sweep_for_participant(dict(REQ, AllowWindowReuse="1"))
        assert b.sweep_calls == 3


def test_reports_handed_in_through_the_request_body_are_computed_and_never_stored():
    rows = [{"date_time_s1_daily": "2025-09-01 09:00", "nrs": 3.0}]
    with _Bench(reports=_reports(key=None)) as b:
        out = B.band_time_sweep_for_participant(dict(REQ, ProcessedPRO=rows))
        assert b.sweep_calls == 1
        assert out["store_keys"] is None and b.kinds() == []
        B.band_time_sweep_for_participant(dict(REQ, ProcessedPRO=rows))
        assert b.sweep_calls == 2


def test_without_a_tile_key_nothing_is_stored():
    with _Bench(tiles_sig=None) as b:
        out = B.band_time_sweep_for_participant(dict(REQ))
        assert out["store_keys"] is None and b.kinds() == []


def test_with_the_store_off_every_request_computes_and_nothing_is_written():
    with _Bench() as b:
        st.ENABLED = False
        B.band_time_sweep_for_participant(dict(REQ))
        B.band_time_sweep_for_participant(dict(REQ))
        assert b.sweep_calls == 2 and b.kinds() == []


# --------------------------------------------------------------------------------------------------
# merged from test_grid_rule_on_sidecar.py
# The Biomarkers writer names the grid rule on every stored grid, and its key is the one the other
# pages' readers can recompute (decision 317, 2026-09-26).
#
# The Closed-Loop card and the Stim Optimizer read a stored grid by its settings tag and must serve it
# only when it was written under the grid rule in force (`ClosedLoopDeployment/tests/
# test_grid_rule_in_force.py`). They can know that two ways: the sidecar names the rule (every grid
# written from now on), or, for a sidecar written before this change, the entry's key equals the key
# the rule in force gives for what the sidecar records. Both are pinned here against the real writer,
# with the recordings, the tile cache and the arithmetic stood in for (`test_band_sweep_store._Bench`).
# Run inside the container: python3 _agent_bridge/run_tests.py


from modules.Biomarkers.routines import sweep_settings as SS                 # noqa: E402
KINDS = ("biomarker_band_sweep", "biomarker_band_correlation", "biomarker_band_discrimination")
PAGE_LIKE = dict(REQ, SweepMetric="vas", MatchToleranceMin=5.0, LabelStrategy="median",
                 PercentileLow=33.3, PercentileHigh=66.7, MatchDirection="prior",
                 IncludeClinicSheetRatings="true", AllowWindowReuse="1")


def test_every_stored_grid_product_names_the_rule_it_was_written_under():
    with _Bench() as b:
        B.band_time_sweep_for_participant(dict(REQ))
        for kind in KINDS:
            meta = b.sidecar(kind)
            assert (meta.get("extra") or {}).get("rule_version") == SS.GRID_RULE_VERSION, kind
            assert SS.grid_written_under_rule_in_force(meta), kind


def test_the_writer_binds_the_rule_and_kind_from_their_one_home():
    assert B._BAND_SWEEP_RULE_VERSION is SS.GRID_RULE_VERSION
    assert B._BAND_SWEEP_RESPONSE_KIND is SS.GRID_KIND
    assert SS.GRID_INPUT_KINDS == (B._RAW_LSB_SHARED_KIND, "redcap_reports")


def test_the_writers_key_is_the_one_home_signature():
    with _Bench() as b:
        pro_df = b.reports.copy()
        settings = {"eligibility_radius_seconds": 3600.0, "allow_window_reuse": False,
                    "label_strategy": "tertile", "percentile_low": 33.3333,
                    "percentile_high": 66.6667, "outlier_n_mad": 5.0, "outlier_scale": "raw",
                    "match_direction": "pro_first", "include_cross_setting_stability": False,
                    "include_clinic_sheet_ratings": False, "adjust_for_stim_current": False}
        sig, _prov, tiles_sig = B._band_sweep_signature("u", pro_df, "nrs", settings)
        tiles_key = st.product_key(B._RAW_LSB_SHARED_KIND, "u", tiles_sig)
        report_key = pro_df.attrs[B.PRO_STORE_KEY_ATTR]
        assert sig == SS.grid_signature("u", tiles_key, report_key, "nrs", settings)
        assert sig[1] == SS.GRID_RULE_VERSION


def test_a_sidecar_without_the_rule_is_recognised_from_its_key_for_default_and_page_settings():
    """What the readers do for every grid written before this change: drop the rule from a real
    sidecar and the key recomputed from what it records must still name the rule in force."""
    for req in (dict(REQ), PAGE_LIKE, dict(REQ, AdjustForStimCurrent="1")):
        with _Bench() as b:
            B.band_time_sweep_for_participant(dict(req))
            meta = b.sidecar("biomarker_band_sweep")
            meta["extra"].pop("rule_version")
            assert SS.grid_written_under_rule_in_force(meta), req
            # and the same sidecar read as if its key had been built under another rule is refused
            assert not SS.grid_written_under_rule_in_force(
                dict(meta, signature_key=st.signature_key(("another rule",))))


# --------------------------------------------------------------------------------------------------
# merged from test_grid_sensing_rule.py
# The heat-map grid's response states the device's sensing rule with today's contacts (2026-09-26).
#
# WHY. While a lead stimulates, the device senses only on the two contacts immediately flanking the
# stimulating contacts (decisions 217, 243, 247). The Stim Optimizer's readiness card and the
# Closed-Loop page's rule D52 apply it; the heat maps showed six pairs as if any of them could drive
# closed loop. The page marks the pairs the device refuses, reading a `sensing_rule` block in the Stim
# Optimizer's shape (`BiomarkerHeatmapGrids.refusedPairs`), and invents nothing when the block is
# absent. The rule's one home is `DecodeCommon.sensing_rule`; the contacts in force are read from the
# device's own dated settings (the raw kind `therapy_settings`, as consumer "biomarkers", the same
# read `routines/stim_current.py` makes for the current).
#
# ATTACHED AFTER THE STORED GRID IS READ, never inside its key or payload: the contacts change
# independently of the recordings and the ratings, so a grid filed before a reprogramming must still
# be served, and must be served with TODAY's contacts, not the ones in force when it was built.
#
# Same bench as test_band_sweep_store.py: no Django, no database, a store root of its own. Run inside
# the container: python3 _agent_bridge/run_tests.py


try:
    from modules.DecodeCommon import sensing_rule as SR
except ImportError:                                                         # pragma: no cover
    from DecodeCommon import sensing_rule as SR
#: RCS08 since 2026-09-02 19:15 UTC on the tablet clock: left C+2-, right C+1-2- (decisions 247, 328;
#: older records said 2026-09-03, a later export's re-stamped copy of the same settings).
_TODAY = {"by_side": {"Left": {"rings": {2}, "cathode": "2a-2b-2c", "newest_row_utc": "2026-09-02T19:15:43+00:00"},
                      "Right": {"rings": {1, 2}, "cathode": "1a-1b-1c-2a-2b-2c",
                                "newest_row_utc": "2026-09-02T19:15:43+00:00"}},
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
    df = pd.DataFrame({"t": pd.to_datetime(["2026-08-12 17:00", "2026-09-02 19:15", "2026-09-02 19:15"], utc=True),
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
