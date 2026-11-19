"""A threshold below zero: a WARNING ONLY (open item of decision 495; the PI, 2026-10-22: "Go").

Decision 180's record pair is the median averaged reading minus and plus the design rule's
half-separation. Where the median is smaller than the half-separation the LOWER threshold comes out
below zero (RCS08 R 0-3 26.5 Hz: 265.95 / -54.05). Device band power cannot go below zero, so the
device would never cross it. The same check covers the upper threshold and the Single mode's
threshold (0.75 x (upper - lower) + lower, D20). As C6-C8, nothing is refused and no number moves:
`below_zero` goes on the placement and the plan, and a plain warning is appended to the placement
note and to the Upper / Lower / Single rows' reasons. These tests build the inputs by hand and read
the values: the warning text and value, the cases that cannot warn, every number unchanged, the
capture pair covered, the order after the home swing, and the neutral setting.
"""
import dataclasses
import subprocess
import sys

import numpy as np
import pytest

from ClosedLoopDeployment import threshold_placement as TPL
from ClosedLoopDeployment import prescription as PRESC
from ClosedLoopDeployment.types import ThresholdPlan

CAND = {"channel": "ZERO_THREE_RIGHT", "center_hz": 26.5, "band_width_hz": 5.0}
LOWER_WARN = ("The lower threshold is below zero (−54.05); band power cannot go below zero, "
              "so the device would never cross it.")


def _record_plan(median=105.95, half=160.0):
    """RCS08 R 0-3 26.5 Hz's shape: a median of 105.95 and a half-separation of 160 give
    265.95 / -54.05."""
    cap = ThresholdPlan(upper=180.0, lower=150.0, capture_amp_low=1.4, capture_amp_high=4.8,
                        note="capture")
    pl = TPL.record_pair(median=median, design_rows=[{"averaging_s": 3.0, "onset_s": 30.0,
                                                      "min_separation": half}],
                         averaging_ms=3000, onset_ms=30000)
    return TPL.apply(cap, pl, observed_series=np.linspace(0.0, 400.0, 101)), pl


def _numbers(plan):
    return {f.name: getattr(plan, f.name) for f in dataclasses.fields(plan)
            if f.name not in ("placement", "placement_note")}


# --- the block ----------------------------------------------------------------------------------
def test_a_lower_threshold_below_zero_gets_the_warning_with_its_value():
    b = TPL.below_zero_block(265.95, -54.05)
    assert b["status"] == "below zero" and b["below_zero"] == ["lower"]
    assert b["warnings"]["lower"] == LOWER_WARN
    assert b["warnings"]["upper"] is None and b["warnings"]["single"] is None
    assert b["single"] == pytest.approx(0.75 * (265.95 + 54.05) - 54.05)     # 185.95, above zero
    assert b["warning"] == LOWER_WARN
    assert b["lower"] == -54.05 and b["upper"] == 265.95


def test_a_pair_wholly_above_zero_gives_no_warning():
    b = TPL.below_zero_block(640.22, 320.22)
    assert b["status"] == "none below zero" and b["below_zero"] == []
    assert b["warning"] is None and all(v is None for v in b["warnings"].values())


def test_zero_itself_is_not_below_zero():
    b = TPL.below_zero_block(100.0, 0.0)
    assert b["below_zero"] == [] and b["warning"] is None


def test_the_upper_and_single_thresholds_are_covered_too():
    # only reachable with negative band power; covered so a negative upper can never pass unsaid
    b = TPL.below_zero_block(-10.0, -50.0)
    assert b["below_zero"] == ["upper", "lower", "single"]
    assert b["single"] == pytest.approx(-20.0)
    assert b["warnings"]["upper"] == (
        "The upper threshold is below zero (−10.00); band power cannot go below zero, so power "
        "would always sit above it and the device would never see it crossed from above.")
    assert b["warnings"]["single"].startswith("The single threshold is below zero (−20.00)")
    assert b["warning"] == b["warnings"]["upper"] + " " + b["warnings"]["lower"]
    # a Single threshold below zero while the upper is not: lower well below, 0.75 of the way up
    b2 = TPL.below_zero_block(10.0, -100.0)
    assert b2["below_zero"] == ["lower", "single"] and b2["single"] == pytest.approx(-17.5)


def test_no_pair_gives_no_warning():
    b = TPL.below_zero_block(None, None)
    assert b["below_zero"] == [] and b["single"] is None and b["warning"] is None


# --- nothing that decides moves ------------------------------------------------------------------
def test_the_pair_and_every_number_on_it_are_unchanged_and_the_note_gains_only_the_warning():
    plan, pl = _record_plan()
    assert plan.upper == pytest.approx(265.95) and plan.lower == pytest.approx(-54.05)
    plan2, pl2 = TPL.with_below_zero(plan, pl)
    assert _numbers(plan2) == _numbers(plan)
    assert {k: v for k, v in pl2.items() if k != "below_zero"} == pl
    assert {k: v for k, v in plan2.placement.items() if k != "below_zero"} == plan.placement
    assert plan2.placement["below_zero"] == pl2["below_zero"]
    assert plan2.placement_note == plan.placement_note + ". " + pl2["below_zero"]["warning"]
    assert pl2["below_zero"]["warnings"]["lower"] == LOWER_WARN


def test_the_threshold_rows_keep_their_values_and_only_the_right_row_gains_the_warning():
    plan, pl = _record_plan()
    plan2, _ = TPL.with_below_zero(plan, pl)
    for mode in ("dual", "single"):
        a = {f.name: f for f in PRESC.prescribe(mode=mode, threshold_plan=plan, candidate=CAND).fields}
        b = {f.name: f for f in PRESC.prescribe(mode=mode, threshold_plan=plan2, candidate=CAND).fields}
        assert list(a) == list(b)
        for name in a:
            fa, fb = dataclasses.asdict(a[name]), dataclasses.asdict(b[name])
            if name == "Lower LFP threshold":
                assert fb["why"] == fa["why"] + " " + LOWER_WARN
                fa.pop("why"), fb.pop("why")
            assert fa == fb, (mode, name)                     # the upper and single rows untouched
    single = next(f for f in PRESC.prescribe(mode="single", threshold_plan=plan2, candidate=CAND).fields
                  if f.name == "Single LFP threshold")
    assert single.value == pytest.approx(185.95) and "below zero" not in single.why


def test_a_single_threshold_below_zero_warns_on_its_row():
    cap = ThresholdPlan(upper=10.0, lower=-100.0, capture_amp_low=1.4, capture_amp_high=4.8)
    cap = TPL.apply(cap, {"available": False, "reason": "no design table"})
    cap2, _ = TPL.with_below_zero(cap, {"available": False})
    single = next(f for f in PRESC.prescribe(mode="single", threshold_plan=cap2, candidate=CAND).fields
                  if f.name == "Single LFP threshold")
    assert single.value == pytest.approx(-17.5)
    assert single.why.endswith("The single threshold is below zero (−17.50); band power cannot go "
                               "below zero, so power would always sit above it and the device would "
                               "never see it crossed from above.")


def test_the_report_step_appends_after_the_home_swing_and_moves_nothing(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    plan, pl = _record_plan()
    monkeypatch.setattr(AD, "_place_thresholds_core", lambda *a, **k: (plan, dict(pl)))
    monkeypatch.setattr(AD, "_home_chronic_samples", lambda uid, loaded=None: {})   # no home record
    monkeypatch.setattr(TPL, "HOME_SWING", True)
    monkeypatch.setattr(TPL, "BELOW_ZERO", True)
    plan2, pl2 = AD._place_thresholds_from_record("uid", object(), [dict(CAND)], hemisphere="Right")
    assert _numbers(plan2) == _numbers(plan)
    hs, bz = pl2["home_swing"]["warning"], pl2["below_zero"]["warning"]
    assert hs and bz == LOWER_WARN
    assert plan2.placement_note == plan.placement_note + ". " + hs + ". " + bz
    lower = next(f for f in PRESC.prescribe(mode="dual", threshold_plan=plan2, candidate=CAND).fields
                 if f.name == "Lower LFP threshold")
    assert lower.why.endswith(" " + hs + " " + LOWER_WARN) and lower.value == pytest.approx(-54.05)


def test_the_neutral_setting_returns_the_placement_untouched_field_for_field(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    plan, pl = _record_plan()
    monkeypatch.setattr(AD, "_place_thresholds_core", lambda *a, **k: (plan, pl))
    monkeypatch.setattr(TPL, "HOME_SWING", False)
    monkeypatch.setattr(TPL, "BELOW_ZERO", False)
    plan2, pl2 = AD._place_thresholds_from_record("uid", object(), [dict(CAND)], hemisphere="Right")
    assert plan2 is plan and pl2 is pl
    assert "below_zero" not in (plan2.placement or {})


def test_a_failing_check_never_moves_the_pair(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    plan, pl = _record_plan()
    monkeypatch.setattr(AD, "_place_thresholds_core", lambda *a, **k: (plan, dict(pl)))
    monkeypatch.setattr(TPL, "HOME_SWING", False)
    monkeypatch.setattr(TPL, "BELOW_ZERO", True)

    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(TPL, "with_below_zero", _boom)
    plan2, pl2 = AD._place_thresholds_from_record("uid", object(), [dict(CAND)], hemisphere="Right")
    assert plan2 is plan and pl2 == pl


def test_the_neutral_setting_is_read_from_the_environment():
    code = ("import sys; sys.path.insert(0, %r); "
            "from ClosedLoopDeployment import threshold_placement as T; print(T.BELOW_ZERO)"
            % str(__import__("pathlib").Path(TPL.__file__).resolve().parents[1]))
    for env, want in (("0", "False"), ("1", "True")):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**__import__("os").environ, "BRAVO_THRESHOLD_BELOW_ZERO": env},
                             timeout=120)
        assert out.stdout.strip().splitlines()[-1] == want, out.stderr
