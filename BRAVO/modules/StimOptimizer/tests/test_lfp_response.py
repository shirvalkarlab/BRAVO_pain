"""Tests for the LFP-responds-to-stimulation gate (manual p. 35 requirement).

Merged here 2026-10-05: test_no_log_power_readiness.py (each under its own heading below).
"""
import numpy as np
import pytest

from StimOptimizer.routines import lfp_response as LR
import inspect
from StimOptimizer.routines import lfp_evidence as LE
from StimOptimizer.routines import stage_gate as SG


def _synth(n_per=40, suppression=True, effect=0.8, noise=0.25, seed=0, n_eras=3,
           era_collinear=False):
    """Two capture arms with a controllable multiplicative amplitude effect.

    `era` is CROSSED with amplitude by default (each era contains both arms), which is what makes
    the amplitude effect identifiable after blocking. Pass era_collinear=True to nest era within
    amplitude instead — the pathological case this record actually resembles, where amplitude rose
    over time and era-blocking therefore removes the very contrast under test.
    """
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.5, 3.5], n_per)
    # Band power in DEVICE UNITS (decision 202, 2026-09-19; a log-scale construction until then):
    # 100 units at the low arm; a suppression DIVIDES the level by (1 + effect) at the high arm
    # (effect=1.0 halves it), an elevation multiplies by the same -- monotone in current and never
    # zero -- with a MULTIPLICATIVE scatter whose coefficient of variation is `noise`, drawn from a
    # gamma distribution so power stays strictly positive without any logarithm.
    factor = 1.0 + effect * (amp - 1.5) / 2.0
    level = 100.0 / factor if suppression else 100.0 * factor
    k = 1.0 / (noise ** 2)
    p = level * rng.gamma(shape=k, scale=1.0 / k, size=amp.size)
    if era_collinear:
        era = np.repeat(np.arange(n_eras), int(np.ceil(amp.size / n_eras)))[:amp.size]
    else:
        era = np.tile(np.arange(n_eras), int(np.ceil(amp.size / n_eras)))[:amp.size]
    clus = np.arange(amp.size) // 4
    return p, amp, era, clus


def test_a_suppressing_band_passes_for_a_suppression_mode():
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    r = LR.assess_response(p, a, era=era, cluster=cl, mode_requires="suppression")
    assert r.responds is True and r.direction_ok is True
    assert r.power_high < r.power_low
    assert r.captures_inverted is False
    assert r.slope_per_mA < 0 and r.slope_p < 0.05
    assert "RESPONDS" in r.describe()


def test_the_same_band_FAILS_for_an_elevation_mode():
    """Direction is mode-specific: the identical data cannot satisfy both."""
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    r = LR.assess_response(p, a, era=era, cluster=cl, mode_requires="elevation")
    assert r.responds is False and r.direction_ok is False
    assert r.captures_inverted is True and "WRONG WAY" in r.reason


def test_a_statistically_significant_but_tiny_response_still_fails():
    """THE POINT OF THE SEPARATION CRITERION. With enough rows a trivial effect is significant, but
    a threshold placed between two nearly-identical captures is not usable."""
    p, a, era, cl = _synth(n_per=400, suppression=True, effect=0.05, noise=0.25, seed=3)
    r = LR.assess_response(p, a, era=era, cluster=cl)
    assert r.slope_p < 0.05, "fixture should be significant, else it tests nothing"
    assert r.direction_ok is True
    assert r.responds is False and "TOO CLOSE" in r.reason
    assert r.separation_d < LR.MIN_CAPTURE_SEPARATION_D


def test_no_amplitude_variation_is_not_assessed_rather_than_negative():
    """Absence of an identifiable effect is not evidence of no effect."""
    p = np.full(60, 100.0) + np.random.default_rng(0).normal(0, 1, 60)
    r = LR.assess_response(p, np.full(60, 2.0))
    assert r.responds is None and "never varied" in r.reason
    assert "NOT ASSESSED" in r.describe()


def test_too_few_rows_is_not_assessed():
    r = LR.assess_response(np.array([100.0, 90.0, 80.0]), np.array([1.0, 2.0, 3.0]))
    assert r.responds is None and "usable rows" in r.reason


def test_thin_capture_arms_are_not_assessed():
    """Many amplitude levels but none with enough rows must not be forced into a verdict."""
    rng = np.random.default_rng(1)
    a = np.repeat(np.arange(1.0, 6.0, 0.25), 3)          # 3 rows per level
    p = 100.0 - 30.0 * a + rng.normal(0, 10.0, a.size)
    r = LR.assess_response(p, a)
    assert r.responds is None and "rows" in r.reason


def test_era_blocking_is_applied_and_its_absence_is_disclosed():
    """The amplitude effect is confounded with time in this record; a run without era blocking must
    say so rather than presenting the estimate as adjusted."""
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    with_era = LR.assess_response(p, a, era=era, cluster=cl)
    without = LR.assess_response(p, a, cluster=cl)
    assert with_era.n_eras > 1
    assert without.n_eras == 0
    assert any("era NOT blocked" in n for n in without.notes)
    assert not any("era NOT blocked" in n for n in with_era.notes)


def test_unadjusted_slope_is_reported_beside_the_adjusted_one():
    """So the size of the time confound is visible rather than asserted away."""
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    r = LR.assess_response(p, a, era=era, cluster=cl)
    assert np.isfinite(r.slope_unadjusted) and np.isfinite(r.slope_per_mA)


def test_missing_cluster_variable_is_disclosed_as_anticonservative():
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    r = LR.assess_response(p, a, era=era)
    assert any("NOT cluster-robust" in n for n in r.notes)


def test_nonpositive_power_rows_are_dropped_and_counted():
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    p = p.copy(); p[:5] = 0.0
    r = LR.assess_response(p, a, era=era, cluster=cl)
    assert any("non-positive power" in n for n in r.notes)


def test_bad_arguments_are_refused():
    with pytest.raises(ValueError, match="same shape"):
        LR.assess_response(np.ones(10), np.ones(9))
    with pytest.raises(ValueError, match="mode_requires"):
        LR.assess_response(np.ones(30) * 5, np.repeat([1.0, 2.0], 15), mode_requires="whatever")


def test_era_collinear_with_amplitude_destroys_the_estimate_not_silently():
    """THE PATHOLOGY THIS RECORD ACTUALLY HAS, demonstrated rather than asserted.

    Amplitude rose over time in this patient's record, so if eras are nested within amplitude
    instead of crossed with it, blocking on era removes the very contrast under test.

    An earlier version of this test used effect=1.0, where the signal is so strong that the nested
    fit still returns p = 5e-82 — so it demonstrated nothing, and its docstring's claim of "a null
    result nested" was false. Its assertion was also merely nested_p > crossed_p, which two numbers
    both indistinguishable from zero satisfy vacuously. Parameters are now chosen where the
    pathology genuinely bites, and the assertions state the outcome rather than an ordering:
    at effect=0.20 with noise=0.6 the crossed fit gives p about 0.0035 (significant) while the
    nested fit gives p about 0.42 (null) on the same underlying effect. (Those were noise=1.0,
    0.004 and 0.34 while the fixture and the fit were on the log scale; re-measured on the raw
    device scale when decision 202 moved both, 2026-09-19.)

    The capture contrast survives both, because it compares the two amplitude arms directly and
    never conditions on era. That is precisely why the module's verdict does not rest on the slope.
    """
    crossed = LR.assess_response(*_synth(n_per=200, effect=0.20, noise=0.6)[:2],
                                 era=_synth(n_per=200, effect=0.20, noise=0.6)[2],
                                 cluster=_synth(n_per=200, effect=0.20, noise=0.6)[3])
    p, a, era, cl = _synth(n_per=200, effect=0.20, noise=0.6, era_collinear=True)
    nested = LR.assess_response(p, a, era=era, cluster=cl)

    assert crossed.slope_p < 0.01, (
        f"crossed fixture must be estimable or this tests nothing (got {crossed.slope_p:.3g})")
    assert nested.slope_p > 0.05, (
        f"nested fixture must LOSE the effect, which is the pathology under test "
        f"(got {nested.slope_p:.3g})")
    # The capture contrast is unaffected: it does not condition on era.
    assert nested.direction_ok is True


# ================================================================================================
# From test_no_log_power_readiness.py (merged here 2026-10-05).
# Decision 202 (the PI, 2026-09-19): log power is used in no calculation. The Stim Optimizer's
# readiness screen -- "falls with current once the time confound is removed", the current half of
# decision 199's one-band rule -- fitted its era-blocked slope on np.log(power). It now fits raw device
# power, and the slope is in device units per mA, the units the device thresholds in.
# ================================================================================================


def _linear_fixture(slope_per_mA=-20.0, n_per=24, noise=4.0, seed=0):
    """Two capture arms whose band power is a STRAIGHT LINE in current, in device units, with era
    crossed with current so blocking leaves the effect identifiable."""
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.5, 3.5], n_per)
    p = 200.0 + slope_per_mA * (amp - 1.5) + rng.normal(0, noise, amp.size)
    era = np.tile(np.arange(3), int(np.ceil(amp.size / 3)))[: amp.size]
    clus = np.arange(amp.size) // 4
    return p, amp, era, clus


def test_the_era_blocked_slope_is_in_device_units_per_mA_not_log_units():
    p, a, era, cl = _linear_fixture(slope_per_mA=-20.0)
    r = LR.assess_response(p, a, era=era, cluster=cl, mode_requires="suppression")
    assert r.responds is True
    # A slope of -20 device units per mA. On log power the same data give about -0.11 per mA,
    # so this bound separates the two beyond any doubt.
    assert -26.0 < r.slope_per_mA < -14.0, r.slope_per_mA
    assert r.slope_p < 0.05
    assert r.slope_ci[0] < r.slope_per_mA < r.slope_ci[1]
    assert "device units per mA" in r.describe()


def test_the_result_carries_no_log_field_at_all():
    p, a, era, cl = _linear_fixture()
    r = LR.assess_response(p, a, era=era, cluster=cl)
    for name in ("slope_log_per_mA", "separation_d_on_log"):
        assert not hasattr(r, name), name
    assert "logarithm" not in r.describe()


def test_the_readiness_source_takes_no_logarithm_of_power():
    src = inspect.getsource(LR)
    for token in ("np.log(", "np.log10(", "np.log1p(", "math.log("):
        assert token not in src, token


def test_the_serialised_band_row_and_the_one_band_rule_read_the_device_unit_slope():
    p, a, era, cl = _linear_fixture(slope_per_mA=-20.0)
    r = LR.assess_response(p, a, era=era, cluster=cl)
    row = SG.verdict_row(24.5, r)
    assert "slope_per_mA" in row and row["slope_per_mA"] == pytest.approx(r.slope_per_mA)
    assert "slope_log_per_mA" not in row and "separation_d_on_log" not in row
    assert LE.band_era_negative_significant(r) is True
    rising, *_ = _linear_fixture(slope_per_mA=+20.0)
    r2 = LR.assess_response(rising, a, era=era, cluster=cl)
    assert LE.band_era_negative_significant(r2) is False
