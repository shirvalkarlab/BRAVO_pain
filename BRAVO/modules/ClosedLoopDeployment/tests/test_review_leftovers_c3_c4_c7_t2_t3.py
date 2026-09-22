"""The 2026-09-15 clinician review's Medium and Low leftovers, built 2026-09-17 on the PI's
"do the c3 c4 etc" (decision 200):

C3  the simulation names the timing values the record cannot decide;
C4  (the reliable-change index was deleted on 2026-09-22, decision 231; its test went with it)
C7  the paused-amplitude row carries the general amplitude range;
T2  the pooled current-to-power row carries every run's own slope beside the pooled one, and
    E1's note reads them out;
T3  the threshold occupancy is computed at the card's averaging AND at the averaging the
    device runs today, and the row's sentence prints both.

Values, not shapes.
"""
import json

import numpy as np
import pytest

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment import amplitude_effect as AE
from ClosedLoopDeployment import edges as ED
from ClosedLoopDeployment import occupancy as OC
from ClosedLoopDeployment import prescription as PR
from ClosedLoopDeployment import simulation as SIM
from ClosedLoopDeployment import timing_recommendation as TR
from ClosedLoopDeployment.tests.test_amplitude_effect import _build, _comparison, _panel, CENTRES
from ClosedLoopDeployment.tests.test_prescription_modes import _cand, _plan

PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")


# --- C7 ---------------------------------------------------------------------------------------
def test_c7_the_paused_amplitude_row_carries_the_general_amplitude_range():
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=_plan(), candidate=_cand(),
                      timing=PA.timing_plan(mode=PA.DUAL))
    paused = next(r for r in pr.as_rows() if r["parameter"] == "Paused amplitude")
    assert paused["value"] is None                       # decision: never a suggested number
    assert list(paused["range"]) == list(PA.ADAPTIVE_AMP_LIMIT_RANGE_MA)
    assert "documented range" in paused["range_source"]


# --- T2 ---------------------------------------------------------------------------------------
def _two_runs():
    a = _comparison(label="run A")
    b = _comparison(label="run B", panel=_panel([1.0, 2.0, 3.0, 4.0]))
    return _build(a, b)


def test_t2_the_pooled_row_carries_every_runs_own_slope():
    out = AE.pooled_shape_for_band(_two_runs(), CENTRES[3], "ONE_THREE_LEFT")   # the falling band
    runs = out["per_run_slopes"]
    assert [r["run"] for r in runs] == ["run A", "run B"]
    assert [r["n"] for r in runs] == [10, 4]
    for r in runs:
        assert r["slope_per_mA"] < 0 and np.isfinite(r["slope_per_mA"])
        assert r["amp_min_mA"] < r["amp_max_mA"]
    assert out["n_runs_slope_negative"] == 2 and out["n_runs_slope_positive"] == 0
    rising = AE.pooled_shape_for_band(_two_runs(), CENTRES[0], "ONE_THREE_LEFT")
    assert rising["n_runs_slope_positive"] == 2 and rising["n_runs_slope_negative"] == 0
    # a run with one current has no slope and is counted as such
    one = _comparison(label="run C", panel=_panel([2.0]))
    out3 = AE.pooled_shape_for_band(_build(_comparison(label="run A"), one), CENTRES[3], "ONE_THREE_LEFT")
    assert [r["run"] for r in out3["per_run_slopes"]] == ["run A"]
    assert out3["n_runs_without_slope"] == 1


def test_t2_the_stored_table_carries_the_per_run_slopes_as_json_and_the_counts():
    table = AE.pooled_table_from_build(_two_runs(), checked_lo_hz=7.8, checked_hi_hz=28.3,
                                       band_half_hz=2.5)
    for k in ("per_run_slopes_json", "n_runs_slope_negative", "n_runs_slope_positive",
              "n_runs_without_slope"):
        assert k in AE.POOLED_FIELDS and k in table.columns
    row = table[np.isclose(table["band_center_hz"], CENTRES[3])].iloc[0]
    runs = json.loads(row["per_run_slopes_json"])
    assert [r["run"] for r in runs] == ["run A", "run B"] and all(r["slope_per_mA"] < 0 for r in runs)
    assert int(row["n_runs_slope_negative"]) == 2
    assert AE.POOLED_RULE_VERSION.startswith("v6_")


def test_t2_the_e1_note_reads_the_per_run_slopes_out():
    row = {"pooled_slope_per_mA": -7.9, "pooled_slope_stderr": 6.0, "pooled_slope_p": 0.21,
           "n": 18, "n_visits": 6, "verdict": "x", "curves": False, "p_curvature": 0.4,
           "n_runs_slope_negative": 4, "n_runs_slope_positive": 2, "n_runs_without_slope": 0,
           "per_run_slopes_json": json.dumps([
               {"run": "2026-09-16 a", "slope_per_mA": -20.1, "n": 5, "amp_min_mA": 1.0, "amp_max_mA": 4.5},
               {"run": "2026-08-18", "slope_per_mA": 5.3, "n": 3, "amp_min_mA": 1.0, "amp_max_mA": 3.0}])}
    e = ED.pooled_actuation_edge(row, scale="device_units")
    assert "PER RUN: 4 of 6 runs fall with current, 2 rise" in e.note
    assert "-20.1" in e.note and "+5.3" in e.note
    assert "runs disagree" in e.confounded_by
    agree = dict(row, n_runs_slope_negative=6, n_runs_slope_positive=0)
    e2 = ED.pooled_actuation_edge(agree, scale="device_units")
    assert "runs disagree" not in e2.confounded_by
    # a stored row from before the field existed says so instead of inventing counts
    old = {k: v for k, v in row.items() if not k.startswith("n_runs") and k != "per_run_slopes_json"}
    e3 = ED.pooled_actuation_edge(old, scale="device_units")
    assert "per-run slopes not stored" in e3.note


# --- T3 ---------------------------------------------------------------------------------------
def _series(n=600, dt=3.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    p = 150.0 + 40.0 * rng.standard_normal(n)
    return t, p


def test_t3_occupancy_is_reported_on_both_clocks_when_they_differ():
    t, p = _series()
    out = OC.threshold_occupancy_two_clocks(t, p, upper=160.0, lower=140.0,
                                            averaging_s=3.0, programmed_averaging_s=30.0)
    assert out["available"] is True and out["averaging_s"] == 3.0
    prog = out["programmed_clock"]
    assert prog["available"] is True and prog["averaging_s"] == 30.0
    assert prog["n_readings"] < out["n_readings"]
    # averaging over ten readings shrinks the scatter, so more land between the pair
    assert prog["frac_between"] > out["frac_between"]
    assert "At the 30 s averaging the device runs today" in out["why"]
    assert f"{100 * prog['frac_between']:.1f}% between" in out["why"]
    assert out["clocks_differ"] is True


def test_t3_one_clock_when_the_device_runs_the_recommended_averaging_or_none_is_known():
    t, p = _series()
    same = OC.threshold_occupancy_two_clocks(t, p, upper=160.0, lower=140.0,
                                             averaging_s=3.0, programmed_averaging_s=3.0)
    assert same["clocks_differ"] is False and same["programmed_clock"]["available"] is True
    assert "the device runs today" not in same["why"]
    assert "The device runs this 3 s averaging today, so the answer is the same" in same["why"]
    unknown = OC.threshold_occupancy_two_clocks(t, p, upper=160.0, lower=140.0,
                                                averaging_s=3.0, programmed_averaging_s=None)
    assert unknown["programmed_clock"]["available"] is False
    assert "not known" in unknown["programmed_clock"]["reason"]
    base = OC.threshold_occupancy(t, p, upper=160.0, lower=140.0, averaging_s=3.0)
    for k in ("frac_above", "frac_between", "frac_below", "median_level", "warning"):
        assert unknown[k] == base[k]                       # the recommended clock is unchanged


def test_t3_the_row_sentence_carries_both_clocks():
    t, p = _series()
    out = OC.threshold_occupancy_two_clocks(t, p, upper=160.0, lower=140.0,
                                            averaging_s=3.0, programmed_averaging_s=30.0)
    note = PR.occupancy_note(out)
    assert "At the 3 s averaging duration in force" in note
    assert "At the 30 s averaging the device runs today" in note


# --- C3 ---------------------------------------------------------------------------------------
def test_c3_the_simulation_regimes_name_the_timing_values_the_record_cannot_decide():
    uid = "p-c3"
    prev = dict(TR.RECORD_DERIVED_TIMING_MS)
    try:
        TR.RECORD_DERIVED_TIMING_MS[uid] = {"onset_upper_ms": 30_000.0, "onset_lower_ms": 30_000.0,
                                            "averaging_ms": 3_000.0, "transition_up_ms": 30_000.0,
                                            "transition_down_ms": 30_000.0, "detection_blanking_ms": 30_000.0}
        dev = {"active_sensing_group_timing": {"Left": {
            "averaging_ms": 30_000.0, "onset_upper_ms": 30_000.0, "onset_lower_ms": 30_000.0,
            "detection_blanking_ms": 30_000.0, "transition_up_ms": 4_000.0, "transition_down_ms": 4_000.0}}}
        out = AD._timing_runs_for_simulation(uid, "Left", dev)
        rec = out["recommended"]
        assert rec["low_confidence_fields"] == ["detection_blanking_ms", "transition_up_ms", "transition_down_ms"]
        assert rec["timing_qualifier"].startswith("using three timing values the record cannot decide")
        assert "transition up" in rec["timing_qualifier"] and "detection blanking" in rec["timing_qualifier"]
        # what the device runs is a measurement, not a recommendation: nothing to qualify
        assert out["programmed"]["low_confidence_fields"] == [] and out["programmed"]["timing_qualifier"] is None
    finally:
        TR.RECORD_DERIVED_TIMING_MS.clear()
        TR.RECORD_DERIVED_TIMING_MS.update(prev)
    assert SIM.RULE_VERSION.startswith("v7_")
