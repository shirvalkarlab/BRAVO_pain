"""The stored pooled within-visit table, and the rule that a partial pool is never written.

WHY THIS EXISTS. The consistency check (decision 74) combines two links: current -> power, pooled
across every stimulation-current ladder, and power -> pain from the calibrated grid. When the check
was first wired into `report_for_participant` it pooled from `_3build` — and that build is truncated
to the runs the PAGE draws whenever the amplitude-effect and ground-truth entries already exist,
which is the steady state after the first request.

Measured live on RCS08, ONE_THREE_LEFT at 17.5 Hz, the same band on the same day:

    cold cache, every run  -> 13 points across 4 visits, "no straight-line movement detected"
    warm cache, 4 runs     ->  6 points across 1 visit,  "not assessed"

The 13 across 4 is exactly what decision 56 measured for this contact. **An answer that depends on
what happened to be cached is not a finding**, and the wrong half of that pair is the one a reader
would almost always have seen. The fix is a stored table pooled from every run, read on every
request — proven live afterwards to give 13 points across 4 visits cold, warm, and warm again.

These tests hold the two rules that keep it that way.
"""
import pandas as pd
import pytest

try:
    from modules.ClosedLoopDeployment import adapter, amplitude_effect, direction_consistency
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import adapter, amplitude_effect, direction_consistency


# --------------------------------------------------------------------------------------------
# 1. a partial pool is never stored
# --------------------------------------------------------------------------------------------

def test_a_pooled_table_from_a_truncated_build_is_refused(monkeypatch):
    """THE RULE THAT MATTERS. A stored wrong answer is worse than no stored answer, because
    everything downstream then trusts it."""
    called = []
    monkeypatch.setattr(amplitude_effect, "pooled_table_from_build",
                        lambda *a, **k: called.append(1) or pd.DataFrame())

    got = adapter.write_pooled_shape(object(), {"comparisons": [{"x": 1}]}, is_every_run=False)

    assert got["written"] is False
    assert got["n_rows"] == 0
    assert "fraction of the visits" in got["reason"]
    assert not called, (
        "the table was derived before the refusal — it must not even be computed from a truncated "
        "build, or a later edit could accidentally store it")


def test_a_build_with_no_runs_is_reported_not_stored():
    got = adapter.write_pooled_shape(object(), {"comparisons": []}, is_every_run=True)
    assert got["written"] is False
    assert "no run of rising current" in got["reason"]


def test_an_absent_reason_from_the_build_is_carried_through():
    got = adapter.write_pooled_shape(
        object(), {"comparisons": [], "absent_reason": "the recordings could not be decoded"},
        is_every_run=True)
    assert got["written"] is False
    assert got["reason"] == "the recordings could not be decoded"


# --------------------------------------------------------------------------------------------
# 2. the check reads the stored row rather than re-pooling
# --------------------------------------------------------------------------------------------

def test_for_band_uses_the_stored_row_and_does_not_pool_again(monkeypatch):
    """If `for_band` ever re-pools while holding a stored row, the truncation defect returns
    silently — the answer would look the same in a cold test and be wrong in production."""
    pooled_calls = []
    monkeypatch.setattr(amplitude_effect, "pooled_shape_for_band",
                        lambda *a, **k: pooled_calls.append(1) or {})

    stored = {"pooled_direction": "band power rises as current rises",
              "pooled_slope_per_mA": 0.4, "pooled_slope_p": 0.01, "n": 13, "n_visits": 4}
    grid = {"available": True, "band_time_sweep": {"L": {"best_correlation_rows": [
        {"band_center_hz": 17.5, "pearson_r": -0.5, "p_selection_aware": 0.01}]}}}

    got = direction_consistency.for_band({"comparisons": []}, grid, "L", 17.5, pooled=stored)

    assert not pooled_calls, "for_band re-pooled from the build despite being handed a stored row"
    assert got["within_visit_n_points"] == 13
    assert got["within_visit_n_visits"] == 4
    # rises with current, and higher power means LESS pain -> raising current should relieve
    assert "relieve" in got["implied_control_direction"]


def test_without_a_stored_row_for_band_still_pools_from_the_build(monkeypatch):
    """The build path is kept, not deleted — a caller that genuinely holds every run may use it,
    and the tests do."""
    monkeypatch.setattr(amplitude_effect, "pooled_shape_for_band",
                        lambda *a, **k: {"pooled_direction": "not assessed"})
    got = direction_consistency.for_band({"comparisons": []}, None, "L", 17.5)
    assert got["implied_control_direction"] == "not assessed"


# --------------------------------------------------------------------------------------------
# 3. reading one row out of the table
# --------------------------------------------------------------------------------------------

def _table():
    return pd.DataFrame([
        {"sensing_contact": "L", "band_center_hz": 17.5, "pooled_direction": "rises",
         "pooled_slope_per_mA": 0.4, "pooled_slope_stderr": 0.1, "pooled_slope_p": 0.01,
         "n": 13, "n_visits": 4, "verdict": "ok", "curves": False, "peaks_inside": False,
         "peak_mA": float("nan"), "p_curvature": float("nan"), "r2_linear": 0.5,
         "r2_quadratic": 0.5},
        {"sensing_contact": "R", "band_center_hz": 17.5, "pooled_direction": "falls",
         "pooled_slope_per_mA": -0.2, "pooled_slope_stderr": 0.1, "pooled_slope_p": 0.04,
         "n": 9, "n_visits": 3, "verdict": "ok", "curves": False, "peaks_inside": False,
         "peak_mA": float("nan"), "p_curvature": float("nan"), "r2_linear": 0.4,
         "r2_quadratic": 0.4},
    ])


def test_pooled_row_matches_on_contact_and_centre_together():
    """Two contacts share a band centre. Matching on the centre alone would hand back another
    electrode's dose-response — the conflation decision 74's own contact fix already had to correct
    once."""
    left = amplitude_effect.pooled_row(_table(), "L", 17.5)
    right = amplitude_effect.pooled_row(_table(), "R", 17.5)
    assert left["pooled_direction"] == "rises" and left["n_visits"] == 4
    assert right["pooled_direction"] == "falls" and right["n_visits"] == 3


def test_pooled_row_is_none_when_the_point_is_not_in_the_table():
    assert amplitude_effect.pooled_row(_table(), "L", 29.5) is None
    assert amplitude_effect.pooled_row(_table(), "MISSING", 17.5) is None
    assert amplitude_effect.pooled_row(None, "L", 17.5) is None
    assert amplitude_effect.pooled_row(pd.DataFrame(), "L", 17.5) is None


def test_the_stored_row_carries_every_field_the_check_reads():
    row = amplitude_effect.pooled_row(_table(), "L", 17.5)
    for k in ("pooled_direction", "pooled_slope_per_mA", "pooled_slope_p", "n", "n_visits"):
        assert k in row, f"{k} is missing, and direction_consistency reads it"


def test_the_new_kind_is_registered_with_its_writer():
    """A derived kind written with no registered writer looks like a raw input to anything that
    later cites it (decision 39)."""
    try:
        from modules.CacheStore import provenance as prov
    except ImportError:                                          # pragma: no cover
        from CacheStore import provenance as prov
    assert prov._WRITER_BY_KIND[amplitude_effect.POOLED_KIND] == "closed_loop"
    assert amplitude_effect.POOLED_KIND not in prov.RAW_KINDS, (
        "the pooled table is derived from the tile entry, not a raw input")
