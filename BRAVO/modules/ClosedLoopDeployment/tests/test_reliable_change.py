"""The individual reliable-change threshold: RCS08's own SHORT-GAP rating noise, from consecutive
ratings filed within one hour of each other under unchanged stimulation settings (decision 111),
reported alongside the Farrar population MCID.

The estimator's tests are built so each rule is exercised on the VALUE it produces, not on the
shape of the result: a pair outside the gap changes nothing, a same-minute entry changes nothing,
a rating in the wash-in changes nothing, and a pair straddling a settings change is never formed.
"""
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import reliable_change as RC

H = 3600.0
T0 = 1_700_000_000.0


def _sd(times_s, values, epochs=((T0 - H, T0 + 100 * H),), **kw):
    starts = [e[0] for e in epochs]
    ends = [e[1] for e in epochs]
    return RC.short_gap_pairwise_sd(times_s, values, starts, ends, **kw)


def test_the_estimate_is_root_mean_square_difference_over_root_two():
    # Five consecutive ratings each 30 min apart: differences +1, -1, +1, -1 -> mean d^2 = 1.
    times = [T0 + k * 0.5 * H for k in range(5)]
    out = _sd(times, [5, 6, 5, 6, 5], min_pairs=1)
    assert out["pooled_sd"] == pytest.approx(np.sqrt(1.0 / 2.0))
    assert out["n_pairs"] == 4 and out["df"] == 4 and out["n_epochs"] == 1
    assert out["reason"] is None


def test_a_pair_further_apart_than_the_gap_contributes_nothing():
    # Same five ratings, but the middle gap is stretched to two hours: the +1/-1 straddling it
    # drop out, leaving two pairs, both |d| = 1.
    times = [T0, T0 + 0.5 * H, T0 + 2.5 * H, T0 + 3.0 * H, T0 + 3.5 * H]
    out = _sd(times, [5, 6, 5, 6, 5], min_pairs=1)
    assert out["n_pairs"] == 3           # (0,1), (2,3), (3,4); the 0.5h->2.5h gap is 2 h
    assert out["pooled_sd"] == pytest.approx(np.sqrt(1.0 / 2.0))
    # And with the gap widened to cover it, the pair comes back.
    wide = _sd(times, [5, 6, 5, 6, 5], min_pairs=1, max_gap_hours=3.0)
    assert wide["n_pairs"] == 4


def test_a_second_entry_within_the_same_minute_is_dropped_and_counted():
    # Two entries 20 s apart with the same value would be a free zero difference. They are one
    # reading, so the second is dropped; the estimate must equal the one without it.
    clean_t = [T0, T0 + 0.5 * H, T0 + 1.0 * H]
    clean = _sd(clean_t, [5, 6, 5], min_pairs=1)
    dup_t = [T0, T0 + 20.0, T0 + 0.5 * H, T0 + 1.0 * H]
    dup = _sd(dup_t, [5, 5, 6, 5], min_pairs=1)
    assert dup["n_dropped_same_minute"] == 1
    assert dup["n_pairs"] == clean["n_pairs"] == 2
    assert dup["pooled_sd"] == pytest.approx(clean["pooled_sd"])
    # A differing value within the same minute is still one reading (the later one is dropped).
    dup2 = _sd([T0, T0 + 20.0, T0 + 0.5 * H], [5, 9, 5], min_pairs=1)
    assert dup2["n_dropped_same_minute"] == 1 and dup2["n_pairs"] == 1
    assert dup2["pooled_sd"] == pytest.approx(0.0)


def test_a_rating_inside_the_washin_is_left_out():
    # The first rating sits 30 s after the settings changed; the patient may still be feeling it.
    times = [T0 + 30.0, T0 + 0.5 * H, T0 + 1.0 * H]
    out = _sd(times, [9, 5, 5], epochs=((T0, T0 + 10 * H),), min_pairs=1)
    assert out["n_pairs"] == 1           # only (5, 5); the 9 never entered
    assert out["pooled_sd"] == pytest.approx(0.0)


def test_a_pair_never_straddles_a_settings_change():
    # Two ratings 10 minutes apart, but the settings changed between them: different epochs, no pair.
    times = [T0 + 5 * 60.0, T0 + 15 * 60.0]
    out = _sd(times, [5, 9], epochs=((T0 - H, T0 + 10 * 60.0), (T0 + 10 * 60.0, T0 + H)),
              min_pairs=1)
    assert out["n_pairs"] == 0
    assert np.isnan(out["pooled_sd"])
    assert "pair" in out["reason"]


def test_too_few_pairs_is_not_assessed_and_says_how_many():
    times = [T0, T0 + 0.5 * H, T0 + 1.0 * H]   # two pairs, below the default floor of five
    out = _sd(times, [5, 6, 5])
    assert np.isnan(out["pooled_sd"])
    assert out["n_pairs"] == 2 and out["df"] == 2
    assert "2 pair" in out["reason"] and str(RC.MIN_PAIRS) in out["reason"]


def test_empty_or_mismatched_inputs_are_not_assessed():
    assert np.isnan(_sd([], [])["pooled_sd"])
    assert np.isnan(_sd([T0], [5])["pooled_sd"])
    assert np.isnan(_sd([T0, T0 + 1], [5])["pooled_sd"])           # lengths differ
    assert np.isnan(RC.short_gap_pairwise_sd([T0, T0 + 1], [5, 6], [], [])["pooled_sd"])
    nan_in = _sd([T0, T0 + 0.5 * H, T0 + 1.0 * H], [5, np.nan, 5], min_pairs=1)
    assert nan_in["n_pairs"] == 1        # the NaN rating is simply not there


def test_the_verdict_composes_with_the_new_estimator():
    times = [T0 + k * 0.5 * H for k in range(8)]
    sd = _sd(times, [5, 6, 5, 6, 5, 6, 5, 6])
    v = RC.reliable_change_verdict(6.0, 2.0, sd)
    assert v["individual_reliable_change_threshold"] == pytest.approx(
        RC.RELIABLE_CHANGE_Z * sd["pooled_sd"] * np.sqrt(2))
    assert v["pooled_same_condition_df"] == sd["n_pairs"]


def test_reliable_change_verdict_flags_a_large_change_as_reliable():
    pooled = dict(pooled_sd=0.5, df=20, n_epochs=4, reason=None)
    out = RC.reliable_change_verdict(pre_mean=7.0, post_mean=3.0, pooled_sd_result=pooled)
    assert out["change"] == pytest.approx(-4.0)
    assert abs(out["individual_rci"]) >= RC.RELIABLE_CHANGE_Z
    assert "reliably outside" in out["individual_verdict"]
    assert out["individual_reliable_change_threshold"] == pytest.approx(
        RC.RELIABLE_CHANGE_Z * 0.5 * np.sqrt(2))
    assert "meets the Farrar" in out["population_verdict"]


def test_reliable_change_verdict_flags_a_small_change_as_within_noise():
    pooled = dict(pooled_sd=2.0, df=20, n_epochs=4, reason=None)
    out = RC.reliable_change_verdict(pre_mean=6.0, post_mean=5.5, pooled_sd_result=pooled)
    assert abs(out["individual_rci"]) < RC.RELIABLE_CHANGE_Z
    assert "cannot be distinguished" in out["individual_verdict"]
    # a change this small also fails the population benchmark, but the two are reported
    # independently -- confirms neither is derived from the other
    assert "does not meet the Farrar" in out["population_verdict"]


def test_more_ratings_per_side_shrinks_the_threshold():
    pooled = dict(pooled_sd=1.0, df=20, n_epochs=4, reason=None)
    one_each = RC.reliable_change_verdict(7.0, 5.0, pooled, n_pre=1, n_post=1)
    many_each = RC.reliable_change_verdict(7.0, 5.0, pooled, n_pre=10, n_post=10)
    assert many_each["individual_reliable_change_threshold"] < one_each[
        "individual_reliable_change_threshold"]


def test_reliable_change_verdict_is_not_assessed_when_the_pooled_sd_is_not_assessed():
    pooled = dict(pooled_sd=np.nan, df=1, n_epochs=1,
                  reason="only 1 pooled degrees of freedom of same-condition 'nrs' history")
    out = RC.reliable_change_verdict(7.0, 5.0, pooled)
    assert out["individual_verdict"] == "not assessed"
    assert out["reason"] == pooled["reason"]
    # the population cross-check still runs -- it only needs the two means
    assert out["population_verdict"] != "not assessed"


def test_reliable_change_verdict_handles_missing_means():
    out = RC.reliable_change_verdict(None, 5.0, dict(pooled_sd=1.0, df=20))
    assert out["individual_verdict"] == "not assessed"
    assert out["population_verdict"] == "not assessed"
    assert "not both available" in out["reason"]


def test_reliable_change_verdict_handles_zero_pooled_sd():
    pooled = dict(pooled_sd=0.0, df=20, n_epochs=4)
    out = RC.reliable_change_verdict(7.0, 5.0, pooled)
    assert out["individual_verdict"] == "not assessed"
    assert "no variation" in out["reason"]


def test_farrar_fraction_check_applies_when_points_check_would_not():
    # A 1.5-point drop from a baseline of 4.0 is 37.5%, clearing the 30% fraction bar even though
    # it misses the flat 2.0-point bar -- confirms the two Farrar criteria are combined with OR.
    pooled = dict(pooled_sd=5.0, df=20, n_epochs=4)  # deliberately large, so the individual check fails
    out = RC.reliable_change_verdict(pre_mean=4.0, post_mean=2.5, pooled_sd_result=pooled)
    assert out["change"] == pytest.approx(-1.5)
    assert "meets the Farrar" in out["population_verdict"]
    assert "cannot be distinguished" in out["individual_verdict"]
