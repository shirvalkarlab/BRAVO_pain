"""Review of 2026-09-12, findings S1 and S2: Stage 1 reads each side's OWN pulse width, and a
pulse width in force with no fittable stratum is NOT ASSESSED rather than "resolved" on a
contrast between two other strata.

Every assertion here is on a VALUE -- which side, which pulse width, which label -- never on the
shape of the result. The matrices are constructed so the Left and Right pulse-width columns
differ, which is the structure RCS08's own matched table has (67 of 92 epochs differ).
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1


def _matrix(n_per_cell=10, pw_levels=(60.0, 140.0), rates=(55.0, 110.0), seed=0,
            right_pw=150.0, aliased=False):
    """Left pulse width takes `pw_levels`; the Right column is a DIFFERENT constant."""
    rng = np.random.default_rng(seed)
    rows, ep = [], 0
    for i, pw in enumerate(pw_levels):
        use = (rates[i % len(rates)],) if aliased else rates
        for rate in use:
            for k in range(n_per_cell):
                ep += 1
                rows.append(dict(
                    epoch=float(ep), freq_hz=float(rate), pw_us_Left=float(pw),
                    pw_us_Right=float(right_pw),
                    amp_mA_Left=float(1.0 + 0.2 * (k % 5)),
                    amp_mA_Right=float(1.2 + 0.2 * (k % 4)),
                    n=8.0, dur_h=200.0,
                    left_leg_vas=float(50.0 + 3.0 * rng.standard_normal()),
                    left_leg_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


@pytest.fixture(scope="module")
def both_sides_own_columns():
    """Left at 60/140 us over two rates; Right at 150 us throughout."""
    return S1.run_stage1(_matrix(), data_horizon="test", washin_min=1.0)


# ---------------------------------------------------------------------------------------------
# S1: the Right side is stratified and labelled by pw_us_Right, the Left by pw_us_Left
# ---------------------------------------------------------------------------------------------
def test_the_right_side_reads_its_own_pulse_width_column(both_sides_own_columns):
    res = both_sides_own_columns
    right = res.frozen.setting("Right")
    assert right.pw_us == 150.0, right.pw_us
    assert {k for k in res.slices if k[0] == "Right"} == {("Right", 150.0)}
    assert res.frozen.audit["per_hemisphere"]["Right"]["pw_col"] == "pw_us_Right"
    assert res.frozen.audit["per_hemisphere"]["Right"]["pw_col_fallback"] is False
    assert res.frozen.incumbent_pw_us_by_side == {"Left": 140.0, "Right": 150.0}
    # the Right's design audit counts the Right column, not the Left's two levels
    assert res.frozen.audit["per_hemisphere"]["Right"]["design"]["pw_levels"] == [150.0]


def test_the_left_side_still_reads_the_left_column(both_sides_own_columns):
    res = both_sides_own_columns
    assert {k for k in res.slices if k[0] == "Left"} == {("Left", 60.0), ("Left", 140.0)}
    assert res.frozen.audit["per_hemisphere"]["Left"]["pw_col"] == "pw_us_Left"
    assert res.frozen.incumbent_pw_us == 140.0          # the historical name keeps the Left value
    assert res.frozen.setting("Left").pw_us in (60.0, 140.0)


def test_the_left_side_is_unchanged_by_the_right_column_existing():
    """Field for field on the Left setting and strata: with and without a pw_us_Right column."""
    d = _matrix()
    with_right = S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    without = S1.run_stage1(d.drop(columns=["pw_us_Right"]), hemispheres=("Left",),
                            data_horizon="test", washin_min=1.0)
    a, b = with_right.frozen.setting("Left"), without.frozen.setting("Left")
    for f in ("rate_hz", "pw_us", "amp_star_mA", "n_epochs_fitted", "rate_resolved",
              "pw_resolved", "reasons"):
        assert getattr(a, f) == getattr(b, f), f
    pd.testing.assert_frame_equal(with_right.summary, without.summary)


def test_a_missing_right_column_falls_back_to_the_left_and_says_so():
    d = _matrix().drop(columns=["pw_us_Right"])
    res = S1.run_stage1(d, hemispheres=("Right",), data_horizon="test", washin_min=1.0)
    h = res.frozen.audit["per_hemisphere"]["Right"]
    assert h["pw_col"] == "pw_us_Left" and h["pw_col_fallback"] is True
    s = res.frozen.setting("Right")
    assert s.pw_us in (60.0, 140.0)                       # the LEFT column's levels
    assert any("PULSE-WIDTH COLUMN FALLBACK" in r and "pw_us_Right" in r for r in s.reasons)
    assert s.detail["pw_col_fallback"] is True


def test_an_explicit_absent_column_is_not_observed_not_substituted():
    """A caller naming a column that is not there asked about that column: NOT OBSERVED."""
    d = _matrix().drop(columns=["pw_us_Right"])
    res = S1.run_stage1(d, hemispheres=("Right",), data_horizon="test", washin_min=1.0,
                        pw_col="pw_us_Right")
    s = res.frozen.setting("Right")
    assert s.pw_us is None and s.pw_resolved is None
    assert res.frozen.audit["per_hemisphere"]["Right"]["pw_col_fallback"] is False


def test_pw_col_for_resolves_own_then_fallback_then_explicit():
    assert S1.pw_col_for("Right", ["pw_us_Left", "pw_us_Right"]) == ("pw_us_Right", False)
    assert S1.pw_col_for("Right", ["pw_us_Left"]) == ("pw_us_Left", True)
    assert S1.pw_col_for("Right", ["pw_us_Left"], pw_col="pw_us_Right") == ("pw_us_Right", False)
    assert S1.pw_col_for("Left", ["pw_us_Left", "pw_us_Right"]) == ("pw_us_Left", False)


# ---------------------------------------------------------------------------------------------
# S2: the pulse width in force has too few epochs for a surface -> NOT ASSESSED, never resolved
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def incumbent_on_a_thin_stratum():
    """Two levels (60 and 140 us) with 20 epochs each, and the incumbent on a 100 us level that
    has only 4 epochs -- below the 8-epoch stratum floor -- so no surface exists at the pulse
    width in force. The Left column is used for both sides here so the fixture stays small."""
    d = _matrix(n_per_cell=10, pw_levels=(60.0, 140.0), rates=(55.0, 110.0))
    thin = d.iloc[:4].copy()
    thin["epoch"] = [9001.0, 9002.0, 9003.0, 9004.0]
    thin["pw_us_Left"] = 100.0
    thin["freq_hz"] = 55.0
    d = pd.concat([d, thin], ignore_index=True)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")   # thin = newest
    return S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)


def test_the_incumbent_is_the_thin_stratum(incumbent_on_a_thin_stratum):
    res = incumbent_on_a_thin_stratum
    assert res.frozen.incumbent_pw_us == 100.0
    assert "Left__pw100" in res.skipped and "4 fitted epochs at 100 us" in res.skipped["Left__pw100"]
    assert {k[1] for k in res.slices} == {60.0, 140.0}


def test_pw_resolved_is_none_not_true_when_the_pulse_width_in_force_has_no_surface(
        incumbent_on_a_thin_stratum):
    s = incumbent_on_a_thin_stratum.frozen.setting("Left")
    assert s.pw_resolved is None, s.reasons
    assert s.resolved is False
    assert incumbent_on_a_thin_stratum.frozen.resolved is False
    assert s.detail["pw_reference_us"] is None
    assert s.detail["pw_in_force_n_epochs"] == 4
    assert s.detail["incumbent_pw_us"] == 100.0


def test_the_reason_names_the_count_and_the_floor(incumbent_on_a_thin_stratum):
    s = incumbent_on_a_thin_stratum.frozen.setting("Left")
    joined = " ".join(s.reasons)
    assert "NOT ASSESSED" in joined
    assert "(100 us) has 4 epochs, below the 8-epoch stratum floor" in joined
    assert "would not be a comparison with the setting in force" in joined
    assert "IS resolved" not in joined


def test_the_best_of_the_others_contrast_is_a_number_on_the_record_not_the_verdict(
        incumbent_on_a_thin_stratum):
    s = incumbent_on_a_thin_stratum.frozen.setting("Left")
    c = s.detail["pw_contrast_between_other_strata"]
    assert {c["from_pw_us"], c["to_pw_us"]} == {60.0, 140.0}
    assert np.isfinite(c["gain"]) and c["sd_of_difference"] > 0
    assert "never the verdict" in c["note"]


def test_a_fittable_pulse_width_in_force_is_the_reference_of_the_contrast():
    """The control: with the incumbent on a fitted stratum (140 us, 20 epochs) the contrast's
    reference IS the pulse width in force and the S2 branch never fires. Whether the contrast
    then resolves, or is refused because the reference stratum never ran the chosen rate (the
    pre-existing rule), is a separate question this test does not pin."""
    res = S1.run_stage1(_matrix(n_per_cell=10, pw_levels=(60.0, 140.0), rates=(55.0, 110.0)),
                        hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    s = res.frozen.setting("Left")
    assert res.frozen.incumbent_pw_us == 140.0
    assert s.detail["pw_reference_us"] == 140.0
    assert "pw_contrast_between_other_strata" not in s.detail
    assert "pw_in_force_n_epochs" not in s.detail
    assert not any("below the 8-epoch stratum floor" in r for r in s.reasons)
