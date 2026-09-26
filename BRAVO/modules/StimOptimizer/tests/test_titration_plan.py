"""The titration session the Stim Optimizer recommends for the next visit (`titration_plan.py`,
2026-09-12 evening: open item 30 and the 20 s post-ramp margin of decision 144 joined into one
recommendation; REVISED 2026-09-14, the PI's ruling on the ladder's down leg, the two-row step,
the held other side, the joint corners and the flat clinic-sheet rows).

Values, never shapes: the ladder goes UP in 0.5 mA steps to the ceiling (rounding down when the
ceiling is not a multiple of the step) and back DOWN in 1.0 mA drops, always ending at 0; a rate
below 55 Hz is lifted to 55 with the reason; the harmonic-avoidance lists for 55, 110 and 145 Hz
are pinned centre by centre; a step is a ramp row then a test row, 60 s each; the points-yield
arithmetic; `post_ramp.margin_becomes_available` on a constructed table with a 6-setting run
(False) and an 8-setting run (True); the joint-corners block caps, dedupes and excludes; the flat
clinic-sheet rows carry the real workbook's own column order and the "L x / R y" bilateral form;
and the service response carries `titration_plan` for both sides with every `source` non-empty.
"""
import shutil
import sys
import tempfile
import types

import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import amplitude_effect as AE
from ClosedLoopDeployment import post_ramp as PR
from StimOptimizer import titration_plan as TP
from StimOptimizer.routines import percept_adaptive as PA
from StimOptimizer.routines import within_visit as WV


# ---------------------------------------------------------------------------------------------
# the ladder: up in 0.5 mA steps, down in 1.0 mA drops (the PI's ruling, 2026-09-14)
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("ceiling", [5.0, 4.8, 3.0, 0.5, 2.25, 6.0])
def test_the_ladder_never_exceeds_the_ceiling_goes_up_then_down_and_ends_at_zero(ceiling):
    lad = TP.ladder(ceiling)
    assert max(lad["steps_mA"]) <= ceiling + 1e-9
    assert lad["top_mA"] == max(lad["steps_mA"])
    assert lad["steps_mA"][0] == 0.0 and lad["steps_mA"][-1] == 0.0
    up = lad["steps_mA"][: lad["n_distinct_currents_up"]]
    down = lad["steps_mA"][lad["n_distinct_currents_up"]:]
    assert up == [round(0.5 * i, 3) for i in range(lad["n_distinct_currents_up"])]
    assert len(down) == lad["n_down"]
    assert lad["n_steps"] == lad["n_distinct_currents_up"] + lad["n_down"]
    # the down leg never takes a step bigger than 1.0 mA, and never goes back up
    full = [up[-1]] + down
    for a, b in zip(full, full[1:]):
        assert 0.0 < a - b <= 1.0 + 1e-9


def test_the_ladder_for_the_stated_4_5_mA_ceiling_is_10_up_and_5_down():
    """The PI's own worked example, 2026-09-14: "4.5 -> 0, 0.5, ..., 4.5 = 10 steps" on the way
    up, "3.5, 2.5, 1.5, 0.5, 0" on the way down."""
    lad = TP.ladder(4.5)
    assert lad["top_mA"] == 4.5
    assert lad["n_distinct_currents_up"] == 10 and lad["n_down"] == 5 and lad["n_steps"] == 15
    assert lad["steps_mA"] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5,
                               3.5, 2.5, 1.5, 0.5, 0.0]
    assert lad["compact"] == "0 → 0.5 → … → 4.5 → … → 0 mA"


def test_the_ladder_for_the_stated_5_mA_ceiling_is_11_up_and_5_down():
    lad = TP.ladder(5.0)
    assert lad["top_mA"] == 5.0
    assert lad["n_distinct_currents_up"] == 11 and lad["n_down"] == 5 and lad["n_steps"] == 16
    assert lad["steps_mA"] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0,
                               4.0, 3.0, 2.0, 1.0, 0.0]


def test_a_ceiling_below_1_0_mA_still_ends_at_zero_with_one_down_row():
    # top=0.5: the down leg's first 1.0 mA drop would go negative, so it lands straight on 0.
    lad = TP.ladder(0.5)
    assert lad["top_mA"] == 0.5 and lad["n_distinct_currents_up"] == 2
    assert lad["n_down"] == 1 and lad["steps_mA"][-2:] == [0.5, 0.0]


def test_a_ceiling_that_is_not_a_multiple_of_the_step_rounds_down_and_says_so():
    lad = TP.ladder(4.8)
    assert lad["top_mA"] == 4.5 and lad["n_distinct_currents_up"] == 10 and lad["n_down"] == 5
    assert lad["n_steps"] == 15
    assert "not a multiple of 0.5 mA" in lad["why"]


def test_no_ceiling_means_no_ladder_and_a_reason():
    for bad in (None, 0.0, -1.0, float("nan")):
        lad = TP.ladder(bad)
        assert lad["steps_mA"] == [] and lad["n_steps"] == 0 and lad["top_mA"] is None
        assert lad["n_down"] == 0 and lad["n_distinct_currents_up"] == 0
        assert "no ceiling" in lad["why"]


# ---------------------------------------------------------------------------------------------
# the rate
# ---------------------------------------------------------------------------------------------
def test_a_rate_below_55_hz_is_lifted_to_55_with_the_reason():
    r = TP.rate_to_hold(40.0)
    assert r["rate_hz"] == 55.0 and r["rate_in_force_hz"] == 40.0 and r["lifted"] is True
    assert "40 Hz" in r["why"] and "55 Hz" in r["why"] and "decision 138" in r["why"]
    assert PA.MIN_ADAPTIVE_RATE_HZ == 55.0


def test_a_rate_at_or_above_55_hz_is_held_as_is():
    for rate in (55.0, 110.0, 145.0):
        r = TP.rate_to_hold(rate)
        assert r["rate_hz"] == rate and r["lifted"] is False and f"{rate:g} Hz" in r["why"]


def test_no_rate_on_record_means_the_adaptive_minimum_and_says_so():
    r = TP.rate_to_hold(None)
    assert r["rate_hz"] == 55.0 and r["rate_in_force_hz"] is None and r["lifted"] is True
    assert "no stimulation rate is on record" in r["why"]


# ---------------------------------------------------------------------------------------------
# the harmonic avoidance, pinned on the VALUES
# ---------------------------------------------------------------------------------------------
def test_the_22_centres_are_8_5_to_29_5_hz():
    assert list(TP.CENTRES_HZ) == [8.5 + i for i in range(22)]


def test_harmonic_avoidance_at_55_hz():
    """Found 2026-09-25: the old code folded only |250 - rate| (195 Hz at 55 Hz, nowhere near the
    grid) and missed every higher multiple. `analytics.harmonic_landings_hz` folds the fourth
    multiple (220 Hz) to 30 Hz and the fifth (275 Hz) to 25 Hz, both of which land inside or right
    at the edge of the 8.5-29.5 Hz grid -- so 25 Hz now also catches 24.5 Hz, the band decision 236
    called "the one clean band to watch"."""
    h = TP.harmonic_avoidance(55.0)
    assert h["harmonics_hz"] == {"multiple_4": 30.0, "multiple_5": 25.0, "half_rate": 27.5,
                                 "quarter_rate": 13.75, "three_quarters_rate": 41.25}
    assert h["harmonic_names"]["multiple_5"] == ("the fifth multiple of the rate folded by the "
                                                 "device's 250 Hz sampling")
    assert h["harmonic_names"]["multiple_4"] == ("the fourth multiple of the rate folded by the "
                                                 "device's 250 Hz sampling")
    # 13.75 +/- 2.5 -> 11.25..16.25 catches 11.5, 12.5, 13.5, 14.5, 15.5; 25 +/- 2.5 -> 22.5..27.5
    # catches 22.5, 23.5, 24.5, 25.5, 26.5, 27.5; 27.5 +/- 2.5 -> 25..30 catches 25.5-29.5; 30 +/-
    # 2.5 -> 27.5..32.5 catches 27.5, 28.5, 29.5; 41.25 is outside the grid.
    assert h["avoid_hz"] == [11.5, 12.5, 13.5, 14.5, 15.5, 22.5, 23.5, 24.5, 25.5, 26.5, 27.5, 28.5, 29.5]
    assert h["clear_hz"] == [8.5, 9.5, 10.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5]
    assert h["n_clear"] == 9 and h["n_avoid"] == 13
    assert "13.75 Hz" in h["avoid_reasons"]["13.5"] and "quarter" in h["avoid_reasons"]["13.5"]
    assert "27.5 Hz" in h["avoid_reasons"]["29.5"] and "half" in h["avoid_reasons"]["29.5"]
    assert "25 Hz" in h["avoid_reasons"]["24.5"] and "fifth multiple" in h["avoid_reasons"]["24.5"]
    # the PI's own correction, 2026-09-06: never claim the band MEASURES the stimulator, only that
    # it carries a folded multiple and needs care -- the old (buggy) wording is gone
    assert "of one of those measures the stimulator" not in h["why"]
    assert "the PI, 2026-09-06" in h["why"]


def test_harmonic_avoidance_at_110_hz():
    """Found 2026-09-25: the seventh multiple (770 Hz) folds to 20 Hz, newly avoided; the second
    (220 Hz) folds to 30 Hz, which only reaches 29.5 Hz, already avoided through the quarter rate."""
    h = TP.harmonic_avoidance(110.0)
    assert h["harmonics_hz"] == {"multiple_2": 30.0, "multiple_7": 20.0, "half_rate": 55.0,
                                 "quarter_rate": 27.5, "three_quarters_rate": 82.5}
    assert h["avoid_hz"] == [17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 25.5, 26.5, 27.5, 28.5, 29.5]
    assert h["n_clear"] == 11
    assert h["clear_hz"][0] == 8.5 and h["clear_hz"][-1] == 24.5


def test_harmonic_avoidance_at_145_hz_now_finds_two_landings_inside_the_grid():
    """Found 2026-09-25: this rate used to pass as leaving every centre clear -- a symptom of the
    same bug, since the fifth multiple (725 Hz) folds to 25 Hz and the seventh (1015 Hz) to 15 Hz,
    both inside the grid."""
    h = TP.harmonic_avoidance(145.0)
    assert h["harmonics_hz"] == {"multiple_5": 25.0, "multiple_7": 15.0, "half_rate": 72.5,
                                 "quarter_rate": 36.25, "three_quarters_rate": 108.75}
    assert h["avoid_hz"] == [12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 22.5, 23.5, 24.5, 25.5, 26.5, 27.5]
    assert h["n_clear"] == 10 and h["n_avoid"] == 12


def test_a_candidate_centre_is_judged_the_same_way():
    # 24.5 Hz is no longer clear at 55 Hz after the fix (it now catches the fifth-multiple landing
    # at 25 Hz); 20.5 Hz stays genuinely clear.
    h = TP.harmonic_avoidance(55.0, candidate_center_hz=24.5)
    assert h["candidate_clear"] is False and "25 Hz" in h["candidate_note"]
    h2 = TP.harmonic_avoidance(55.0, candidate_center_hz=20.5)
    assert h2["candidate_clear"] is True and "clear" in h2["candidate_note"]
    h3 = TP.harmonic_avoidance(55.0, candidate_center_hz=27.5)
    assert h3["candidate_clear"] is False and "27.5 Hz" in h3["candidate_note"]


# ---------------------------------------------------------------------------------------------
# the hold (test row, unchanged) and the step timing (ramp + test, new 2026-09-14)
# ---------------------------------------------------------------------------------------------
def test_the_hold_is_at_least_60_s_and_leaves_at_least_10_usable_pieces_after_the_margin():
    h = TP.hold_per_step()
    assert h["seconds"] >= 60.0
    assert h["seconds"] == 30.0 + 20.0 + 10.0
    assert h["settled_window_s"] == WV.PRE_CHANGE_WINDOW_S == 30.0
    assert h["post_ramp_margin_s"] == WV.RAMP_EXCLUDE_S == 20.0
    assert h["piece_s"] == WV.CHUNK_S == 3.0
    assert h["min_pieces_required"] == WV.MIN_CHUNKS_PRE_CHANGE == 10
    assert h["usable_pieces_after_margin"] == 13 >= h["min_pieces_required"]
    assert "30 s settled window" in h["why"] and "20 s" in h["why"] and "10 s of slack" in h["why"]


def test_the_step_timing_is_a_60_s_ramp_row_then_the_60_s_test_row_120_s_a_step():
    t = TP.step_timing()
    assert t["ramp_s"] == 60.0
    assert t["test_s"] == TP.hold_per_step()["seconds"] == 60.0
    assert t["total_s"] == 120.0
    assert "ramp row" in t["why"] and "test row" in t["why"] and "2 min" in t["why"]


# ---------------------------------------------------------------------------------------------
# the per-run points table and the margin
# ---------------------------------------------------------------------------------------------
def _run_rows(run, currents, contact="ONE_THREE_LEFT", source="time domain voltage trace",
              centres=(20.5, 24.5), value=100.0):
    rows = []
    for c in currents:
        for f in centres:
            rows.append(dict(run=run, sensing_contact=contact, source=source, current_mA=float(c),
                             band_centre_hz=float(f), settled_band_power_device_units=value))
    return rows


def test_margin_becomes_available_is_false_on_a_six_setting_run_and_true_on_an_eight_setting_run():
    six = pd.DataFrame(_run_rows("2026-08-18 L", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]))
    switch_before = PR.USE_POST_RAMP_MARGIN
    m = PR.margin_becomes_available(six)
    assert m["available"] is False and m["min_settled_settings"] == AE.MIN_POINTS_CURVATURE == 8
    assert m["max_settled_settings_in_one_run"] == 6 and m["run"] == "2026-08-18 L"
    assert m["n_runs"] == 1 and m["runs_at_or_above_floor"] == []
    assert "no run holds 8 settled settings" in m["note"] and "6" in m["note"]
    assert m["switch_on"] is switch_before and PR.USE_POST_RAMP_MARGIN is switch_before   # NOT flipped here

    eight = pd.DataFrame(_run_rows("titration L", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]))
    m2 = PR.margin_becomes_available(pd.concat([six, eight], ignore_index=True))
    assert m2["available"] is True and m2["n_runs"] == 2
    assert m2["max_settled_settings_in_one_run"] == 8 and m2["run"] == "titration L"
    assert m2["runs_at_or_above_floor"] == [{"run": "titration L", "sensing_contact": "ONE_THREE_LEFT",
                                             "n_settled_settings": 8}]


def test_margin_counts_settled_values_on_the_voltage_trace_route_only_and_distinct_currents():
    # eight currents but two of them carry no settled value -> 6; and a device route with eight
    # settled currents does not count
    rows = _run_rows("r", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]) + \
        _run_rows("r", [3.0, 3.5], value=float("nan")) + \
        _run_rows("r", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5], source="device's own band power")
    m = PR.margin_becomes_available(pd.DataFrame(rows))
    assert m["max_settled_settings_in_one_run"] == 6 and m["available"] is False
    # the same current at two band centres is ONE setting
    per = TP.settled_settings_per_run(pd.DataFrame(_run_rows("r", [1.0, 1.0, 2.0], centres=(10.5, 11.5, 12.5))))
    assert per["n_settled_settings"].tolist() == [2]


def test_margin_on_no_table_says_nothing_was_counted():
    m = PR.margin_becomes_available(None)
    assert m["available"] is False and m["table_stored"] is False
    assert "not stored" in m["note"] and m["max_settled_settings_in_one_run"] is None
    m2 = PR.margin_becomes_available(pd.DataFrame())
    assert m2["available"] is False and m2["table_stored"] is True and m2["n_runs"] == 0


# ---------------------------------------------------------------------------------------------
# what the record holds today, and the yield arithmetic
# ---------------------------------------------------------------------------------------------
def _pooled(contact="ONE_THREE_LEFT"):
    return pd.DataFrame([
        dict(sensing_contact=contact, band_center_hz=20.5, n=13, n_visits=4),
        dict(sensing_contact=contact, band_center_hz=24.5, n=11, n_visits=3),
        dict(sensing_contact=contact, band_center_hz=72.5, n=40, n_visits=9),   # outside 8-30 Hz
        dict(sensing_contact="ZERO_THREE_RIGHT", band_center_hz=20.5, n=12, n_visits=6),
    ])


def test_record_today_reads_the_best_covered_centre_inside_the_adaptive_window_for_that_contact():
    runs = pd.DataFrame(_run_rows("a", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]) + _run_rows("b", [1.0, 2.0, 3.0]))
    rec = TP.record_today_for_contact(_pooled(), runs, "ONE_THREE_LEFT", lo_hz=8.0, hi_hz=30.0)
    assert rec["points"] == 13 and rec["runs"] == 4 and rec["band_center_hz"] == 20.5
    assert rec["n_centres_at_max"] == 1 and rec["n_centres_in_window"] == 2   # 72.5 Hz is outside
    assert rec["max_settled_settings_in_one_run"] == 6 and rec["n_runs_on_contact"] == 2
    assert "13 settled points across 4 runs" in rec["note"] and "at most 6 settled currents" in rec["note"]
    assert "1 of 2 centres" in rec["note"]
    other = TP.record_today_for_contact(_pooled(), runs, "ZERO_THREE_RIGHT", lo_hz=8.0, hi_hz=30.0)
    assert other["points"] == 12 and other["runs"] == 6 and other["max_settled_settings_in_one_run"] is None
    assert "no run on this contact" in other["note"]


def test_record_today_with_no_tables_says_so_rather_than_zero():
    rec = TP.record_today_for_contact(None, None, "ONE_THREE_LEFT")
    assert rec["points"] is None and rec["max_settled_settings_in_one_run"] is None
    assert rec["pooled_table_stored"] is False and rec["run_points_table_stored"] is False
    assert "not stored yet" in rec["note"]
    none = TP.record_today_for_contact(_pooled(), None, None)
    assert "no sensing contact" in none["note"]


def _side(**kw):
    base = dict(rate_in_force_hz=55.0, rate_source="stream", pulse_width_us=100.0,
                pulse_width_source="stream", ceiling_mA=5.0, ceiling_source="stated by PI",
                contact={"channel": "ONE_THREE_LEFT", "display_short": "L 1⁻3⁺", "n_responding": 12,
                         "n_bands": 18, "laterality": "ipsilateral", "deployable": True,
                         "rate_hz": 55.0, "sensing_side": "Left"},
                contact_source="the readiness screen",
                record_today=TP.record_today_for_contact(
                    _pooled(), pd.DataFrame(_run_rows("a", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])),
                    "ONE_THREE_LEFT", lo_hz=8.0, hi_hz=30.0))
    base.update(kw)
    return base


def test_the_points_yield_arithmetic_and_the_settled_margin_sentence():
    """S7 settled (decision 196, 2026-09-17): the post-move margin is 0 s by measurement -- on the
    2026-09-16 titration session the first 3 s after a current move read 1.000 of the same
    setting's last-30 s level (31 settings, 95 % 0.86-1.16) -- so the sentence states that, and
    never says the margin is waiting on anything."""
    runs = pd.DataFrame(_run_rows("a", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]))
    margin = PR.margin_becomes_available(runs)
    p = TP.side_plan("Left", margin=margin, **_side())
    y = p["yield"]
    assert y["settled_points_from_session"] == 16 == p["ladder"]["n_steps"]   # 5.0 mA -> 11 up + 5 down
    assert y["distinct_currents_up_leg"] == 11
    assert y["margin_switched_on_today"] is False
    s = y["sentence"]
    assert "13 settled points across 4 runs" in s and "at most 6 currents in any one run" in s
    assert "16 settled points" in s and "11 distinct currents" in s
    assert "post-move margin is 0 s" in s and "measured" in s
    for retired in ("stays off", "switched on", "can be switched on", "could not be judged"):
        assert retired not in s, retired


def test_the_settled_margin_sentence_does_not_depend_on_the_per_run_table():
    y = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side())["yield"]
    assert "post-move margin is 0 s" in y["sentence"] and "could not be judged" not in y["sentence"]


def test_a_lifted_rate_changes_the_band_list_and_the_source_names_the_minimum():
    p = TP.side_plan("Right", margin=PR.margin_becomes_available(None), **_side(rate_in_force_hz=40.0))
    assert p["rate_hz"] == 55.0 and p["rate_lifted"] is True
    assert p["bands"]["rate_hz"] == 55.0 and p["bands"]["avoid_hz"][:2] == [11.5, 12.5]
    assert "MIN_ADAPTIVE_RATE_HZ" in p["sources"]["rate_hz"] and "decision 138" in p["sources"]["rate_hz"]


def test_a_contralateral_contact_is_named_as_on_the_other_side():
    c = {"channel": "ZERO_THREE_RIGHT", "display_short": "R 0⁻3⁺", "n_responding": 9, "n_bands": 18,
         "laterality": "contralateral", "deployable": True, "rate_hz": 55.0, "sensing_side": "Right"}
    p = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side(contact=c))
    assert p["sensing_contact"]["on_other_side"] is True
    assert "OTHER side" in p["sensing_contact"]["note"] and "Right" in p["sensing_contact"]["note"]
    p2 = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side(contact=None))
    assert p2["sensing_contact"] is None and "no sensing contact is named" in p2["sensing_contact_note"]


def test_every_source_is_non_empty_and_every_number_has_one():
    p = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side())
    src = p["sources"]
    for k in ("rate_hz", "pulse_width_us", "ceiling_mA", "sensing_contact", "held_other_side",
              "ladder", "step_timing", "hold", "bands", "yield.settled_points_from_session",
              "yield.record_today", "yield.margin", "conditions"):
        assert isinstance(src.get(k), str) and src[k].strip(), k
    for k in ("rate_hz", "pulse_width_us", "ceiling_mA"):
        assert p[k] is not None
    assert any("FIXED measurement current" in c for c in p["conditions"])
    # no decision number in the words the page prints (the design review of 2026-09-26)
    assert not any("decision" in c for c in p["conditions"])
    assert any("streaming on" in c for c in p["conditions"])
    assert any("baseline before" in c for c in p["conditions"])


# ---------------------------------------------------------------------------------------------
# the other side is held at its own current in force (new, 2026-09-14)
# ---------------------------------------------------------------------------------------------
def test_held_other_side_is_reported_and_reaches_the_sources():
    p = TP.side_plan("Left", margin=PR.margin_becomes_available(None),
                     held_other_side_mA=2.5, held_other_side_source="the Right side, stream",
                     **_side())
    assert p["held_other_side"] == {"current_mA": 2.5, "source": "the Right side, stream"}
    assert p["sources"]["held_other_side"] == "the Right side, stream"
    assert any("HELD" in c for c in p["conditions"])


def test_no_held_other_side_reading_says_so_rather_than_zero():
    p = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side())
    assert p["held_other_side"]["current_mA"] is None
    assert p["held_other_side"]["source"] == "no reading for the other side"


# ---------------------------------------------------------------------------------------------
# the joint corners (optional): caps, dedupes and excludes
# ---------------------------------------------------------------------------------------------
def test_joint_corners_are_the_four_1_0_4_0_combinations_capped_at_each_sides_ceiling():
    jc = TP.joint_corners(4.5, 4.5)
    pts = {(p["amp_left_mA"], p["amp_right_mA"]) for p in jc["points"]}
    assert pts == {(1.0, 1.0), (4.0, 1.0), (1.0, 4.0), (4.0, 4.0)}
    assert jc["optional"] is True and "off-diagonal" in jc["why"]
    assert jc["n_points"] == 4 and jc["n_excluded"] == 0


def test_a_low_ceiling_caps_and_can_collapse_two_corners_together():
    jc = TP.joint_corners(0.8, 4.5)   # the left 4.0 mA corners both cap to 0.8
    pts = {(p["amp_left_mA"], p["amp_right_mA"]) for p in jc["points"]}
    assert pts == {(0.8, 1.0), (0.8, 4.0)}
    assert jc["n_points"] == 2


def test_an_unsafe_corner_is_excluded_and_named_not_silently_dropped():
    def is_safe(l, r):
        return not (l >= 4.0 and r >= 4.0)
    jc = TP.joint_corners(4.5, 4.5, is_safe=is_safe)
    excluded = {(p["amp_left_mA"], p["amp_right_mA"]) for p in jc["excluded"]}
    assert (4.0, 4.0) in excluded
    assert (4.0, 4.0) not in {(p["amp_left_mA"], p["amp_right_mA"]) for p in jc["points"]}
    hit = [p for p in jc["excluded"] if (p["amp_left_mA"], p["amp_right_mA"]) == (4.0, 4.0)][0]
    assert "reason" in hit and "safe set" in hit["reason"]
    assert jc["n_points"] == 3 and jc["n_excluded"] == 1


def test_no_ceiling_on_either_side_uses_the_raw_levels():
    jc = TP.joint_corners(None, None)
    pts = {(p["amp_left_mA"], p["amp_right_mA"]) for p in jc["points"]}
    assert pts == {(1.0, 1.0), (4.0, 1.0), (1.0, 4.0), (4.0, 4.0)}


def test_plan_for_sides_offers_no_joint_corners_when_only_one_side_is_requested():
    margin = PR.margin_becomes_available(None)
    out = TP.plan_for_sides({"Left": _side()}, margin=margin)
    assert out["joint_corners"]["points"] == []
    assert "only one side was requested" in out["joint_corners"]["note"]
    assert all(r["block"] != "joint_corners" for r in out["sheet_rows"])


def test_plan_for_sides_offers_joint_corners_when_both_sides_are_requested():
    margin = PR.margin_becomes_available(None)
    out = TP.plan_for_sides({"Left": _side(), "Right": _side()}, margin=margin)
    assert len(out["joint_corners"]["points"]) == 4
    assert any(r["block"] == "joint_corners" for r in out["sheet_rows"])


# ---------------------------------------------------------------------------------------------
# the flat clinic-sheet rows
# ---------------------------------------------------------------------------------------------
def test_sheet_columns_match_the_template_workbooks_own_header_row():
    # Row 11, columns A-S, of the lab's template "Stim Testing" tab (read with openpyxl,
    # 2026-09-14); the export copies that template, so this is the header the rows must match.
    assert TP.SHEET_COLUMNS == (
        "Group", "Contacts", "sEEG Contacts", "Amp (mA)", "Rate (Hz)", "PW (µs)", "Threshold",
        "Duration (s)", "Side Effect?", "Timestamp", "Movement/Change point",
        "General Notes / Pt Verbal Notes", "Overall", "Head", "Back", "Left Leg", "Left Foot",
        "Right Leg", "Right Foot")


def _sides_for_sheet():
    margin = PR.margin_becomes_available(None)
    left = TP.side_plan("Left", margin=margin, held_other_side_mA=2.0,
                        held_other_side_source="the Right side", **_side(ceiling_mA=4.5))
    right = TP.side_plan("Right", margin=margin, held_other_side_mA=1.5,
                         held_other_side_source="the Left side",
                         **_side(rate_in_force_hz=55.0, pulse_width_us=150.0, ceiling_mA=4.5))
    return {"Left": left, "Right": right}


def test_build_sheet_rows_has_two_rows_per_step_and_the_bilateral_contacts_and_amps():
    sides = _sides_for_sheet()
    in_force = {"Left": {"contacts_short": "L C+2-", "pulse_width_us": 100.0},
               "Right": {"contacts_short": "R C+1-", "pulse_width_us": 150.0}}
    timing = TP.step_timing()
    jc = TP.joint_corners(4.5, 4.5)
    rows = TP.build_sheet_rows(sides, jc, in_force=in_force, timing=timing)
    n_left = sides["Left"]["ladder"]["n_steps"]
    n_right = sides["Right"]["ladder"]["n_steps"]
    n_joint = len(jc["points"])
    assert len(rows) == 2 * (n_left + n_right + n_joint)
    for r in rows:
        assert set(r) >= set(TP.SHEET_COLUMNS) | {"block", "step", "row_kind"}
    ramp_rows = [r for r in rows if r["row_kind"] == "ramp"]
    test_rows = [r for r in rows if r["row_kind"] == "test"]
    assert len(ramp_rows) == n_left + n_right + n_joint
    assert len(test_rows) == len(ramp_rows)
    # the ramp row carries Contacts/Amp/Rate/PW and the ramp duration; the test row carries only
    # the test duration (the PI's ruling, 2026-09-14)
    r0 = ramp_rows[0]
    assert r0["Contacts"] == "L C+2- / R C+1-"   # as the lab's 2026-09-16 visit sheet writes it
    assert r0["Amp (mA)"].startswith("L ") and " / R " in r0["Amp (mA)"]
    assert r0["Rate (Hz)"] == 55.0
    assert r0["PW (µs)"] == "L 100 / R 150"
    assert r0["Duration (s)"] == 60.0
    t0 = test_rows[0]
    assert t0["Contacts"] is None and t0["Amp (mA)"] is None and t0["Rate (Hz)"] is None
    assert t0["PW (µs)"] is None and t0["Duration (s)"] == 60.0
    assert t0["step"] == r0["step"] and "Stim Set" not in r0
    # blocks are named and steps number sequentially within a block
    blocks = [r["block"] for r in ramp_rows]
    assert blocks == (["left_ladder"] * n_left + ["right_ladder"] * n_right
                      + ["joint_corners"] * n_joint)
    left_steps = [r["step"] for r in ramp_rows if r["block"] == "left_ladder"]
    assert left_steps == list(range(1, n_left + 1))


def test_the_left_ladder_varies_left_and_holds_right_at_its_own_current():
    sides = _sides_for_sheet()
    in_force = {"Left": {"contacts_short": "L C+2-", "pulse_width_us": 100.0},
               "Right": {"contacts_short": "R C+1-", "pulse_width_us": 150.0}}
    timing = TP.step_timing()
    rows = TP.build_sheet_rows(sides, {"points": []}, in_force=in_force, timing=timing)
    left_ramp = [r for r in rows if r["block"] == "left_ladder" and r["row_kind"] == "ramp"]
    ladder_currents = sides["Left"]["ladder"]["steps_mA"]
    for r, cur in zip(left_ramp, ladder_currents):
        assert r["Amp (mA)"] == f"L {cur:g} / R 2"    # right held at 2.0 mA throughout


# ---------------------------------------------------------------------------------------------
# the service response carries the block for both sides
# ---------------------------------------------------------------------------------------------
def _matrix(n=8):
    rows = []
    for k in range(n):
        rows.append(dict(epoch=float(k + 1), freq_hz=55.0, pw_us_Left=100.0, pw_us_Right=150.0,
                         amp_mA_Left=1.0 + 0.5 * (k % 4), amp_mA_Right=1.5 + 0.5 * (k % 3),
                         cathode_Left="2a-2b-2c", cathode_Right="1a-1b-1c",
                         n=8.0, dur_h=200.0, state="bilateral_active",
                         left_leg_vas=50.0 + k, left_leg_vas_sd=8.0, back_vas=40.0 + k, back_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    d["t_end"] = d["t0"] + pd.Timedelta(days=2)
    return d


def _screen():
    return pd.DataFrame([
        dict(channel="ONE_THREE_LEFT", hemisphere="Left", rate_hz=55.0, n_bands=18, n_responding=12,
             responding_fraction=0.667, median_separation_d=0.9, laterality="ipsilateral",
             sensing_side="Left", deployable=True),
        dict(channel="ZERO_THREE_RIGHT", hemisphere="Right", rate_hz=55.0, n_bands=18, n_responding=4,
             responding_fraction=0.222, median_separation_d=0.3, laterality="ipsilateral",
             sensing_side="Right", deployable=False),
    ])


class _Arm:
    def __init__(self, hemi):
        self.site, self.hemisphere = "left_leg", hemi
        self.queue = pd.DataFrame({"rank": [1], "freq_hz": [55.0], "amp_mA": [2.0], "score": [0.3]})
        self.batch = self.queue.copy()
        self.meta = {"incumbent_mu": 0.4, "mu_star": -0.6, "sd_star": 0.9, "incumbent_sd": 0.9,
                     "x_star": [55.0, 2.0], "data_horizon": "h", "washin_min": 1.0,
                     "amp_col": f"amp_mA_{hemi}", "n_epochs_fitted": 8, "kernel": "rbf",
                     "safe_is_contiguous": True, "safe_contiguous_ceiling": float("nan")}
        self.ctx = types.SimpleNamespace(meta=self.meta)

    def surface_can_resolve_its_optimum(self, k=1.0):
        return False


class _Report:
    def __init__(self):
        self.arms = {"left_leg__Left": _Arm("Left"), "left_leg__Right": _Arm("Right")}
        self.summary = pd.DataFrame({"arm": list(self.arms), "n_epochs": [8, 8]})
        self.manifest = {"declared": "stub"}

    def recommendation_is_supported(self):
        return False


@pytest.fixture
def bench(monkeypatch):
    import importlib
    from StimOptimizer import adapter as AD
    from StimOptimizer import bravo_service as BS
    st = BS._cache_store
    _ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")
    root = tempfile.mkdtemp(prefix="bravo_so_titration_")
    monkeypatch.setattr(BS, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(_ledger, "ENABLED", False)
    monkeypatch.setattr(st, "ENABLED", True)
    models = types.ModuleType("Server.models")
    models.Participant = types.SimpleNamespace(find=lambda uid: types.SimpleNamespace(uid=uid))
    server = types.ModuleType("Server"); server.models = models
    monkeypatch.setitem(sys.modules, "Server", server)
    monkeypatch.setitem(sys.modules, "Server.models", models)
    stream = pd.DataFrame({"t": pd.to_datetime(["2026-01-01"], utc=True)})
    monkeypatch.setattr(AD, "settings_stream", lambda p, **kw: stream)
    es = _matrix()
    monkeypatch.setattr(AD, "build_design_matrix", lambda p, rd=None, **kw: es.copy())
    monkeypatch.setattr(AD, "evidence_inputs", lambda p, **kw: (None, None))
    monkeypatch.setattr(BS, "_tiles_key_for", lambda p: (None, "no tiles in this test"))
    monkeypatch.setattr(BS, "_blockers", lambda rep, arms, observed=None: [])
    monkeypatch.setattr(BS.pipeline, "run", lambda es, **kw: _Report())

    def readiness(p, es, include=True, inputs=None, screen_out=None, **kw):
        if screen_out is not None:
            screen_out["screen"] = _screen()
        return {"available": True, "ready": True, "verdict": "stubbed"}
    monkeypatch.setattr(BS, "closed_loop_readiness", readiness)
    yield types.SimpleNamespace(root=root, es=es, BS=BS)
    shutil.rmtree(root, ignore_errors=True)


def test_the_response_carries_a_titration_plan_for_both_sides_with_every_source_non_empty(bench):
    out = bench.BS.run_for_participant({"ParticipantId": "P", "Backend": "none",
                                        "Hemispheres": ["Left", "Right"]})
    assert out.get("available") is True, out.get("reason")
    tp = out["titration_plan"]
    assert tp["available"] is True
    assert set(tp["sides"]) == {"Left", "Right"}
    for side, p in tp["sides"].items():
        assert p["side"] == side
        assert p["rate_hz"] == 55.0 and p["rate_lifted"] is False
        assert p["pulse_width_us"] == (100.0 if side == "Left" else 150.0)   # each side's OWN column
        assert p["ceiling_mA"] == 5.0                                        # the module hard limit fallback
        assert "no PI-stated ceiling" in p["sources"]["ceiling_mA"]
        assert p["ladder"]["n_steps"] == 16 and p["hold"]["seconds"] == 60.0
        assert p["step_timing"]["total_s"] == 120.0
        # found 2026-09-25: 22.5-24.5 Hz are newly avoided too (the fifth multiple of 55 Hz folds
        # to 25 Hz, which harmonic_avoidance used to miss)
        assert p["bands"]["avoid_hz"] == [11.5, 12.5, 13.5, 14.5, 15.5, 22.5, 23.5, 24.5, 25.5, 26.5,
                                          27.5, 28.5, 29.5]
        for k, v in p["sources"].items():
            assert isinstance(v, str) and v.strip(), (side, k)
        assert "setting in force on the" in p["sources"]["rate_hz"]
        # the other side is held at its own current in force, read from the same matrix
        assert p["held_other_side"]["current_mA"] is not None
    # the Left side's best deployable cell; the Right side's cell did not pass and is named as such
    assert tp["sides"]["Left"]["sensing_contact"]["channel"] == "ONE_THREE_LEFT"
    assert tp["sides"]["Left"]["sensing_contact"]["n_responding"] == 12
    assert "best deployable cell" in tp["sides"]["Left"]["sources"]["sensing_contact"]
    assert "at the session's rate, 55 Hz" in tp["sides"]["Left"]["sources"]["sensing_contact"]
    assert tp["sides"]["Right"]["sensing_contact"]["channel"] == "ZERO_THREE_RIGHT"
    assert "did not pass" in tp["sides"]["Right"]["sensing_contact"]["note"] or \
        "no contact on this side passed" in tp["sides"]["Right"]["sensing_contact"]["note"]
    # no stored tables in the scratch root: said, not counted as zero
    assert tp["margin"]["table_stored"] is False and tp["margin"]["available"] is False
    assert "no entry is stored" in tp["stored_tables"]["pooled"] and "no entry is stored" in tp["stored_tables"]["run_points"]
    assert tp["sides"]["Left"]["yield"]["record_today"]["points"] is None
    # the joint corners and the flat sheet rows are both present
    assert tp["joint_corners"]["optional"] is True
    assert isinstance(tp["sheet_rows"], list) and len(tp["sheet_rows"]) > 0
    assert tp["sheet_columns"] == list(TP.SHEET_COLUMNS)
    n_left = tp["sides"]["Left"]["ladder"]["n_steps"]
    n_right = tp["sides"]["Right"]["ladder"]["n_steps"]
    n_joint = len(tp["joint_corners"]["points"])
    base_rows = [r for r in tp["sheet_rows"] if not str(r["block"]).startswith("exploratory")]
    assert len(base_rows) == 2 * (n_left + n_right + n_joint)
    assert tp["session_time"]["n_steps_total"] == n_left + n_right + n_joint
    # THE EXPLORATORY LADDER (2026-09-21): the Right side's best pair is R 0-3+, which needs
    # stimulation on rings 1 and 2, while the bench's Right side stimulates on ring 1 alone; the
    # Left side's best pair (L 1-3+) needs ring 2, which is in force, so no proposal there.
    assert set(tp["proposed"]) == {"Right"}
    pr = tp["proposed"]["Right"]
    assert pr["stimulation"]["contacts_short"] == "R C+1-2-" and pr["stimulation"]["in_force_rings"] == [1]
    assert pr["sensing_pair"]["channel"] == "ZERO_THREE_RIGHT" and pr["rate_hz"] == 55.0
    assert pr["first_exposure"]["ever_powered"] is False and "never" in pr["first_exposure"]["sentence"]
    assert pr["held_other_side"]["current_mA"] is not None
    expl = [r for r in tp["sheet_rows"] if str(r["block"]).startswith("exploratory_right")]
    assert len(expl) == 2 * pr["ladder"]["n_steps"] + 3
    assert expl[0]["Contacts"].endswith("/ R C+1-2-")
    assert tp["session_time"]["total_minutes"] > tp["session_time"]["steps_minutes"]
    # JSON-safe: no numpy scalars anywhere
    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        else:
            assert not isinstance(o, (np.generic,)), type(o)
    walk(tp)


def test_a_contact_that_passed_only_at_another_rate_is_named_with_that_rate(bench, monkeypatch):
    BS = bench.BS

    def readiness(p, es, include=True, inputs=None, screen_out=None, **kw):
        sc = _screen()
        sc.loc[sc["hemisphere"] == "Left", "rate_hz"] = 165.0
        if screen_out is not None:
            screen_out["screen"] = sc
        return {"available": True}
    monkeypatch.setattr(BS, "closed_loop_readiness", readiness)
    out = BS.run_for_participant({"ParticipantId": "P", "Backend": "none", "Hemispheres": ["Left"]})
    p = out["titration_plan"]["sides"]["Left"]
    assert p["rate_hz"] == 55.0
    assert p["sensing_contact"]["channel"] == "ONE_THREE_LEFT" and p["sensing_contact"]["rate_hz"] == 165.0
    assert "no cell on this side passed at the session's rate of 55 Hz" in p["sources"]["sensing_contact"]
    assert "from 165 Hz" in p["sources"]["sensing_contact"]


def test_the_plan_is_in_the_stored_response_and_a_readiness_failure_does_not_remove_it(bench, monkeypatch):
    BS = bench.BS
    monkeypatch.setattr(BS, "closed_loop_readiness",
                        lambda p, es, include=True, **kw: {"available": False, "reason": "stubbed off"})
    out = BS.run_for_participant({"ParticipantId": "P", "Backend": "none", "Hemispheres": ["Left"]})
    tp = out["titration_plan"]
    assert tp["available"] is True and set(tp["sides"]) == {"Left"}
    assert tp["sides"]["Left"]["sensing_contact"] is None
    assert "no sensing contact is named" in tp["sides"]["Left"]["sensing_contact_note"]
    assert tp["sides"]["Left"]["ladder"]["n_steps"] == 16
    # a single side means no joint corners rows in the flat sheet
    assert all(r["block"] != "joint_corners" for r in tp["sheet_rows"])


# ---------------------------------------------------------------------------------------------
# THE EXPLORATORY LADDER FOR A STIMULATION CONFIGURATION THE RECORD HAS NEVER POWERED
# (the PI, 2026-09-21: "create the titration ladder (left C positive, one minus, two minus) in a
# way that will be very helpful for deciding how the biomarker moves and its acute effect on
# pain"). The readiness screen's best left sensing pair is L 0-3+, which the device allows only
# while contacts 1 and 2 stimulate together (decision 217); on RCS08 that configuration was
# programmed for three months in 2025 at 0.0 mA and has never carried current.
# ---------------------------------------------------------------------------------------------
def _epochs_with_cathodes():
    """A small epoch table in the design matrix's own columns: contact 2 alone at several
    currents (today's configuration), contacts 1+2 together at 0 mA only (the 2025 record)."""
    rows = []
    t = pd.Timestamp("2025-07-18", tz="UTC")
    for k, (cath, amp, n) in enumerate([("1a-1b-1c-2a-2b-2c", 0.0, 40), ("1a-1b-1c-2a-2b-2c", 0.0, 62),
                                         ("2a-2b-2c", 1.6, 73), ("2a-2b-2c", 4.0, 43), ("2a-2b-2c", 3.5, 24),
                                         ("1a-2a", 1.0, 1)]):
        rows.append(dict(epoch=float(k), t0=t + pd.Timedelta(days=30 * k), dur_h=100.0 + k, freq_hz=55.0,
                         amp_mA_Left=amp, amp_mA_Right=2.5, pw_us_Left=100.0, pw_us_Right=150.0,
                         cathode_Left=cath, cathode_Right="1a-1b-1c-2a-2b-2c", n=n, left_leg_vas=50.0))
    return pd.DataFrame(rows)


def test_the_stimulating_rings_a_sensing_pair_requires_are_the_inverse_of_the_flanking_rule():
    assert TP.stim_rings_for_sensing_pair("ZERO_THREE_LEFT") == {1, 2}
    assert TP.stim_rings_for_sensing_pair("ZERO_TWO_LEFT") == {1}
    assert TP.stim_rings_for_sensing_pair("ONE_THREE_RIGHT") == {2}
    assert TP.stim_rings_for_sensing_pair("ZERO_ONE_LEFT") is None        # nothing sits between 0 and 1
    assert TP.stim_rings_for_sensing_pair("nonsense") is None
    from StimOptimizer.routines import lfp_evidence as LE
    for ch in ("ZERO_THREE_LEFT", "ZERO_TWO_LEFT", "ONE_THREE_LEFT"):
        assert LE.flanking_pair(TP.stim_rings_for_sensing_pair(ch)) == LE.sensing_pair_rings(ch)


def test_a_configurations_exposure_is_read_from_the_epoch_table_and_says_when_it_never_carried_current():
    es = _epochs_with_cathodes()
    ex = TP.configuration_exposure(es, "Left", {1, 2})
    # the two full-ring epochs at 0 mA, and one day on one segment of each ring at 1.0 mA (the
    # RCS08 record of 2025-11-12): counted, said separately, and not "powered"
    assert ex["epochs"] == 3 and ex["epochs_full_rings"] == 2 and ex["epochs_partial_rings"] == 1
    assert ex["reports"] == 103 and ex["hours"] == 306.0
    assert ex["amp_max_full_rings_mA"] == 0.0 and ex["amp_max_mA"] == 1.0 and ex["ever_powered"] is False
    assert ex["first"].startswith("2025-07-18") and ex["last"].startswith("2025-12-15")
    assert "never carried current" in ex["sentence"] and "0.0 mA" in ex["sentence"]
    assert "L C+1a-2a-" in ex["sentence"] and "1 mA" in ex["sentence"]
    ex2 = TP.configuration_exposure(es, "Left", {2})
    assert ex2["epochs"] == 3 and ex2["amp_max_mA"] == 4.0 and ex2["ever_powered"] is True
    assert TP.configuration_exposure(es, "Left", {3})["epochs"] == 0
    assert TP.configuration_exposure(None, "Left", {1, 2})["epochs"] == 0


def test_the_acute_pain_holds_are_off_on_off_with_a_rating_every_minute_and_the_patient_blind():
    h = TP.acute_pain_holds(3.5)
    assert [x["current_mA"] for x in h["holds"]] == [0.0, 3.5, 0.0]
    assert [x["state"] for x in h["holds"]] == ["off", "on", "off"]
    assert all(x["minutes"] == 5.0 for x in h["holds"]) and h["rating_every_minutes"] == 1.0
    assert h["ratings_per_hold"] == 5 and h["total_minutes"] == 15.0
    assert h["blind"] is True and "blind" in h["why"].lower()
    assert "top current the patient tolerated" in h["why"]
    assert TP.acute_pain_holds(None)["holds"] == []


def test_the_configuration_plan_names_the_contacts_the_pair_the_rate_in_force_and_the_stop_rule():
    es = _epochs_with_cathodes()
    contact = {"channel": "ZERO_THREE_LEFT", "display_short": "L 0⁻3⁺", "rate_hz": 125.0,
               "qualifying_centers_hz": [24.5, 25.5, 26.5, 27.5], "n_qualifying": 4, "n_bands": 18,
               "n_responding": 0, "deployable": False}
    p = TP.configuration_plan("Left", rings={1, 2}, contact=contact, rate_source="the readiness screen's cell",
                              pulse_width_us=100.0, pulse_width_source="in force", ceiling_mA=4.5,
                              ceiling_source="the PI", exposure=TP.configuration_exposure(es, "Left", {1, 2}),
                              held_other_side_mA=2.5, held_other_side_source="the Right side in force",
                              in_force_rings={2}, other_side_contacts="R C+1-2-", other_side_pw=150.0,
                              rate_in_force_hz=55.0)
    assert p["stimulation"]["contacts_short"] == "L C+1-2-"
    assert p["rate_in_force_hz"] == 55.0
    # the condition a clinician reads: the session's rate is the one in force, the bands were found
    # at another rate, and the bands that land on a harmonic at this rate are named there too
    _rate_cond = next(c for c in p["conditions"] if c.startswith("rate "))
    assert _rate_cond.startswith("rate 55 Hz, the rate in force")
    assert "found at 125 Hz" in _rate_cond
    # FOUND 2026-09-25: harmonic_avoidance used to fold only |250 - rate| and missed the fifth
    # multiple of 55 Hz (275 Hz, folding to 25 Hz), which sits close enough to pull 24.5 Hz onto a
    # harmonic too -- the band this test, and decision 236, once called "the one clean band to
    # watch." With the fix ALL FOUR watched bands land on a harmonic; none is clear.
    assert "24.5, 25.5, 26.5 and 27.5 Hz" in _rate_cond and "leaving none of them clear" in _rate_cond
    assert p["stimulation"]["rings"] == [1, 2] and p["stimulation"]["in_force_rings"] == [2]
    assert p["stimulation"]["differs_from_in_force"] is True
    assert p["sensing_pair"]["channel"] == "ZERO_THREE_LEFT" and "flank" in p["sensing_pair"]["why"]
    # THE RATE IS THE ONE IN FORCE (the PI, 2026-09-22, ruling 3; decision 233), not the rate of the
    # cell where the bands were found. The cell's rate is reported beside it so the difference is
    # visible: the bands were found at 125 Hz and the session runs at 55 Hz.
    assert p["rate_hz"] == 55.0 and "in force" in p["sources"]["rate_hz"]
    assert p["cell_rate_hz"] == 125.0
    # The consequence, stated and never hidden (decision 220: a warning, never a refusal). At 55 Hz
    # a band is 5 Hz wide and the fixed harmonic-landing computation now places TWO landings inside
    # the watched range -- the fifth multiple of the rate (folded to 25 Hz) and half the rate
    # (27.5 Hz) -- between them covering all four watched bands, 24.5 through 27.5 Hz.
    assert p["bands"]["watch_hz"] == [24.5, 25.5, 26.5, 27.5]
    assert p["bands"]["watch_clear"] is False
    assert p["bands"]["watch_on_harmonic_hz"] == [24.5, 25.5, 26.5, 27.5]
    assert p["bands"]["watch_clear_hz"] == []
    assert 24.5 not in p["bands"]["clear_hz"]
    why = p["bands"]["watch_why"]
    assert "27.5 Hz (half the rate)" in why and "26.5 and 27.5 Hz" in why
    assert "25 Hz (the fifth multiple of the rate folded by the device's 250 Hz sampling)" in why
    assert "24.5 and 25.5 Hz" in why
    assert "none of the watched bands is clear" in why
    assert "measures the stimulator" not in why and "measuring the stimulator" not in why
    # first exposure: 0 mA only in the record -> the stop rule is printed and the ladder starts at 0
    assert p["first_exposure"]["ever_powered"] is False
    assert "side-effect score of 2" in p["first_exposure"]["stop_rule"]
    assert p["ladder"]["steps_mA"][0] == 0.0 and p["ladder"]["top_mA"] == 4.5
    # the acute holds use the ladder's top as the planned "on" current, to be replaced by the top
    # tolerated current on the day
    assert [x["current_mA"] for x in p["acute_pain_holds"]["holds"]] == [0.0, 4.5, 0.0]
    # rows for the sheet: the ladder's two rows per step, then one row per hold, all L C+1-2-
    rows = p["sheet_rows"]
    lad_rows = [r for r in rows if r["block"] == "exploratory_left_ladder"]
    hold_rows = [r for r in rows if r["block"] == "exploratory_left_holds"]
    assert len(lad_rows) == 2 * p["ladder"]["n_steps"] and len(hold_rows) == 3
    assert lad_rows[0]["Contacts"] == "L C+1-2- / R C+1-2-" and lad_rows[0]["Rate (Hz)"] == 55.0
    assert lad_rows[0]["Amp (mA)"] == "L 0 / R 2.5"
    assert hold_rows[1]["Amp (mA)"] == "L 4.5 / R 2.5" and hold_rows[1]["Duration (s)"] == 300.0
    assert hold_rows[1]["General Notes / Pt Verbal Notes"] and "every minute" in hold_rows[1]["General Notes / Pt Verbal Notes"]
    assert p["session_time"]["total_minutes"] > p["session_time"]["steps_minutes"]
    assert any("blind" in c.lower() for c in p["conditions"])
    for k, v in p["sources"].items():
        assert isinstance(v, str) and v, k


def test_plan_for_sides_carries_the_proposed_ladder_and_its_rows_after_the_others():
    margin = PR.margin_becomes_available(None)
    es = _epochs_with_cathodes()
    contact = {"channel": "ZERO_THREE_LEFT", "display_short": "L 0⁻3⁺", "rate_hz": 125.0,
               "qualifying_centers_hz": [24.5], "n_qualifying": 1, "n_bands": 18, "n_responding": 0, "deployable": False}
    proposed = {"Left": dict(rings={1, 2}, contact=contact, rate_source="cell", pulse_width_us=100.0,
                             pulse_width_source="in force", ceiling_mA=4.5, ceiling_source="the PI",
                             exposure=TP.configuration_exposure(es, "Left", {1, 2}), held_other_side_mA=2.5,
                             held_other_side_source="the Right side", in_force_rings={2})}
    in_force = {"Left": {"contacts_short": "L C+2-", "pulse_width_us": 100.0},
                "Right": {"contacts_short": "R C+1-2-", "pulse_width_us": 150.0}}
    out = TP.plan_for_sides({"Left": _side(), "Right": _side()}, margin=margin, in_force=in_force, proposed=proposed)
    assert set(out["proposed"]) == {"Left"}
    assert out["proposed"]["Left"]["stimulation"]["contacts_short"] == "L C+1-2-"
    blocks = [r["block"] for r in out["sheet_rows"]]
    assert blocks.index("exploratory_left_ladder") > blocks.index("joint_corners")
    assert blocks[-1] == "exploratory_left_holds"
    # the proposed rows number on from the last step of the others
    steps = [r["step"] for r in out["sheet_rows"] if r["row_kind"] == "ramp"]
    assert steps == sorted(steps) and len(set(steps)) == len(steps)
    # without a proposal nothing changes in the flat rows
    out0 = TP.plan_for_sides({"Left": _side(), "Right": _side()}, margin=margin, in_force=in_force)
    assert out0["proposed"] == {} and not any(r["block"].startswith("exploratory") for r in out0["sheet_rows"])
