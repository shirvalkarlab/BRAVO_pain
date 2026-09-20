"""Decision 213 (the PI, 2026-09-20, after the 2026-09-16 titration session was under-counted):

(a) JOINED RECORDINGS. The tablet restarted streaming twice during the left ladder on 2026-09-16
    (a 12 s gap at 12:22 with the current held at 2.0 mA across it). The run finder never joined
    two recordings, so one 9-step ladder became two runs of 3 and 8 settings, the 2.0 mA step was
    cut to 18 s, and the first setting of each recording was refused for having nothing before it.
    Now: consecutive recordings whose gap is shorter than the move-grouping window (20 s) and whose
    current is unchanged on both sides across the gap are one record for the run finder; and every
    setting carries the current the device was at BEFORE the move that produced it, read from the
    device's own record, so the first setting of a recording is judged like any other.

(b) BOTH LEGS. A setting is measured when the current CHANGED into it, rising or falling (his words:
    "pool both legs into the slope because we want to model slope in both directions"). Until now
    only a rise counted, so every down-leg step of every ladder was discarded. Each measured setting
    says which leg it is on.
"""
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import three_source_response as TSR
from ClosedLoopDeployment import amplitude_effect, ground_truth, run_points
from StimOptimizer.routines import within_visit as WV


def _ladder(t, points):
    out = np.zeros(t.size, dtype=float)
    for start, value in points:
        out[t >= start] = value
    return out


def _two_recordings(gap_s, *, current_after_gap=2.0):
    """The 2026-09-16 shape: a left ladder 0.5 -> 2.0 in one recording, a gap, then 2.0 -> 4.5 and
    a down leg in the next, the right held at 2.5 mA throughout."""
    t1 = np.arange(0.0, 372.0, 0.5)                                   # 0.5 at start; 1.0, 1.5, 2.0
    left1 = _ladder(t1, [(0, 0.5), (120, 1.0), (240, 1.5), (354, 2.0)])
    t2 = np.arange(372.0 + gap_s, 372.0 + gap_s + 1100.0, 0.5)
    b2 = t2[0]
    left2 = _ladder(t2, [(0, current_after_gap), (b2 + 90, 2.5), (b2 + 210, 3.0), (b2 + 330, 3.5),
                         (b2 + 450, 4.0), (b2 + 570, 4.5), (b2 + 690, 3.5), (b2 + 810, 2.5),
                         (b2 + 930, 1.5)])
    return {"blocks": [{"t": t1, "mA": {"ONE_THREE_LEFT": left1, "ZERO_THREE_RIGHT": np.full(t1.size, 2.5)}},
                       {"t": t2, "mA": {"ONE_THREE_LEFT": left2, "ZERO_THREE_RIGHT": np.full(t2.size, 2.5)}}],
            "contacts": ["ONE_THREE_LEFT", "ZERO_THREE_RIGHT"]}


# --- (a) joined recordings ---------------------------------------------------------------------

def test_a_streaming_restart_shorter_than_the_move_window_with_the_current_held_is_one_run():
    runs = TSR.find_single_side_runs_from_device(_two_recordings(12.0), min_settings=3)
    assert len(runs) == 1, [(r["side"], list(r["steps"]["current_mA"])) for r in runs]
    amp = list(runs[0]["steps"]["current_mA"].round(2))
    assert amp == pytest.approx([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 3.5, 2.5, 1.5]), amp
    # the 2.0 mA setting spans the gap: it starts at its own move and ends at the 2.5 move
    steps = runs[0]["steps"]
    row = steps[steps["current_mA"] == 2.0].iloc[0]
    assert row["t_end"] - row["t0"] == pytest.approx(18.0 + 12.0 + 90.0)


def test_a_gap_longer_than_the_move_window_is_still_two_records():
    runs = TSR.find_single_side_runs_from_device(_two_recordings(60.0), min_settings=3)
    assert len(runs) == 2


def test_a_gap_across_which_the_current_changed_is_not_joined():
    runs = TSR.find_single_side_runs_from_device(_two_recordings(12.0, current_after_gap=2.5), min_settings=3)
    assert len(runs) == 2


def test_every_setting_carries_the_current_the_device_was_at_before_its_move():
    runs = TSR.find_single_side_runs_from_device(_two_recordings(12.0), min_settings=3)
    steps = runs[0]["steps"]
    assert "prev_current_mA" in steps.columns
    assert list(steps["prev_current_mA"].round(2)) == pytest.approx(
        [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 3.5, 2.5])


# --- (b) both legs -------------------------------------------------------------------------------

def _pieces(t0, currents, *, hold_s=60.0, piece_s=3.0, base=100.0, per_mA=10.0):
    ts, ps = [], []
    for a, c in zip(t0, currents):
        for j in range(int(hold_s // piece_s)):
            ts.append(a + j * piece_s); ps.append(np.full(5, base + per_mA * c))
    o = np.argsort(np.asarray(ts, dtype=float))
    return np.asarray(ts, dtype=float)[o], np.vstack(ps)[o]


def test_a_setting_reached_by_turning_the_current_down_is_measured_and_named_falling():
    amp = np.array([1.0, 3.0, 2.0, 2.5])
    t0 = 1000.0 + 60.0 * np.arange(4)
    tt, tp = _pieces(t0, amp)
    P, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=["r"] * 4)
    assert bool(T.iloc[2].accepted) and np.allclose(P[2, :], 120.0)
    assert list(T["leg"]) == ["first", "rising", "falling", "rising"]
    assert bool(T.iloc[2].current_fell_into_this_setting) and not bool(T.iloc[2].current_rose_into_this_setting)


def test_the_first_setting_of_a_block_is_measured_when_the_caller_says_what_came_before_it():
    amp = np.array([1.0, 1.1, 1.2, 1.3])
    t0 = 1000.0 + 60.0 * np.arange(4)
    tt, tp = _pieces(t0, amp)
    _, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=["r"] * 4)
    assert not bool(T.iloc[0].accepted) and T.iloc[0]["leg"] == "first"
    _, T2 = WV.mean_power_before_next_change(t0, amp, tt, tp, block=["r"] * 4,
                                              prev_current_mA=[0.5, 1.0, 1.1, 1.2])
    assert bool(T2.iloc[0].accepted) and T2.iloc[0]["leg"] == "rising"


def test_a_setting_the_current_did_not_change_into_is_refused_with_a_reason():
    amp = np.array([1.0, 2.0, 2.0, 3.0])
    t0 = 1000.0 + 60.0 * np.arange(4)
    tt, tp = _pieces(t0, amp)
    _, T = WV.mean_power_before_next_change(t0, amp, tt, tp, block=["r"] * 4)
    assert not bool(T.iloc[2].accepted) and "did not change" in T.iloc[2].refusal_reason


def test_the_old_rise_only_switch_is_gone():
    amp = np.array([1.0, 2.0]); t0 = np.array([0.0, 60.0]); tt, tp = _pieces(t0, amp)
    with pytest.raises(TypeError):
        WV.mean_power_before_next_change(t0, amp, tt, tp, require_rise_into_setting=False)
    with pytest.raises(TypeError):
        TSR.settled_device_band_power(t0, t0 + 60, amp, tt, tp[:, 0], np.zeros(tt.size),
                                      require_rise_into_setting=False)


def test_the_device_route_measures_a_falling_step_too():
    currents = [1.0, 3.0, 2.0, 2.5]
    hold = 60.0; fs = 2.0
    n = int(4 * hold * fs); t = 1000.0 + np.arange(n) / fs
    mA = np.zeros(n)
    for i, c in enumerate(currents):
        mA[(t >= 1000.0 + i * hold) & (t < 1000.0 + (i + 1) * hold)] = c
    t0 = 1000.0 + hold * np.arange(4); t_end = t0 + hold
    power, table = TSR.settled_device_band_power(t0, t_end, np.array(currents), t, np.full(n, 300.0), mA)
    assert bool(table.iloc[2].accepted) and table.iloc[2]["leg"] == "falling"


def test_the_run_points_rows_name_the_leg():
    steps = pd.DataFrame({"t0": 1e6 + 60.0 * np.arange(4), "t_end": 1e6 + 60.0 * np.arange(1, 5),
                          "current_mA": [1.0, 3.0, 2.0, 2.5], "block": ["run 1"] * 4,
                          "prev_current_mA": [0.0, 1.0, 3.0, 2.0]})
    n = int(4 * 60 / 3); tt = 1e6 + 3.0 * np.arange(n)
    centres = np.arange(2.5, 100.5, 1.0)
    tiles = {"centers_hz": centres.tolist(), "band_half_hz": 2.5, "window_s": 3.0,
             "td": {"t": tt, "lsb": np.full((n, centres.size), 100.0), "ok": np.ones(n, bool), "saturated": np.zeros(n, bool)},
             "psd": {"t": np.empty(0), "lsb": np.empty((0, centres.size))}}
    comp = TSR.build_comparison(label="t", ramped_side="Left", sensing_contact="ONE_THREE_LEFT", steps=steps,
                                visit_date="2026-09-16", window_start_local="x", window_end_local="y",
                                tiles=tiles, device_band_power=None, stimulation_rate_hz=55.0)
    rows = pd.DataFrame(TSR.comparison_rows(comp))
    assert "leg" in rows.columns
    td = rows[(rows["source"] == TSR.SOURCE_TIME_DOMAIN) & rows["current_mA"].notna()]
    got = dict(zip(td["current_mA"], td["leg"]))
    assert got[2.0] == "falling" and got[3.0] == "rising" and got[1.0] == "rising"


def test_every_table_built_from_runs_has_a_new_rule_version():
    for v in (run_points.RULE_VERSION, amplitude_effect.RULE_VERSION, amplitude_effect.POOLED_RULE_VERSION,
              ground_truth.RULE_VERSION):
        assert "both_legs" in v, v
