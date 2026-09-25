"""The carry-over test on constructed ladders (2026-09-25): does pain at one current depend on
whether the current was reached going up or coming down? Written before the module, watched RED."""
import numpy as np
import pandas as pd

try:
    from modules.ControlAnalyses import carry_over as CO
except ImportError:                                            # host spelling
    from ControlAnalyses import carry_over as CO


def _visit(amp_L, amp_R, pain, *, visit="v1", t0=0.0, step_s=60.0, cfg="55|100|150|c", rows=None):
    n = len(amp_L)
    return pd.DataFrame(dict(visit=visit, t_s=t0 + step_s * np.arange(n, dtype=float),
                             row_index=np.arange(n) if rows is None else rows,
                             amp_L=np.asarray(amp_L, float), amp_R=np.asarray(amp_R, float),
                             cfg=cfg, overall=np.asarray(pain, float), setting="clinic"))


def test_a_step_with_no_time_keeps_its_place_below_the_row_above():
    t = np.array([100.0, np.nan, 300.0, 50.0])
    rows = np.array([1, 2, 3, 0])
    order = CO.visit_order(t, rows)
    assert list(order) == [3, 0, 1, 2]


def test_legs_follow_the_last_change_through_a_held_reading():
    # left 0 -> 1 -> 1 (held) -> 2 -> 1, right held at 2.5
    aL = [0, 1, 1, 2, 1]
    aR = [2.5] * 5
    b = CO.blocks(aL, aR, ["k"] * 5)
    assert list(b["block"]) == [0, 1, 1, 2, 3]
    assert b["leg_Left"] == [None, "rising", "rising", "rising", "falling"]
    assert b["leg_Right"] == [None, None, None, None, None]
    assert list(b["from_Left"][[1, 3, 4]]) == [0.0, 1.0, 2.0]


def test_no_leg_when_the_rate_changes_or_both_sides_move_at_once():
    aL = [0, 1, 2, 3]
    aR = [0, 0, 1, 1]
    cfg = ["a", "b", "b", "b"]
    b = CO.blocks(aL, aR, cfg)
    assert b["leg_Left"][1] is None                  # the rate or pulse width changed with it
    assert b["leg_Left"][2] is None and b["leg_Right"][2] is None   # both sides moved
    assert b["leg_Left"][3] == "rising"


def test_a_side_not_written_on_either_step_counts_as_unchanged():
    aL = [np.nan, np.nan, np.nan]
    aR = [1.0, 2.0, 1.0]
    b = CO.blocks(aL, aR, ["k"] * 3)
    assert b["leg_Right"] == [None, "rising", "falling"]


def test_pairs_at_matched_currents_use_each_block_s_last_reading():
    # up 0, 1, 2 (each written twice), down 1; pain at the second reading of 1 mA up is 5
    aL = [0, 0, 1, 1, 2, 2, 1, 1]
    pain = [8, 8, 6, 5, 4, 4, 3, 3]
    d = _visit(aL, [2.5] * 8, pain)
    long = CO.step_frame(d)
    pairs = CO.leg_pairs(long, "overall")
    assert len(pairs) == 1
    p = pairs.iloc[0]
    assert p["side"] == "Left" and p["current_mA"] == 1.0
    assert p["rising"] == 5.0 and p["falling"] == 3.0 and p["diff"] == -2.0
    assert not p["falling_first"]
    assert p["other_mA"] == 2.5


def test_carry_over_reads_the_same_sign_whichever_leg_came_first():
    rng = np.random.default_rng(1)
    frames = []
    for k in range(12):
        up = [0, 1, 2, 3, 2, 1, 0]
        down = [3, 2, 1, 0, 1, 2, 3]
        aL = up if k % 2 == 0 else down
        cur = np.asarray(aL, float)
        prev = np.concatenate([[cur[0]], cur[:-1]])
        fell = cur < prev
        pain = 7 - 0.6 * cur - 1.0 * fell + 0.1 * rng.standard_normal(cur.size)
        frames.append(_visit(aL, [0] * 7, pain, visit=f"v{k}", t0=1e5 * k))
    long = CO.step_frame(pd.concat(frames, ignore_index=True))
    pairs = CO.leg_pairs(long, "overall")
    s = CO.by_order(pairs)
    assert s["falling after rising"]["mean"] < -0.8
    assert s["falling before rising"]["mean"] < -0.8


def test_drift_within_the_visit_flips_sign_with_the_order():
    frames = []
    for k in range(12):
        up = [0, 1, 2, 3, 2, 1, 0]
        down = [3, 2, 1, 0, 1, 2, 3]
        aL = up if k % 2 == 0 else down
        minutes = np.arange(7, dtype=float)
        pain = 7 - 0.3 * minutes                     # no carry-over: pain simply falls with time
        frames.append(_visit(aL, [0] * 7, pain, visit=f"v{k}", t0=1e5 * k))
    long = CO.step_frame(pd.concat(frames, ignore_index=True))
    s = CO.by_order(CO.leg_pairs(long, "overall"))
    assert s["falling after rising"]["mean"] < 0
    assert s["falling before rising"]["mean"] > 0


def test_summary_resamples_whole_visits():
    diffs = np.array([-1.0, -1.0, -1.0, 5.0, -1.0, -1.0])
    units = np.array(["a", "a", "a", "b", "c", "c"])
    s = CO.paired_summary(diffs, units, n_boot=500, seed=0)
    assert s["n_pairs"] == 6 and s["n_visits"] == 3
    assert s["n_lower"] == 5 and s["n_higher"] == 1 and s["n_same"] == 0
    assert s["lo"] <= s["mean"] <= s["hi"]
    # a sign flip moves a visit's pairs together, so three visits give 2**3 arrangements
    assert s["p_sign_flip"] >= 1 / 8


def test_repeated_readings_at_one_setting_give_the_change_between_them():
    aL = [0, 0, 1, 1, 1]
    pain = [8, 7, 6, 5, 4]
    long = CO.step_frame(_visit(aL, [0] * 5, pain))
    h = CO.held_changes(long, "overall")
    assert list(h["change"]) == [-1.0, -2.0]
    assert list(h["on"]) == [False, True]
    assert list(h["minutes"]) == [1.0, 2.0]


def test_ladder_power_pairs_compare_settled_power_at_one_current():
    rp = pd.DataFrame(dict(
        source="time domain voltage trace", run="r1", sensing_contact="ONE_THREE_LEFT",
        band_centre_hz=20.5, band_is_measuring_the_stimulator=False,
        current_mA=[0.0, 1.0, 2.0, 1.0, 0.0],
        leg=["first", "rising", "rising", "falling", "falling"],
        settled_band_power_device_units=[100.0, 90.0, 80.0, 72.0, np.nan],
        why_not_used=["", "", "", "", "too few pieces"],
        window_start_local="2026-09-16 13:00:04"))
    pairs = CO.ladder_pairs(rp)
    assert len(pairs) == 1
    p = pairs.iloc[0]
    assert p["current_mA"] == 1.0 and p["rising"] == 90.0 and p["falling"] == 72.0
    assert abs(p["relative_diff"] - (72.0 / 90.0 - 1.0)) < 1e-12


def _s(mean, lo, hi, n=4):
    return dict(mean=mean, lo=lo, hi=hi, n_pairs=n, n_visits=n)


def test_the_reading_names_carry_over_only_when_both_orders_agree():
    both_low = {"falling after rising": _s(-1.0, -1.5, -0.4), "falling before rising": _s(-0.8, -1.4, -0.2)}
    assert CO.order_reading(both_low)[0] == "carry-over"
    flips = {"falling after rising": _s(-1.0, -1.5, -0.4), "falling before rising": _s(0.7, 0.1, 1.2)}
    assert CO.order_reading(flips)[0] == "drift"
    one_order = {"falling after rising": _s(-1.0, -1.5, -0.4), "falling before rising": _s(None, None, None, 0)}
    assert CO.order_reading(one_order)[0] == "one order"
    unclear = {"falling after rising": _s(-0.2, -0.9, 0.5), "falling before rising": _s(0.1, -0.6, 0.7)}
    assert CO.order_reading(unclear)[0] == "no difference"
