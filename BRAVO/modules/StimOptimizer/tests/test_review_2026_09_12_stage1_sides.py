"""Review of 2026-09-12, findings S1 and S2: Stage 1 reads each side's OWN pulse width, and a
pulse width in force with no fittable joint stratum is NOT ASSESSED rather than "resolved" on a
contrast between two other strata.

REWRITTEN 2026-09-14 for the joint (rate, amplitude-Left, amplitude-Right) redesign. The original
version of this file tested each side being stratified on its OWN pulse-width axis entirely
INDEPENDENTLY of the other side -- a separate ``res.slices[(hemisphere, pw)]`` dictionary per
side, and a helper, ``pw_col_for``, that resolved one side's pulse-width column in isolation. That
machinery is gone by design: pulse width is now stratified as a PAIR (both sides' pulse widths
together), because the joint fit that replaces two independent per-hemisphere fits needs one
stratum per pair, not one per side. Per this project's own rule (a test whose name asserts
something untrue is worse than no test), those tests are not kept passing under a relabelled
premise; what is still true and still tested here is the part of S1/S2 that survives the redesign
intact: each side's pulse width in force is still read from its own column
(``pw_us_Left``/``pw_us_Right``), a missing Right column still falls back to the Left one and
says so, and a pulse-width choice with no fittable joint stratum at the incumbent's own pair is
still NOT ASSESSED rather than silently called resolved.

The "best of the other strata" fallback contrast the original S2 finding reported for the record
(never as the verdict) is not carried into the joint redesign: with one joint decision rather than
one per side, there is no longer a well-defined "other side" contrast to compute when the
incumbent's own pair has no surface, so the joint module reports NOT ASSESSED with no fallback
number rather than inventing one. This is a deliberate simplification, not an oversight.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1


def _matrix(n_per_cell=10, pw_levels=(60.0, 140.0), rates=(55.0, 110.0), seed=0,
           right_pw=150.0, aliased=False):
    """Left pulse width takes `pw_levels`; the Right column is a DIFFERENT constant, the structure
    RCS08's own matched table has (67 of 92 epochs differ)."""
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
    """Left at 60/140 us over two rates; Right at 150 us throughout, so every joint stratum's
    pair is (Left level, 150.0)."""
    return S1.run_stage1(_matrix(), data_horizon="test", washin_min=1.0)


# ---------------------------------------------------------------------------------------------
# S1: the Right side is stratified and labelled by pw_us_Right, the Left by pw_us_Left, jointly
# ---------------------------------------------------------------------------------------------
def test_the_right_side_reads_its_own_pulse_width_column(both_sides_own_columns):
    res = both_sides_own_columns
    right = res.frozen.setting("Right")
    assert right.pw_us == 150.0, right.pw_us
    assert {k[1] for k in res.slices} == {150.0}
    assert res.frozen.audit["per_hemisphere"]["Right"]["pw_col"] == "pw_us_Right"
    assert res.frozen.audit["per_hemisphere"]["Right"]["pw_col_fallback"] is False
    assert res.frozen.incumbent_pw_us_by_side == {"Left": 140.0, "Right": 150.0}


def test_the_left_side_still_reads_the_left_column(both_sides_own_columns):
    res = both_sides_own_columns
    assert {k[0] for k in res.slices} == {60.0, 140.0}
    assert res.frozen.audit["per_hemisphere"]["Left"]["pw_col"] == "pw_us_Left"
    assert res.frozen.incumbent_pw_us == 140.0          # the historical name keeps the Left value
    assert res.frozen.setting("Left").pw_us in (60.0, 140.0)


def test_a_missing_right_column_falls_back_to_the_left_and_says_so():
    d = _matrix().drop(columns=["pw_us_Right"])
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    h = res.frozen.audit["per_hemisphere"]["Right"]
    assert h["pw_col"] == "pw_us_Left" and h["pw_col_fallback"] is True
    s = res.frozen.setting("Right")
    assert s.pw_us in (60.0, 140.0)                       # the LEFT column's levels


def test_an_explicit_absent_column_is_not_observed_not_substituted():
    """A caller naming a column that is not there asked about that column: NOT OBSERVED."""
    d = _matrix().drop(columns=["pw_us_Right"])
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0, pw_col="pw_us_Right")
    for s in res.frozen.settings:
        assert s.pw_us is None and s.pw_resolved is None
    assert res.frozen.audit["per_hemisphere"]["Right"]["pw_col_fallback"] is False


# ---------------------------------------------------------------------------------------------
# S2: the pulse-width pair in force has too few epochs for a surface -> NOT ASSESSED, never
# resolved on a comparison that does not involve the setting in force
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def incumbent_on_a_thin_stratum():
    """Two pairs (60/150 and 140/150 us) with 20 epochs each, and the incumbent on a 100/150 us
    pair that has only 4 epochs -- below the 8-epoch stratum floor -- so no surface exists at the
    pulse-width pair in force."""
    d = _matrix(n_per_cell=10, pw_levels=(60.0, 140.0), rates=(55.0, 110.0))
    thin = d.iloc[:4].copy()
    thin["epoch"] = [9001.0, 9002.0, 9003.0, 9004.0]
    thin["pw_us_Left"] = 100.0
    thin["freq_hz"] = 55.0
    d = pd.concat([d, thin], ignore_index=True)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")   # thin = newest
    return S1.run_stage1(d, data_horizon="test", washin_min=1.0)


def test_the_incumbent_is_the_thin_stratum(incumbent_on_a_thin_stratum):
    res = incumbent_on_a_thin_stratum
    assert res.frozen.incumbent_pw_us == 100.0
    assert "pwL100_pwR150" in res.skipped
    assert "4 fitted epochs at (Left 100 us, Right 150 us)" in res.skipped["pwL100_pwR150"]
    assert {k[0] for k in res.slices} == {60.0, 140.0}


def test_pw_resolved_is_none_not_true_when_the_pulse_width_pair_in_force_has_no_surface(
        incumbent_on_a_thin_stratum):
    s = incumbent_on_a_thin_stratum.frozen.setting("Left")
    assert s.pw_resolved is None, s.reasons
    assert s.resolved is False
    assert incumbent_on_a_thin_stratum.frozen.resolved is False
    assert s.detail["incumbent_pw_us_left"] == 100.0
    assert s.detail["incumbent_pw_us_right"] == 150.0


def test_the_reason_names_not_assessed_and_never_claims_resolution(incumbent_on_a_thin_stratum):
    s = incumbent_on_a_thin_stratum.frozen.setting("Left")
    joined = " ".join(s.reasons)
    assert "NOT ASSESSED" in joined
    assert "no fitted joint stratum of its own" in joined
    assert "IS resolved" not in joined


def test_a_fittable_pulse_width_pair_in_force_is_the_reference_of_the_contrast():
    """The control: with the incumbent on a fitted pair (140/150 us, 20 epochs) the contrast's
    reference IS the pulse-width pair in force, and the thin-stratum NOT ASSESSED branch never
    fires."""
    res = S1.run_stage1(_matrix(n_per_cell=10, pw_levels=(60.0, 140.0), rates=(55.0, 110.0)),
                        data_horizon="test", washin_min=1.0)
    s = res.frozen.setting("Left")
    assert res.frozen.incumbent_pw_us == 140.0
    assert not any("no fitted joint stratum of its own" in r for r in s.reasons)
    assert not any("below the 8-epoch floor" in r for r in s.reasons)
