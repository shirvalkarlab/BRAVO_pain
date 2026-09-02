"""Tests for the LFP-responds-to-stimulation gate (manual p. 35 requirement)."""
import numpy as np
import pytest

from StimOptimizer.routines import lfp_response as LR


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
    base = np.log(100.0)
    sign = -1.0 if suppression else +1.0
    logp = base + sign * effect * (amp - 1.5) / 2.0 + rng.normal(0, noise, amp.size)
    if era_collinear:
        era = np.repeat(np.arange(n_eras), int(np.ceil(amp.size / n_eras)))[:amp.size]
    else:
        era = np.tile(np.arange(n_eras), int(np.ceil(amp.size / n_eras)))[:amp.size]
    clus = np.arange(amp.size) // 4
    return np.exp(logp), amp, era, clus


def test_device_band_power_is_a_sum_of_squares_over_the_band():
    """Not a mean, not a log. The device thresholds this quantity."""
    freqs = np.array([8.0, 10.0, 12.0, 14.0, 30.0])
    mag = np.array([[1.0, 2.0, 3.0, 4.0, 99.0]])
    # band 10-14 Hz selects bins at 10, 12, 14 -> 4 + 9 + 16 = 29
    got = LR.device_band_power(mag, freqs, center_hz=12.0, band_width_hz=4.0)
    assert got.shape == (1,) and got[0] == pytest.approx(29.0)


def test_band_power_refuses_a_band_with_no_bins_and_bad_shapes():
    freqs = np.array([8.0, 10.0, 12.0])
    with pytest.raises(ValueError, match="no frequency bins"):
        LR.device_band_power(np.ones((2, 3)), freqs, center_hz=60.0, band_width_hz=2.0)
    with pytest.raises(ValueError, match="must be 2-D"):
        LR.device_band_power(np.ones(3), freqs, center_hz=10.0, band_width_hz=4.0)
    with pytest.raises(ValueError, match="freqs has"):
        LR.device_band_power(np.ones((2, 5)), freqs, center_hz=10.0, band_width_hz=4.0)


def test_a_suppressing_band_passes_for_a_suppression_mode():
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    r = LR.assess_response(p, a, era=era, cluster=cl, mode_requires="suppression")
    assert r.responds is True and r.direction_ok is True
    assert r.power_high < r.power_low
    assert r.captures_inverted is False
    assert r.slope_log_per_mA < 0 and r.slope_p < 0.05
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
    p = np.exp(np.log(100.0) - 0.3 * a + rng.normal(0, 0.1, a.size))
    r = LR.assess_response(p, a)
    assert r.responds is None and "rows" in r.reason


def test_derived_threshold_uses_the_device_formula_on_the_captures():
    p, a, era, cl = _synth(suppression=True, effect=1.0)
    r = LR.assess_response(p, a, era=era, cluster=cl)
    assert r.derived_threshold == pytest.approx(0.75 * (r.power_high - r.power_low) + r.power_low)


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
    assert np.isfinite(r.slope_unadjusted) and np.isfinite(r.slope_log_per_mA)


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
    """THE PATHOLOGY THIS RECORD ACTUALLY HAS. Amplitude rose over time, so if eras are nested
    within amplitude rather than crossed with it, blocking on era removes the contrast under test.
    Discovered by accident when a fixture generated eras sequentially: the same data that gives
    p<0.001 crossed gives a null result nested. The capture contrast still stands, because it does
    not condition on era — which is exactly why the verdict does not rest on the slope alone.
    """
    crossed = LR.assess_response(*_synth(n_per=200, effect=1.0)[:2],
                                 era=_synth(n_per=200, effect=1.0)[2],
                                 cluster=_synth(n_per=200, effect=1.0)[3])
    p, a, era, cl = _synth(n_per=200, effect=1.0, era_collinear=True)
    nested = LR.assess_response(p, a, era=era, cluster=cl)

    assert crossed.slope_p < 0.01, "crossed fixture must be estimable, else this tests nothing"
    assert nested.slope_p > crossed.slope_p, (crossed.slope_p, nested.slope_p)
    # The capture contrast is unaffected: it compares the two arms directly.
    assert nested.direction_ok is True and nested.separation_d > LR.MIN_CAPTURE_SEPARATION_D
    assert nested.responds is True
