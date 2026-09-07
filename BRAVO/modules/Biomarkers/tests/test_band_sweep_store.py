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
        "matched_seconds": 0.01, "total_seconds": 0.02, "figures": {"heat": {"data": []}},
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
