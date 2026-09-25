"""Does regression to the mean explain decision 253's block-to-block swing? On constructed records
whose answer is known (2026-09-25). Written before the runner, watched RED first.
`artifacts/research_2026-09-25_options/01_regression_to_the_mean.md` is the specification."""
import math

import numpy as np
import pandas as pd

try:
    from modules.ControlAnalyses import regression_to_mean as RM
except ImportError:                                            # host spelling
    from ControlAnalyses import regression_to_mean as RM

DAY = 86400.0


def test_time_blocks_are_contiguous_in_time_order_and_roughly_equal():
    t0 = np.array([5.0, 1.0, 4.0, 2.0, 3.0, 0.0, 6.0])            # 7 rows, out of order
    b = RM.time_blocks(t0, n_blocks=3)
    order = np.argsort(t0)
    sorted_blocks = b[order]
    assert list(sorted_blocks) == [0, 0, 0, 1, 1, 2, 2]           # 7 -> 3,2,2 by array_split


def test_target_mask_picks_the_most_delivered_current_pair():
    aL = [1.6, 1.6, 1.6, 0.5, 0.5, 2.0]
    aR = [1.2, 1.2, 1.2, 0.5, 0.5, 2.0]
    mask, setting = RM.target_mask(aL, aR)
    assert list(mask) == [True, True, True, False, False, False]
    assert setting == (1.6, 1.2)


def test_target_mask_rounds_like_the_reference_setting():
    aL = [1.60001, 1.59999, 1.6, 0.5]
    aR = [1.2, 1.2, 1.2, 0.5]
    mask, setting = RM.target_mask(aL, aR)
    assert list(mask) == [True, True, True, False]


def test_heterogeneity_and_trend_refuse_with_fewer_than_two_blocks():
    rows = RM.block_series(J=[1.0, 1.2], obs_var=[0.1, 0.1], blocks=[0, 0], mask=[True, True])
    assert len(rows) == 1
    h = RM.heterogeneity(rows)
    t = RM.trend(rows)
    assert h["q"] is None and "fewer than two" in h["reason"]
    assert t["slope"] is None and "fewer than two" in t["reason"]


def test_heterogeneity_matches_a_hand_computed_chi_square():
    # two blocks, equal weights (obs_var = 1 everywhere): grand mean is the plain average
    rows = RM.block_series(J=[1.0, 1.0, -1.0, -1.0], obs_var=[1.0] * 4, blocks=[0, 0, 1, 1],
                            mask=[True] * 4)
    h = RM.heterogeneity(rows)
    # weights are 2 per block, means are +1 and -1, grand mean 0 -> Q = 2*1 + 2*1 = 4, df 1
    assert abs(h["q"] - 4.0) < 1e-9
    assert h["df"] == 1
    from scipy import stats as st
    assert abs(h["p"] - float(st.chi2.sf(4.0, 1))) < 1e-12


def test_trend_is_the_two_point_slope_when_only_two_blocks_are_present():
    rows = RM.block_series(J=[2.0, 0.0], obs_var=[1.0, 1.0], blocks=[0, 2], mask=[True, True])
    t = RM.trend(rows)
    # block indices are 0 and 2 (not renumbered), so slope = (0 - 2) / (2 - 0) = -1
    assert abs(t["slope"] - (-1.0)) < 1e-9


def _block_of(n_blocks, counts):
    """`counts` setting-periods per block, in block order (e.g. [3, 3, 2] -> 8 rows)."""
    return np.concatenate([[b] * c for b, c in enumerate(counts)])


def test_internal_split_test_counts_every_split_exactly():
    n, k = 10, 4
    rng = np.random.default_rng(0)
    blocks = _block_of(3, [4, 3, 3])
    J = rng.normal(0, 1, n)
    v = np.full(n, 1.0)
    mask = np.zeros(n, dtype=bool)
    mask[[0, 1, 4, 7]] = True                     # spans all three blocks (0-3, 4-6, 7-9)
    out = RM.internal_split_test(J, v, blocks, mask)
    assert out["n_total"] == math.comb(n, k) == 210
    assert out["n_valid"] <= out["n_total"]
    assert 0.0 <= out["p_two_sided"] <= 1.0
    assert 0.0 <= out["p_same_direction"] <= 1.0


def test_internal_split_test_raises_rather_than_sampling_when_too_many_splits():
    n, k = 40, 20
    blocks = _block_of(3, [14, 13, 13])
    J = np.zeros(n)
    v = np.ones(n)
    mask = np.zeros(n, dtype=bool)
    mask[:k] = True
    import pytest
    with pytest.raises(ValueError):
        RM.internal_split_test(J, v, blocks, mask, max_splits=1000)


def test_internal_split_test_does_not_flag_a_shared_background_pattern_as_setting_specific():
    """Every setting-period in the group carries the SAME block-to-block trend (a shared calendar
    effect, or plain regression to the mean acting on the whole group): whichever 8 of 19 are
    called "target," the block averages -- and so Q and the trend -- come out identical, so a
    random split matches the real one (almost) every time. This is the case the check should read
    as "looks like the whole group's own background pattern," i.e. a LARGE p_two_sided."""
    n = 19
    blocks = _block_of(3, [7, 6, 6])
    block_effect = np.array([1.5, 0.5, -0.5])
    J = block_effect[blocks]                                      # deterministic, no noise at all
    v = np.full(n, 1.0)
    mask = np.zeros(n, dtype=bool)
    mask[:8] = True                                                # "the setting delivered most"
    out = RM.internal_split_test(J, v, blocks, mask)
    assert out["n_total"] == 75582
    assert out["p_two_sided"] > 0.9, (
        f"a swing shared by the whole group should not look specific to one split: {out}")


def test_internal_split_test_flags_a_real_setting_specific_swing():
    """Only 8 SPECIFIC rows, spread across all three blocks the way decision 253's own 8-epoch
    target group is (3 in block 0, 3 in block 1, 2 in block 2), carry an extra, large swing on top
    of the shared background trend every setting-period has; the other rows of the SAME blocks
    carry no such swing, so a random 8-of-19 split only rarely reproduces it. The check should read
    this as unusual: a SMALL p_two_sided."""
    n = 19
    blocks = _block_of(3, [7, 6, 6])
    rng = np.random.default_rng(1)
    background = np.array([0.2, 0.1, 0.0])[blocks]
    mask = np.zeros(n, dtype=bool)
    mask[[0, 1, 2, 7, 8, 9, 13, 14]] = True        # 3 of block 0, 3 of block 1, 2 of block 2
    extra = np.where(mask & (blocks == 0), 8.0, np.where(mask & (blocks == 2), -8.0, 0.0))
    J = background + extra + rng.normal(0, 0.05, n)
    v = np.full(n, 1.0)
    out = RM.internal_split_test(J, v, blocks, mask)
    assert out["p_two_sided"] < 0.01, f"a swing specific to the target group should stand out: {out}"


def test_outside_window_test_reads_a_planted_swing_back_out():
    rng = np.random.default_rng(2)
    n = 40
    t0 = np.arange(n, dtype=float) * DAY
    J = rng.normal(0, 0.2, n)
    v = np.full(n, 1.0)
    # a big, obvious swing sits in one 8-period window (indices 20-27)
    J[20:24] += 5.0
    J[24:28] -= 5.0
    out = RM.outside_window_test(J, v, t0, window_size=8, q_real=1e9)
    assert out["n_windows"] == n - 8 + 1
    assert out["fraction_ge"] == 0.0                                # nothing beats an impossible q_real
    out2 = RM.outside_window_test(J, v, t0, window_size=8, q_real=0.0)
    assert out2["fraction_ge"] == 1.0                                # every window beats q_real=0


def test_outside_window_test_is_not_computable_with_too_few_rows_or_no_q():
    out = RM.outside_window_test([1.0, 2.0], [1.0, 1.0], [0.0, 1.0], window_size=8, q_real=1.0)
    assert out["n_windows"] == 0 and out["fraction_ge"] is None
    out2 = RM.outside_window_test([1.0] * 20, [1.0] * 20, np.arange(20.0), window_size=8, q_real=None)
    assert out2["fraction_ge"] is None


def test_extremity_is_large_when_block_one_is_far_from_the_record_average():
    target_rows = [dict(block=0, n=3, mean=1.51, se=0.12), dict(block=1, n=3, mean=0.53, se=0.24)]
    full_J = np.array([1.51] * 3 + [0.53] * 3 + [0.6] * 13)
    full_v = np.ones(19)
    e = RM.extremity(target_rows, full_J, full_v)
    assert e["value"] is not None and e["value"] > 3.0


def test_extremity_is_small_when_block_one_matches_the_record_average():
    target_rows = [dict(block=0, n=3, mean=0.6, se=0.5), dict(block=1, n=3, mean=0.53, se=0.24)]
    full_J = np.array([0.6] * 19)
    full_v = np.ones(19)
    e = RM.extremity(target_rows, full_J, full_v)
    assert abs(e["value"]) < 0.5


def _stratum_frame(n_blocks_counts, target_extra_block0=0.0, target_extra_block2=0.0, seed=3):
    """A constructed `sub` table shaped like `_fit_rate_stratum`'s own frame: `t0`, two currents,
    `J`, `obs_var`, with a target setting (1.6/1.2 mA, spread 3/3/2 across the three blocks, the
    way decision 253's own 8-epoch group is) and an "other" group filling the rest."""
    rng = np.random.default_rng(seed)
    counts = n_blocks_counts
    n = sum(counts)
    blocks = _block_of(3, counts)
    t0 = np.arange(n, dtype=float) * DAY
    b0 = np.flatnonzero(blocks == 0)[:3]
    b1 = np.flatnonzero(blocks == 1)[:3]
    b2 = np.flatnonzero(blocks == 2)[:2]
    is_target = np.zeros(n, dtype=bool)
    is_target[np.concatenate([b0, b1, b2])] = True
    aL = np.where(is_target, 1.6, rng.choice([0.5, 1.0, 2.0, 3.0], n))
    aR = np.where(is_target, 1.2, rng.choice([0.5, 1.0, 2.0, 3.0], n))
    background = np.array([0.2, 0.1, 0.0])[blocks]
    extra = np.where(is_target & (blocks == 0), target_extra_block0,
                     np.where(is_target & (blocks == 2), target_extra_block2, 0.0))
    J = background + extra + rng.normal(0, 0.05, n)
    obs_var = np.full(n, 0.05)
    return pd.DataFrame(dict(t0=t0, amp_mA_Left=aL, amp_mA_Right=aR, J=J, obs_var=obs_var))


def test_diagnosis_detects_regression_to_the_mean_when_the_swing_is_the_whole_groups_background():
    sub = _stratum_frame([7, 6, 6], target_extra_block0=0.0, target_extra_block2=0.0)
    out = RM.diagnosis(sub, sub)
    assert out["setting"] == dict(amp_mA_Left=1.6, amp_mA_Right=1.2)
    assert out["n_target"] == 8 and out["n_other"] == 11
    assert out["internal_comparison"]["p_two_sided"] > 0.5, (
        "no setting-specific swing was planted; this should read as the group's own background pattern")


def test_diagnosis_does_not_call_a_real_setting_specific_swing_regression_to_the_mean():
    sub = _stratum_frame([7, 6, 6], target_extra_block0=8.0, target_extra_block2=-8.0)
    out = RM.diagnosis(sub, sub)
    assert out["internal_comparison"]["p_two_sided"] < 0.01, (
        "a real, setting-specific swing was planted; it must not be waved away as background")
    assert out["target"]["trend"]["slope"] < 0            # pain improving block to block at target


def test_diagnosis_refuses_cleanly_with_no_rows():
    out = RM.diagnosis(pd.DataFrame(), pd.DataFrame())
    assert out["setting"] is None and "reason" in out


def test_diagnosis_uses_the_stratum_itself_when_no_full_record_is_given():
    sub = _stratum_frame([7, 6, 6])
    out = RM.diagnosis(sub, None)
    assert out["full_record_is_the_stratum_itself"] is True
    assert out["outside_comparison"]["n_windows"] == len(sub) - out["n_target"] + 1
