"""Independent synthetic contracts for threshold comparison labels.

A fictional minimal device export tests active-group selection, each stimulation side's
own current limits and an explicitly ganged sensing signal. Other hand-built inputs test
daytime percentiles, exhaustive state shares, earlier-only fitting, unrounded device-bin
schedules and the neutral setting. No fixture is copied from a participant export.
"""
import copy
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import threshold_comparison as TC


def _entry(side, channel, signal, centre, upper, lower, lo_mA, up_mA, *, ganged=None, status="RUNNING",
           mode="AdaptiveModeDef.DUAL_THRESHOLD_DIRECT", averaging=3000):
    e = {"HemisphereLocation": f"HemisphereLocationDef.{side}",
         "Channel": f"SensingElectrodeConfigDef.{channel}",
         "UpperLfpThreshold": upper, "LowerLfpThreshold": lower,
         "AdaptiveTherapyStatus": f"ADBSStatusDef.{status}",
         "TransitionUpInMilliSeconds": 6000, "TransitionDownInMilliSeconds": 9000,
         "UpperLimitInMilliAmps": up_mA, "LowerLimitInMilliAmps": lo_mA,
         "SensingSetup": {"FrequencyInHertz": centre, "AveragingDurationInMilliSeconds": averaging,
                          "ChannelSignalResult": {"Channel": f"SensingChannelDef.{signal}"}},
         "AdaptiveTherapy": {"UpperThresholdOnsetInMilliSeconds": 4000, "LowerThresholdOnsetInMilliSeconds": 5000,
                             "DetectionBlankingDurationInMilliSeconds": 7000,
                             "AdaptiveStartupDelayInMilliSeconds": 8000}}
    if mode:
        e["Mode"] = mode
    if ganged:
        e["GangedToHemisphere"] = f"HemisphereLocationDef.{ganged}"
    return e


# Fictional inputs authored from programmed_adaptive's field contract, with no source export.
EXPORT = {
    "SessionDate": "2024-02-01T12:00:00Z", "SessionEndDate": "2024-02-01T12:10:00Z",
    "Groups": {"Initial": [], "Final": [
        {"GroupId": "GroupIdDef.GROUP_C", "ActiveGroup": False, "ProgramSettings": {"SensingChannel": [
            _entry("Left", "ONE_AND_THREE", "ONE_THREE_LEFT", 11.72, 30.0, 20.0, 0.0, 4.0, status="NOT_CONFIGURED",
                   mode=None, averaging=3000)]}},
        {"GroupId": "GroupIdDef.GROUP_B", "ActiveGroup": True, "ProgramSettings": {"SensingChannel": [
            _entry("Left", "ZERO_AND_TWO", "ZERO_TWO_LEFT", 29.30, 380.0, 240.0, 0.5, 2.0),
            _entry("Right", "ZERO_AND_TWO", "ZERO_TWO_LEFT", 29.30, 380.0, 240.0, 1.0, 3.5, ganged="Left")]}},
    ]},
}


def test_the_programmed_thresholds_are_read_from_the_active_group_of_the_export():
    p = TC.programmed_adaptive(copy.deepcopy(EXPORT))
    assert p["available"] is True and p["group"] == "GROUP_B"
    assert p["session_end"] == "2024-02-01T12:10:00Z"
    L, R = p["sides"]["Left"], p["sides"]["Right"]
    assert (L["upper"], L["lower"], L["centre_hz"]) == (380.0, 240.0, 29.30)
    assert L["signal_pair"] == "ZERO_TWO_LEFT" and L["ganged_to"] is None
    assert (L["mode"], L["status"]) == ("DUAL_THRESHOLD_DIRECT", "RUNNING")
    assert (L["averaging_ms"], L["onset_upper_ms"], L["onset_lower_ms"]) == (3000.0, 4000.0, 5000.0)
    assert (L["blanking_ms"], L["startup_delay_ms"]) == (7000.0, 8000.0)
    assert (L["transition_up_ms"], L["transition_down_ms"]) == (6000.0, 9000.0)
    assert (L["lower_limit_mA"], L["upper_limit_mA"]) == (0.5, 2.0)
    # the right stimulator is driven by the LEFT lead's signal (ganged), with its own current limits
    assert R["signal_pair"] == "ZERO_TWO_LEFT" and R["ganged_to"] == "Left"
    assert (R["upper"], R["lower"], R["lower_limit_mA"], R["upper_limit_mA"]) == (380.0, 240.0, 1.0, 3.5)
    # the inactive group's placeholder pair (30 / 20) is never read
    assert all(s["upper"] != 30.0 for s in p["sides"].values())


def test_no_active_group_with_sensing_is_said_not_invented():
    d = copy.deepcopy(EXPORT)
    for g in d["Groups"]["Final"]:
        g["ActiveGroup"] = False
    p = TC.programmed_adaptive(d)
    assert p["available"] is False and p["sides"] == {} and "no active group" in p["reason"]
    assert TC.programmed_adaptive(None)["available"] is False


def _utc(local_strings):
    """Seconds since 1970 (UTC) of California wall-clock times."""
    return (pd.to_datetime(local_strings).tz_localize(TC.TZ).tz_convert("UTC").astype("int64") / 1e9).to_numpy()


def test_the_manufacturer_percentiles_use_daytime_readings_only_and_match_a_hand_calculation():
    day = ["2024-02-20 07:00", "2024-02-20 09:30", "2024-02-20 12:00", "2024-02-20 15:00", "2024-02-20 19:50"]
    night = ["2024-02-20 06:59", "2024-02-20 20:00", "2024-02-21 02:00"]
    t = _utc(day + night)
    y = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 9000.0, 9000.0, 9000.0])
    g = TC.percentile_pair(t, y)
    # five daytime values 10..50: the 25th percentile sits at position 0.25 x 4 = 1 -> 20, the 75th
    # at position 3 -> 40 (linear interpolation, numpy's default); the night readings are left out
    assert (g["lower"], g["upper"], g["n_day_readings"]) == (20.0, 40.0, 5)
    # a value between order statistics: 6 daytime values 1..6 -> 25th at 1.25 -> 2.25, 75th at 3.75 -> 4.75
    t6 = _utc([f"2024-02-20 {h:02d}:00" for h in (8, 9, 10, 11, 12, 13)])
    g6 = TC.percentile_pair(t6, np.arange(1.0, 7.0))
    assert g6["lower"] == pytest.approx(2.25, abs=1e-12) and g6["upper"] == pytest.approx(4.75, abs=1e-12)
    assert TC.percentile_pair(_utc(night), np.array([1.0, 2.0, 3.0]))["upper"] is None


@pytest.mark.parametrize("upper,lower", [(380.0, 240.0), (220.0, 180.0), (100.0, 100.0), (50.0, -40.0)])
def test_the_three_state_shares_add_to_the_whole(upper, lower):
    rng = np.random.default_rng(3)
    y = np.concatenate([rng.gamma(2.0, 150.0, 997), [upper, lower, upper]])   # values ON a threshold too
    s = TC.state_shares(y, upper, lower)
    assert s["n_above"] + s["n_between"] + s["n_below"] == s["n"] == 1000
    assert s["above"] + s["between"] + s["below"] == pytest.approx(1.0, abs=1e-12)
    # a value equal to a threshold is not past it: it counts as between
    assert s["n_above"] == int(np.sum(y > upper)) and s["n_below"] == int(np.sum(y < lower))
    t = _utc(pd.date_range("2024-02-20 00:00", periods=1000, freq="10min").strftime("%Y-%m-%d %H:%M"))
    for part in TC.period_shares(t, y, upper, lower).values():
        assert part["n_above"] + part["n_between"] + part["n_below"] == part["n"]
    assert sum(TC.period_shares(t, y, upper, lower)[k]["n"] for k in ("day", "night")) == 1000


def _home_and_reports(n_days=20, seed=1):
    """A home log every 10 minutes and one pain report a day at 10:05 local, each covered by the
    10:00 reading."""
    rng = np.random.default_rng(seed)
    t = _utc(pd.date_range("2024-02-01 00:00", periods=n_days * 144, freq="10min").strftime("%Y-%m-%d %H:%M"))
    y = rng.gamma(2.0, 150.0, t.size)
    rt = _utc([f"2024-02-{d:02d} 10:05" for d in range(1, n_days + 1)])
    ry = rng.integers(0, 100, rt.size).astype(float)
    return t, y, rt, ry


def test_the_fitted_candidate_never_uses_a_later_report_or_a_later_home_reading():
    t, y, rt, ry = _home_and_reports()
    fit = TC.fit_upper_on_earlier(rt, ry, t, y)
    assert fit["available"] is True and (fit["n_fit"], fit["n_held_out"]) == (14, 6)
    cut = fit["cut_s"]
    later_r = rt > cut
    later_h = t > cut
    ry2, y2 = ry.copy(), y.copy()
    ry2[later_r] = 100.0 - ry2[later_r] + 7.0           # every later pain report changed
    y2[later_h] = y2[later_h] * 50.0 + 1.0              # every later home reading changed
    fit2 = TC.fit_upper_on_earlier(rt, ry2, t, y2)
    for k in ("cut_s", "upper", "lower", "percentile", "fit_difference", "n_fit", "n_held_out"):
        assert fit2[k] == fit[k], k
    assert fit2["grid"] == fit["grid"]
    # ... and the held-out reading is the later reports' own (it moved)
    assert fit2["held_out"] != fit["held_out"]
    # an EARLIER report does move the fit (the test can fail)
    ry3 = ry.copy()
    ry3[~later_r] = ry3[~later_r][::-1]
    assert TC.fit_upper_on_earlier(rt, ry3, t, y)["grid"] != fit["grid"]


def test_home_readings_are_chosen_by_the_devices_own_frequency_not_the_clamped_label():
    """Two fictional sensing periods share an old clamped display label. Native device-bin
    schedules must still select each period independently, without pooling their readings."""
    t = np.arange(0.0, 20 * 600.0, 600.0) + 1.79e9
    switch = t[10]
    samples = {"ZERO_TWO_LEFT": {"t": t, "y": np.arange(20.0), "freq_hz": np.full(20, 26.4)}}
    sched = {"Left": [(0.0, 28.32), (switch, 29.30)], "Right": []}
    t27, y27, f27 = TC.home_at_band(samples, sched, "ZERO_TWO_LEFT", 29.5)
    t26, y26, f26 = TC.home_at_band(samples, sched, "ZERO_TWO_LEFT", 28.5)
    assert f27 == 29.30 and list(y27) == list(np.arange(10.0, 20.0))
    assert f26 == 28.32 and list(y26) == list(np.arange(10.0))
    assert TC.home_at_band(samples, sched, "ZERO_TWO_LEFT", 15.5)[2] is None
    assert TC.home_at_band(samples, sched, "ZERO_TWO_RIGHT", 29.5)[2] is None


def test_the_schedule_is_read_unrounded_from_the_chronic_recordings_by_lead():
    recs = [{"ChannelNames": ["LeftHemisphere ZERO_TWO"], "FreqScheduleHz": [[0, 28.32], [100, 29.30]]},
            {"ChannelNames": ["LeftHemisphere ZERO_TWO"], "FreqScheduleHz": [[0, 28.32], [100, 29.30]]},
            {"ChannelNames": ["RightHemisphere ZERO_TWO"], "FreqScheduleHz": [[0, 11.72], [200, 29.30]]}]
    s = TC.frequency_schedules(recs)
    assert s == {"Left": [(0.0, 28.32), (100.0, 29.30)], "Right": [(0.0, 11.72), (200.0, 29.30)]}
    assert list(TC.frequency_at([-1, 0, 99, 100, 500], s["Left"])[1:]) == [28.32, 28.32, 29.30, 29.30]
    assert np.isnan(TC.frequency_at([-1], s["Left"])[0])


def test_pain_by_state_takes_the_covering_reading_and_reports_the_difference():
    base = 1.79e9
    t = base + np.arange(6) * 600.0
    y = np.array([500.0, 500.0, 500.0, 100.0, 100.0, 100.0])           # above, above, above, below x3
    rt = t + 300.0                                                   # each inside its reading's 10 min
    ry = np.array([60.0, 70.0, 80.0, 10.0, 20.0, 30.0])
    p = TC.pain_by_state(rt, ry, t, y, 380.0, 240.0)
    assert p["n_reports"] == 6
    assert p["by_state"]["above"]["n"] == 3 and p["by_state"]["above"]["median"] == 70.0
    assert p["by_state"]["below"]["n"] == 3 and p["by_state"]["below"]["median"] == 20.0
    assert p["by_state"]["between"]["n"] == 0
    assert p["difference"]["value"] == 50.0 and (p["difference"]["n_above"], p["difference"]["n_rest"]) == (3, 3)
    # rotations by 1..5 give +40, -40, -50, +40, -40: one as large as +50 (the shift by 3) -> p = 2 / 6
    assert p["difference"]["p_rotation"] == pytest.approx(2 / 6) and p["difference"]["n_rotations"] == 5
    # a report in a gap of the log (more than 10 minutes after the last reading starts) has none
    assert TC.pain_by_state(np.array([t[-1] + 601.0]), np.array([5.0]), t, y, 380.0, 240.0)["n_reports"] == 0


def test_the_time_held_high_follows_the_dual_rule():
    y = np.array([300.0, 400.0, 300.0, 200.0, 300.0, 400.0])          # between, above, between, below, between, above
    st = TC.hysteresis_states(y, 380.0, 240.0)
    assert list(st) == [0, 1, 1, -1, -1, 1]


def test_the_design_rule_rate_is_read_at_the_largest_separation_no_wider_than_the_half_gap():
    table = [{"averaging_s": 3.0, "onset_s": 3.0, "min_separation": None,
              "sweep": [{"separation": 5.0, "total_per_hour": 597.0}, {"separation": 60.0, "total_per_hour": 590.0},
                        {"separation": 300.0, "total_per_hour": 570.0}]},
             {"averaging_s": 3.0, "onset_s": 30.0, "min_separation": 15.0,
              "sweep": [{"separation": 5.0, "total_per_hour": 1.2}, {"separation": 15.0, "total_per_hour": 0.9}]}]
    r = TC.design_rate(table, 380.0, 240.0, averaging_ms=1200, onset_ms=1200)
    assert (r["half_gap"], r["at_separation"], r["crossings_per_hour_at_most"]) == (70.0, 60.0, 590.0)
    assert r["meets_rule"] is False and r["timing_exact"] is False
    r30 = TC.design_rate(table, 220.0, 180.0, averaging_ms=3000, onset_ms=30000)
    assert r30["meets_rule"] is True and r30["crossings_per_hour_at_most"] == 0.9
    assert TC.design_rate(None, 1.0, 0.0, averaging_ms=1, onset_ms=1)["applies"] is False


def test_flags_below_zero_and_outside_the_home_range():
    assert TC.flags(200.0, -40.0, (50.0, 2500.0)) == ["lower threshold below zero",
                                                        "outside the home range (50-2500)"]
    assert TC.flags(380.0, 240.0, (50.0, 2500.0)) == []


def _svc():
    try:
        from modules.ClosedLoopDeployment import bravo_service as svc
    except ImportError:                                               # pragma: no cover
        from ClosedLoopDeployment import bravo_service as svc
    return svc


def test_neutral_returns_the_report_untouched_field_for_field(monkeypatch):
    svc = _svc()
    report = {"available": True, "verdict": "blocked", "threshold": {"upper": 220.0, "lower": 180.0},
              "pain_score": {"key": "left_leg_vas", "label": "Left Leg VAS"}}
    before = copy.deepcopy(report)
    req = {"ParticipantId": "p1", "Candidates": [{"channel": "ZERO_TWO_LEFT", "center_hz": 29.5}]}
    monkeypatch.setattr(TC, "ENABLED", False)
    try:
        import modules.ClosedLoopDeployment.threshold_comparison as TC2   # the container spelling
        monkeypatch.setattr(TC2, "ENABLED", False)
    except ImportError:
        pass
    out = svc._with_threshold_comparison(report, req)
    assert out is report and out == before
    # on: the same fields plus the one block, nothing else touched
    monkeypatch.setattr(TC, "ENABLED", True)
    try:
        import modules.ClosedLoopDeployment.threshold_comparison as TC2
        monkeypatch.setattr(TC2, "ENABLED", True)
    except ImportError:
        pass
    monkeypatch.setattr(svc, "_threshold_comparison", lambda rd, rep: {"available": True, "rows": []})
    on = svc._with_threshold_comparison(report, req)
    assert set(on) - set(before) == {"threshold_comparison"}
    assert {k: on[k] for k in before} == before and report == before
    # the grid alone (no band), an unavailable report: never a block
    assert svc._with_threshold_comparison(report, {"ParticipantId": "p1", "Candidates": []}) is report
    off = {"available": False, "reason": "x"}
    assert svc._with_threshold_comparison(off, req) is off


def test_the_neutral_setting_is_read_from_the_environment():
    code = "from ClosedLoopDeployment import threshold_comparison as T; print(T.ENABLED)"
    import os
    env = dict(os.environ, BRAVO_THRESHOLD_COMPARISON="0")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert out.stdout.strip() == "False", out.stderr
