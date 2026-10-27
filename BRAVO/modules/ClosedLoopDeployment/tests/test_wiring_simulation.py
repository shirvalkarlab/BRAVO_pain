"""The three sense-to-control wirings compared by simulation (decision 472).

The first test is the equality proof: with one band read, no effect across sides and the other
stimulator idle, the two-controller loop must give the SAME current, sample by sample, as the
existing simulation (`simulation.simulate_series`) with the same straight-line response.
"""
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import simulation as SIM
from ClosedLoopDeployment import wiring_simulation as W
from ClosedLoopDeployment.types import ThresholdPlan
from StimOptimizer.routines.amplitude_response import ResponseCurve

DT = 3.0
TIMING = {"averaging_ms": 3000, "onset_ms": 6000, "detection_blanking_ms": 3000,
          "transition_up_ms": 30000, "transition_down_ms": 30000}


def _power(n=400, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n) * DT
    return t, 100 + 40 * np.sin(t / 90.0) + rng.normal(0, 8, n)


def test_one_controller_equals_the_existing_simulation_bit_for_bit():
    t, p = _power()
    a_obs = np.full(t.size, 2.0)
    slope = -6.0
    plan = ThresholdPlan(upper=115.0, lower=90.0, capture_amp_low=1.0, capture_amp_high=4.0)
    ref = SIM.simulate_series(t, p, a_obs, plan, [ResponseCurve.linear(slope)], tau_s=30.0, params=TIMING)
    g = {"t": t, "dt": DT, "p": {"Left": p, "Right": np.full(t.size, np.nan)},
         "a": {"Left": a_obs, "Right": np.zeros(t.size)}}
    ctrl = W.controller_params({"upper": 115.0, "lower": 90.0, "amp_low_mA": 1.0, "amp_high_mA": 4.0}, TIMING)
    idle = dict(ctrl)
    k = {"Left": {"Left": slope, "Right": 0.0}, "Right": {"Left": 0.0, "Right": 0.0}}
    out = W.run_stretch(g, {"Left": "Left", "Right": "Right"}, {"Left": ctrl, "Right": idle}, k, tau_s=30.0)
    assert out["Left"]["amp"].size == ref["amp"].shape[1]
    diff = np.flatnonzero(out["Left"]["amp"] != ref["amp"][0])
    assert diff.size == 0, f"{diff.size} of {ref['amp'].shape[1]} samples differ"
    assert out["Left"]["n_trans"] == int(ref["n_transitions"][0])


def test_the_other_stimulators_current_moves_the_band_it_does_not_drive():
    """Left drives both: the right stimulator's current shifts the left band by k[Left][Right],
    so the left controller's run differs from a run with no cross-side effect."""
    t, p = _power()
    g = {"t": t, "dt": DT, "p": {"Left": p, "Right": p.copy()},
         "a": {"Left": np.full(t.size, 2.0), "Right": np.full(t.size, 1.0)}}
    ctrl = W.controller_params({"upper": 115.0, "lower": 90.0, "amp_low_mA": 1.0, "amp_high_mA": 4.0}, TIMING)
    drives = W.WIRINGS["left_both"]
    k0 = {"Left": {"Left": -6.0, "Right": 0.0}, "Right": {"Left": 0.0, "Right": -6.0}}
    k1 = {"Left": {"Left": -6.0, "Right": 15.0}, "Right": {"Left": 0.0, "Right": -6.0}}
    a = W.run_stretch(g, drives, {"Left": ctrl, "Right": ctrl}, k0)
    b = W.run_stretch(g, drives, {"Left": ctrl, "Right": ctrl}, k1)
    assert not np.array_equal(a["Left"]["amp"], b["Left"]["amp"])
    # the band the wiring does not read changes nothing
    k2 = {"Left": {"Left": -6.0, "Right": 0.0}, "Right": {"Left": 50.0, "Right": 50.0}}
    c = W.run_stretch(g, drives, {"Left": ctrl, "Right": ctrl}, k2)
    assert np.array_equal(a["Left"]["amp"], c["Left"]["amp"])


def test_auc_is_the_share_of_high_low_pairs_ordered_and_needs_enough_ratings():
    assert W.auc([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], [1] * 5 + [0] * 5) == 1.0
    assert W.auc([0.5] * 10, [1] * 5 + [0] * 5) == 0.5
    assert W.auc([1, 0, 1], [1, 0, 1]) is None


def test_joint_stretches_keep_only_time_both_sides_were_recorded():
    tl = np.arange(0, 300, 3.0)
    tr = np.arange(150, 600, 3.0)
    mk = lambda t, v: {"t": t, "power": np.full(t.size, v), "amp_Left": np.full(t.size, 2.0),  # noqa: E731
                       "amp_Right": np.full(t.size, 1.0)}
    st, med = W.joint_stretches(mk(tl, 10.0), mk(tr, 20.0))
    assert med == 3.0 and len(st) == 1
    assert st[0]["t"][0] == 150.0 and st[0]["t"][-1] == 297.0
    assert np.all(st[0]["p"]["Left"] == 10.0) and np.all(st[0]["p"]["Right"] == 20.0)


def test_cross_slope_is_zero_and_says_so_with_too_few_runs():
    xs, ys, lab = np.array([1, 2, 3.0]), np.array([5, 4, 3.0]), np.array(["r1"] * 3)
    out = W.cross_slope(xs, ys, lab)
    assert out["slope_per_mA"] == 0.0 and out["measured"] is False and "taken as zero" in out["source"]


def test_settled_points_take_the_last_30_s_of_each_setting_of_the_stepped_side_only():
    steps = pd.DataFrame({"t0": [0.0, 100.0], "t_end": [100.0, 200.0], "current_mA": [1.0, 2.0],
                          "block": ["Right run 1"] * 2})
    runs = [{"side": "Right", "steps": steps}, {"side": "Left", "steps": steps}]
    t = np.arange(0, 200, 3.0)
    p = np.where(t < 100, 10.0, 20.0)
    p[(t >= 60) & (t < 70)] = 999.0          # before the settled window: ignored
    x, y, lab = W.settled_points(runs, "Right", t, p)
    assert x.tolist() == [1.0, 2.0] and y.tolist() == [10.0, 20.0] and set(lab) == {"Right run 1"}


def _draws(mean, n=200, sd=0.01, seed=0):
    return np.random.default_rng(seed).normal(mean, sd, n)


def test_recommend_the_clear_winner():
    sc = {"independent": 0.55, "left_both": 0.70, "right_both": 0.52}
    dr = {w: _draws(v, seed=i) for i, (w, v) in enumerate(sc.items())}
    r = W.recommend(sc, dr, {w: True for w in sc})
    assert r["wiring"] == "left_both" and r["basis"] == "clearly_best"


def test_recommend_independent_on_a_tie():
    sc = {"independent": 0.70, "left_both": 0.71, "right_both": 0.40}
    dr = {"independent": _draws(0.70, sd=0.05, seed=1), "left_both": _draws(0.71, sd=0.05, seed=2),
          "right_both": _draws(0.40, seed=3)}
    r = W.recommend(sc, dr, {w: True for w in sc})
    assert r["wiring"] == "independent" and r["basis"] == "tie_default"


def test_recommend_among_allowed_and_say_when_none_is():
    sc = {"independent": 0.55, "left_both": 0.70, "right_both": 0.52}
    dr = {w: _draws(v, seed=i) for i, (w, v) in enumerate(sc.items())}
    r = W.recommend(sc, dr, {"independent": True, "left_both": False, "right_both": True})
    assert r["wiring"] == "independent"
    r = W.recommend(sc, dr, {w: False for w in sc})
    assert r["wiring"] == "left_both" and r["none_allowed"] is True
    assert "refuses every wiring" in r["reason"]


def test_compare_scores_all_three_on_the_same_ratings():
    rng = np.random.default_rng(4)
    n = 2000
    t = np.arange(n) * DT
    pain = np.clip(5 + 3 * np.sin(t / 600.0) + rng.normal(0, 0.5, n), 0, 10)
    pl = 100 + 12 * (pain - 5) + rng.normal(0, 5, n)          # left band tracks pain
    pr = 100 + rng.normal(0, 12, n)                            # right band does not
    left = {"t": t, "power": pl, "amp_Left": np.full(n, 2.0), "amp_Right": np.full(n, 2.0)}
    right = {"t": t, "power": pr, "amp_Left": np.full(n, 2.0), "amp_Right": np.full(n, 2.0)}
    st, med = W.joint_stretches(left, right)
    c = {"upper": 110.0, "lower": 90.0, "amp_low_mA": 1.0, "amp_high_mA": 4.0}
    ctrls = {(s, x): c for s in W.SIDES for x in W.SIDES}
    k = {"Left": {"Left": 0.0, "Right": 0.0}, "Right": {"Left": 0.0, "Right": 0.0}}
    rt = t[::20] + 1.0
    ry = pain[::20]
    day = (rt // 600).astype(int)
    out = W.compare(st, med, ctrls, k, rt, ry, day, timing=TIMING, allowed={}, n_boot=200)
    ws = out["wirings"]
    assert out["record"]["n_ratings_high"] >= 5 and out["record"]["n_ratings_low"] >= 5
    assert ws["left_both"]["score"] > ws["right_both"]["score"]
    assert ws["left_both"]["auc"]["Left"] == ws["left_both"]["auc"]["Right"]
    assert out["recommendation"]["wiring"] == "left_both"


def test_the_thirds_are_cut_on_the_ratings_inside_the_record():
    """Ratings outside the record must not move the cut: here they are all 0, which cut on every
    rating would put every in-record rating in the high third."""
    rng = np.random.default_rng(5)
    n = 2000
    t = np.arange(n) * DT
    pain = np.clip(5 + 3 * np.sin(t / 600.0), 0, 10)
    p = 100 + 12 * (pain - 5) + rng.normal(0, 5, n)
    side = {"t": t, "power": p, "amp_Left": np.full(n, 2.0), "amp_Right": np.full(n, 2.0)}
    st, med = W.joint_stretches(side, dict(side))
    c = {"upper": 110.0, "lower": 90.0, "amp_low_mA": 1.0, "amp_high_mA": 4.0}
    ctrls = {(s, x): c for s in W.SIDES for x in W.SIDES}
    k = {"Left": {"Left": 0.0, "Right": 0.0}, "Right": {"Left": 0.0, "Right": 0.0}}
    rt = np.concatenate([t[::20] + 1.0, t[-1] + 10_000 + np.arange(500.0)])
    ry = np.concatenate([pain[::20], np.zeros(500)])
    day = (rt // 600).astype(int)
    out = W.compare(st, med, ctrls, k, rt, ry, day, timing=TIMING, n_boot=50)
    assert out["record"]["n_ratings_low"] >= 5 and out["record"]["n_ratings_high"] >= 5


def test_ratings_in_a_stretchs_opening_are_left_out():
    """Both controllers start mid-range at every stretch; a rating before they could move reads
    the starting point and is not scored."""
    n = 400
    t = np.arange(n) * DT
    side = {"t": t, "power": np.full(n, 100.0), "amp_Left": np.full(n, 2.0), "amp_Right": np.full(n, 2.0)}
    st, med = W.joint_stretches(side, dict(side))
    c = {"upper": 110.0, "lower": 90.0, "amp_low_mA": 1.0, "amp_high_mA": 4.0}
    ctrls = {(s, x): c for s in W.SIDES for x in W.SIDES}
    k = {"Left": {"Left": 0.0, "Right": 0.0}, "Right": {"Left": 0.0, "Right": 0.0}}
    rt = np.array([3.0, 9.0, 30.0, 300.0, 600.0])
    out = W.compare(st, med, ctrls, k, rt, np.array([1, 2, 3, 4, 5.0]), np.zeros(5), timing=TIMING, n_boot=10)
    opening = (TIMING["onset_ms"] + TIMING["transition_up_ms"]) / 1000.0
    assert out["record"]["opening_s"] == opening
    assert out["record"]["n_ratings_in_opening"] == int((rt < opening).sum())


def test_no_recommendation_when_no_wirings_current_rises_with_pain():
    sc = {"independent": 0.36, "left_both": 0.26, "right_both": 0.37}
    dr = {"independent": _draws(0.36, sd=0.1, seed=1), "left_both": _draws(0.26, sd=0.05, seed=2),
          "right_both": _draws(0.37, sd=0.1, seed=3)}
    r = W.recommend(sc, dr, {w: True for w in sc})
    assert r["wiring"] is None and r["basis"] == "none_follows_pain"
    # one that does rise with pain is named even when it is not the device's ordinary case
    dr["right_both"] = _draws(0.70, sd=0.02, seed=4)
    sc["right_both"] = 0.70
    assert W.recommend(sc, dr, {w: True for w in sc})["wiring"] == "right_both"
