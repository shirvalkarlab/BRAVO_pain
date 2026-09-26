"""The Biomarkers writer names the grid rule on every stored grid, and its key is the one the other
pages' readers can recompute (decision 317, 2026-09-26).

The Closed-Loop card and the Stim Optimizer read a stored grid by its settings tag and must serve it
only when it was written under the grid rule in force (`ClosedLoopDeployment/tests/
test_grid_rule_in_force.py`). They can know that two ways: the sidecar names the rule (every grid
written from now on), or, for a sidecar written before this change, the entry's key equals the key
the rule in force gives for what the sidecar records. Both are pinned here against the real writer,
with the recordings, the tile cache and the arithmetic stood in for (`test_band_sweep_store._Bench`).
Run inside the container: python3 _agent_bridge/run_tests.py
"""
from modules.Biomarkers.tests.test_band_sweep_store import B, REQ, _Bench   # noqa: E402
from modules.Biomarkers.routines import sweep_settings as SS                 # noqa: E402
from modules.CacheStore import store as st                                    # noqa: E402

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
