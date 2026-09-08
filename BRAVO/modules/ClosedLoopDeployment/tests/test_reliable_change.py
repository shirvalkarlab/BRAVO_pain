"""The individual reliable-change threshold: RCS08's own same-condition rating variance, pooled
across epochs of unchanged stimulation settings, reported alongside the Farrar population MCID.
"""
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import reliable_change as RC


def _epochs(rows):
    """rows: list of (nrs_mean, nrs_sd, nrs_n) tuples, one per epoch."""
    return pd.DataFrame([{"epoch": i, "nrs": m, "nrs_sd": sd, "nrs_n": n}
                         for i, (m, sd, n) in enumerate(rows)])


def test_pooled_sd_is_the_classic_within_groups_estimator():
    # Two epochs, equal size, so the pooled SD is a simple average of the two variances' sqrt.
    epochs = _epochs([(5.0, 1.0, 5), (5.0, 2.0, 5)])
    out = RC.pooled_same_condition_sd(epochs, "nrs", min_total_df=1)
    expected = np.sqrt((4 * 1.0 ** 2 + 4 * 2.0 ** 2) / 8.0)
    assert out["pooled_sd"] == pytest.approx(expected)
    assert out["df"] == 8
    assert out["n_epochs"] == 2
    assert out["reason"] is None


def test_pooled_sd_weights_larger_epochs_more():
    # A big, low-variance epoch should pull the pooled estimate down more than a small, high-
    # variance one -- confirms weighting is by degrees of freedom, not a plain average of SDs.
    epochs = _epochs([(5.0, 0.5, 20), (5.0, 3.0, 3)])
    out = RC.pooled_same_condition_sd(epochs, "nrs", min_total_df=1)
    plain_average = (0.5 + 3.0) / 2.0
    assert out["pooled_sd"] < plain_average


def test_epochs_below_the_per_epoch_floor_are_excluded():
    epochs = _epochs([(5.0, 1.0, 1), (5.0, 1.0, 1)])  # n=1: no within-epoch spread possible
    out = RC.pooled_same_condition_sd(epochs, "nrs", min_total_df=1)
    assert np.isnan(out["pooled_sd"])
    assert "at least" in out["reason"]


def test_too_little_pooled_history_is_not_assessed():
    epochs = _epochs([(5.0, 1.0, 2)])  # df = 1, below the default floor of 5
    out = RC.pooled_same_condition_sd(epochs, "nrs")
    assert np.isnan(out["pooled_sd"])
    assert out["df"] == 1
    assert "pooled degrees of freedom" in out["reason"]


def test_empty_or_missing_epochs_is_not_assessed():
    assert np.isnan(RC.pooled_same_condition_sd(None, "nrs")["pooled_sd"])
    assert np.isnan(RC.pooled_same_condition_sd(pd.DataFrame(), "nrs")["pooled_sd"])
    no_item = pd.DataFrame([{"epoch": 0}])
    out = RC.pooled_same_condition_sd(no_item, "nrs")
    assert np.isnan(out["pooled_sd"])
    assert "no" in out["reason"] and "nrs" in out["reason"]


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
