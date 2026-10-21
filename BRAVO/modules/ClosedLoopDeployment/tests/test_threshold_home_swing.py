"""The home swing beside the threshold pair: a WARNING ONLY (wave 2, C7; the PI, 2026-10-20: "Keep
thresholds, warn").

Both threshold pairs (decision 180's record pair and the tablet's capture pair) are set from clinic
recordings only, on the calibrated LSB scale, and the ruling keeps them so; no home-record (chronic
log) value enters any threshold number. What the pair carries is `home_swing` -- how many fold the
home record's hourly medians swing across the day at the band (C6's profile), a ratio within that
one product, so no conversion is involved -- and a plain warning
appended to the threshold rows' reasons. These tests build the inputs by hand and check the values:
the warning at a 2-fold swing and not on a flat one, the no-home-record text, the pair and every
number on it unchanged with and without the block, and the neutral setting reproducing the old
answer field for field.
"""
import dataclasses
import subprocess
import sys

import numpy as np
import pytest

from ClosedLoopDeployment import threshold_placement as TPL
from ClosedLoopDeployment import prescription as PRESC
from ClosedLoopDeployment.types import ThresholdPlan
from Biomarkers.routines import daily_swing as DS

PAIR = "ZERO_THREE_RIGHT"
CAND = {"channel": PAIR, "center_hz": 9.5, "band_width_hz": 5.0}


def _samples(level_by_local_hour, *, freq_hz=9.77, days=6, pair=PAIR):
    """A chronic log on ``pair`` at ``freq_hz``: one reading every 10 minutes for ``days`` days,
    each reading the value its California local hour is given."""
    t = 1_760_000_000.0 + 600.0 * np.arange(days * 144)
    h = DS.local_hours(t)
    y = np.asarray([level_by_local_hour(int(x)) for x in h], dtype=float)
    return {pair: {"t": t, "y": y, "freq_hz": np.full(t.size, float(freq_hz))}}


def _two_fold(hour):
    return 200.0 if hour < 6 else 100.0          # highest 00:00, lowest 06:00, 2.0-fold


def _record_plan():
    cap = ThresholdPlan(upper=598.84, lower=338.0, capture_amp_low=1.4, capture_amp_high=4.8,
                        warnings=["D26 inverted capture: not assessed"], note="capture")
    pl = TPL.record_pair(median=480.22, design_rows=[{"averaging_s": 3.0, "onset_s": 30.0,
                                                      "min_separation": 160.0}],
                         averaging_ms=3000, onset_ms=30000)
    return TPL.apply(cap, pl, observed_series=np.linspace(200.0, 800.0, 101)), pl


# --- the warning -------------------------------------------------------------------------------
def test_a_two_fold_home_swing_gives_the_warning_with_its_hours():
    b = TPL.home_swing_block(_samples(_two_fold), PAIR, 9.5)
    assert b["status"] == DS.STATUS_MEASURED and b["chronic_freq_hz"] == 9.77
    assert b["ratio"] == pytest.approx(2.0) and b["hour_high"] == 0 and b["hour_low"] == 6
    assert b["n_readings"] == 6 * 144 and b["n_days"] >= 6
    assert b["thresholds_from"] == "clinic recordings only"
    assert b["warn_at_ratio"] == DS.SWING_WARN_RATIO          # C6's constant, imported
    assert b["warning"] == ("Home power at this band swings 2.0-fold across the day (lowest 06:00, "
                            "highest 00:00); these thresholds were set from clinic recordings "
                            "only, so the device may cross them from the time of day alone.")


def test_a_flat_home_profile_gives_no_warning():
    b = TPL.home_swing_block(_samples(lambda h: 150.0), PAIR, 9.5)
    assert b["status"] == DS.STATUS_MEASURED and b["ratio"] == pytest.approx(1.0)
    assert b["warning"] is None and b["thresholds_from"] == "clinic recordings only"


def test_the_block_holds_a_ratio_and_counts_never_a_home_record_value():
    b = TPL.home_swing_block(_samples(_two_fold), PAIR, 9.5)
    assert "hourly_median" not in b and "median" not in b and "level" not in b
    for k in ("ratio", "hour_low", "hour_high", "n_readings", "n_days", "status",
              "thresholds_from", "warning"):
        assert k in b


# --- no home record ----------------------------------------------------------------------------
NO_HOME = "No home record at this band; these thresholds were set from clinic recordings only."


def test_no_home_record_on_the_pair_says_so():
    b = TPL.home_swing_block(_samples(_two_fold, pair="ONE_THREE_LEFT"), PAIR, 9.5)
    assert b["status"] == DS.STATUS_NO_HOME_RECORD and b["ratio"] is None
    assert b["warning"] == NO_HOME


def test_a_home_frequency_half_a_hertz_or_more_away_is_not_this_band():
    b = TPL.home_swing_block(_samples(_two_fold, freq_hz=10.2), PAIR, 9.5)   # 0.7 Hz away
    assert b["status"] == DS.STATUS_NO_HOME_RECORD and b["warning"] == NO_HOME


def test_an_unreadable_home_record_says_so_and_names_the_reason():
    b = TPL.home_swing_block(None, PAIR, 9.5, reason="the home record could not be read: boom")
    assert b["status"] == TPL.HOME_STATUS_UNREADABLE and "boom" in b["reason"]
    assert b["warning"] == ("The home record could not be read; these thresholds were set from "
                            "clinic recordings only.")


# --- nothing that decides moves ------------------------------------------------------------------
def _numbers(plan):
    return {f.name: getattr(plan, f.name) for f in dataclasses.fields(plan)
            if f.name not in ("placement", "placement_note")}


def test_the_pair_and_every_number_on_it_are_the_same_with_and_without_the_block():
    plan, pl = _record_plan()
    block = TPL.home_swing_block(_samples(_two_fold), PAIR, 9.5)
    plan2, pl2 = TPL.with_home_swing(plan, pl, block)
    assert _numbers(plan2) == _numbers(plan)
    assert plan2.upper == pytest.approx(640.22) and plan2.lower == pytest.approx(320.22)
    assert {k: v for k, v in pl2.items() if k != "home_swing"} == pl
    assert {k: v for k, v in plan2.placement.items() if k != "home_swing"} == plan.placement
    assert plan2.placement_note == plan.placement_note + ". " + block["warning"]


def test_the_threshold_rows_keep_their_values_and_gain_only_the_warning():
    plan, pl = _record_plan()
    block = TPL.home_swing_block(_samples(_two_fold), PAIR, 9.5)
    plan2, _ = TPL.with_home_swing(plan, pl, block)
    for mode in ("dual", "single"):
        a = {f.name: f for f in PRESC.prescribe(mode=mode, threshold_plan=plan, candidate=CAND).fields}
        b = {f.name: f for f in PRESC.prescribe(mode=mode, threshold_plan=plan2, candidate=CAND).fields}
        assert list(a) == list(b)
        for name in a:
            fa, fb = dataclasses.asdict(a[name]), dataclasses.asdict(b[name])
            if "threshold" in name.lower() and "LFP" in name:
                assert fb["why"] == fa["why"] + " " + block["warning"], name
                fa.pop("why"), fb.pop("why")
            assert fa == fb, name


def test_the_capture_pair_rows_also_carry_the_warning():
    cap = ThresholdPlan(upper=196.13, lower=190.89, capture_amp_low=1.4, capture_amp_high=4.8)
    cap = TPL.apply(cap, {"available": False, "reason": "no design table"})
    block = TPL.home_swing_block(_samples(_two_fold, pair="ONE_THREE_LEFT"), PAIR, 9.5)
    cap2, _ = TPL.with_home_swing(cap, {"available": False}, block)
    up = next(f for f in PRESC.prescribe(mode="dual", threshold_plan=cap2, candidate=CAND).fields
              if f.name == "Upper LFP threshold")
    assert up.value == 196.13 and up.why.endswith(NO_HOME)


def test_the_report_step_adds_the_block_and_moves_nothing(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    plan, pl = _record_plan()
    monkeypatch.setattr(AD, "_place_thresholds_core", lambda *a, **k: (plan, dict(pl)))
    monkeypatch.setattr(AD, "_home_chronic_samples", lambda uid, loaded=None: _samples(_two_fold))
    monkeypatch.setattr(TPL, "HOME_SWING", True)
    plan2, pl2 = AD._place_thresholds_from_record("uid", object(), [dict(CAND)], hemisphere="Right")
    assert _numbers(plan2) == _numbers(plan)
    assert pl2["home_swing"]["ratio"] == pytest.approx(2.0)
    assert plan2.placement["home_swing"] == pl2["home_swing"]


def test_a_failing_home_record_read_never_moves_the_pair(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    plan, pl = _record_plan()
    monkeypatch.setattr(AD, "_place_thresholds_core", lambda *a, **k: (plan, dict(pl)))

    def _boom(uid, loaded=None):
        raise RuntimeError("no database")
    monkeypatch.setattr(AD, "_home_chronic_samples", _boom)
    monkeypatch.setattr(TPL, "HOME_SWING", True)
    plan2, pl2 = AD._place_thresholds_from_record("uid", object(), [dict(CAND)], hemisphere="Right")
    assert _numbers(plan2) == _numbers(plan)
    assert pl2["home_swing"]["status"] == TPL.HOME_STATUS_UNREADABLE


# --- the neutral setting -------------------------------------------------------------------------
def test_the_neutral_setting_returns_the_placement_untouched_field_for_field(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    plan, pl = _record_plan()
    monkeypatch.setattr(AD, "_place_thresholds_core", lambda *a, **k: (plan, pl))

    def _never(uid, loaded=None):
        raise AssertionError("the neutral setting must not read the home record")
    monkeypatch.setattr(AD, "_home_chronic_samples", _never)
    monkeypatch.setattr(TPL, "HOME_SWING", False)
    plan2, pl2 = AD._place_thresholds_from_record("uid", object(), [dict(CAND)], hemisphere="Right")
    assert plan2 is plan and pl2 is pl
    assert dataclasses.asdict(plan2) == dataclasses.asdict(plan)
    rows_a = [dataclasses.asdict(f) for f in PRESC.prescribe(mode="dual", threshold_plan=plan,
                                                             candidate=CAND).fields]
    rows_b = [dataclasses.asdict(f) for f in PRESC.prescribe(mode="dual", threshold_plan=plan2,
                                                             candidate=CAND).fields]
    assert rows_a == rows_b


def test_the_neutral_setting_is_read_from_the_environment():
    code = ("import sys; sys.path.insert(0, %r); "
            "from ClosedLoopDeployment import threshold_placement as T; print(T.HOME_SWING)"
            % str(__import__("pathlib").Path(TPL.__file__).resolve().parents[1]))
    for env, want in (("0", "False"), ("1", "True")):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**__import__("os").environ, "BRAVO_THRESHOLD_HOME_SWING": env},
                             timeout=120)
        assert out.stdout.strip().splitlines()[-1] == want, out.stderr
