"""Synthetic regression fixtures adapted from Prasad8146f069 for threshold_placement."""
import dataclasses

import numpy as np
import pytest

from ClosedLoopDeployment import threshold_placement as TPL
from ClosedLoopDeployment import prescription as PRESC
from ClosedLoopDeployment.types import ThresholdPlan


def _table(rows):
    """A design-rule table in the shape `design_rule.separation_table` emits."""
    return [{"averaging_s": a, "onset_s": o, "min_separation": m} for a, o, m in rows]


def _capture_plan(upper=196.13, lower=190.89):
    return ThresholdPlan(upper=upper, lower=lower, capture_amp_low=1.4, capture_amp_high=4.8,
                         warnings=["D26 inverted capture: not assessed"],
                         capture_verdicts={"inverted": {"status": "not assessed"}},
                         note="capture")


# --- the centre ------------------------------------------------------------------------------
def test_median_level_is_the_median_of_the_averaged_readings():
    t = 1_000_000.0 + 3.0 * np.arange(40)
    power = np.r_[np.full(20, 100.0), np.full(20, 300.0)]        # median of averaged = 200 at 3 s
    m = TPL.median_level(t, power, averaging_s=3.0)
    assert m["available"] is True
    assert m["median"] == pytest.approx(200.0)
    assert m["n_readings"] == 40 and m["averaging_s"] == 3.0


def test_median_level_refuses_on_no_readings():
    m = TPL.median_level(np.empty(0), np.empty(0), averaging_s=3.0)
    assert m["available"] is False and m["median"] is None and "no" in m["reason"]


# --- the pair --------------------------------------------------------------------------------
def test_record_pair_is_the_median_plus_and_minus_the_rules_minimum_at_the_cards_timing():
    rows = _table([(3.0, 30.0, 5.0), (3.0, 60.0, 4.0), (6.0, 30.0, 12.0)])
    p = TPL.record_pair(median=181.12, design_rows=rows, averaging_ms=3000, onset_ms=30000)
    assert p["available"] is True
    assert p["upper"] == pytest.approx(186.12) and p["lower"] == pytest.approx(176.12)
    assert p["centre"] == pytest.approx(181.12) and p["half_separation"] == 5.0
    assert p["timing_exact"] is True and p["averaging_s"] == 3.0 and p["onset_s"] == 30.0


def test_record_pair_uses_the_nearest_evaluated_timing_and_says_so_when_not_exact():
    rows = _table([(3.0, 30.0, 5.0), (6.0, 30.0, 12.0)])
    p = TPL.record_pair(median=100.0, design_rows=rows, averaging_ms=4000, onset_ms=30000)
    assert p["available"] is True and p["half_separation"] == 5.0
    assert p["timing_exact"] is False and "nearest" in p["note"]


def test_record_pair_refuses_when_the_rule_finds_no_separation_that_holds():
    rows = _table([(3.0, 30.0, None)])
    p = TPL.record_pair(median=100.0, design_rows=rows, averaging_ms=3000, onset_ms=30000)
    assert p["available"] is False and p["upper"] is None and p["lower"] is None
    assert "no separation" in p["reason"]


def test_record_pair_refuses_without_a_median_or_a_table():
    rows = _table([(3.0, 30.0, 5.0)])
    assert TPL.record_pair(median=None, design_rows=rows, averaging_ms=3000, onset_ms=30000)["available"] is False
    assert TPL.record_pair(median=100.0, design_rows=[], averaging_ms=3000, onset_ms=30000)["available"] is False
    assert TPL.record_pair(median=100.0, design_rows=rows, averaging_ms=None, onset_ms=30000)["available"] is False


# --- applying it to the plan ---------------------------------------------------------------
def test_apply_replaces_the_pair_keeps_the_capture_pair_beside_it_and_touches_nothing_else():
    plan = _capture_plan()
    placement = TPL.record_pair(median=181.12, design_rows=_table([(3.0, 30.0, 5.0)]),
                                averaging_ms=3000, onset_ms=30000)
    new = TPL.apply(plan, placement)
    assert new is not plan
    assert new.upper == pytest.approx(186.12) and new.lower == pytest.approx(176.12)
    assert new.capture_upper == 196.13 and new.capture_lower == 190.89
    assert new.placement_rule == "record" and plan.placement_rule == "capture"
    assert new.placement["centre"] == pytest.approx(181.12) and new.placement["half_separation"] == 5.0
    # the D26 verdicts, the capture amplitudes and the warnings are the capture's and stay
    assert new.warnings == plan.warnings and new.capture_verdicts == plan.capture_verdicts
    assert new.capture_amp_low == 1.4 and new.capture_amp_high == 4.8
    assert "median" in new.placement_note and "design rule" in new.placement_note


def test_apply_leaves_the_capture_plan_alone_when_the_placement_is_refused():
    plan = _capture_plan()
    refused = TPL.record_pair(median=None, design_rows=[], averaging_ms=3000, onset_ms=30000)
    new = TPL.apply(plan, refused)
    assert new.upper == 196.13 and new.lower == 190.89 and new.placement_rule == "capture"
    assert new.capture_upper == 196.13 and new.capture_lower == 190.89
    assert new.placement.get("available") is False and "reason" in new.placement


def test_apply_recomputes_the_time_fractions_for_the_new_pair_when_a_series_is_given():
    plan = _capture_plan()
    placement = TPL.record_pair(median=100.0, design_rows=_table([(3.0, 30.0, 10.0)]),
                                averaging_ms=3000, onset_ms=30000)    # pair 90 / 110
    series = np.r_[np.full(10, 50.0), np.full(20, 100.0), np.full(10, 200.0)]
    new = TPL.apply(plan, placement, observed_series=series)
    assert new.frac_time_below == pytest.approx(0.25)
    assert new.frac_time_between == pytest.approx(0.5)
    assert new.frac_time_above == pytest.approx(0.25)


# --- the card's row --------------------------------------------------------------------------
def test_the_threshold_rows_name_the_rule_and_the_capture_value_the_tablet_would_have_used():
    plan = TPL.apply(_capture_plan(), TPL.record_pair(
        median=181.12, design_rows=_table([(3.0, 30.0, 5.0)]), averaging_ms=3000, onset_ms=30000))
    p = PRESC.prescribe(mode="dual", threshold_plan=plan, candidate={"channel": "ZERO_TWO_LEFT",
                        "center_hz": 24.5, "band_width_hz": 5.0})
    fields = {f.name: f for f in p.fields}
    up, lo = fields["Upper LFP threshold"], fields["Lower LFP threshold"]
    assert up.value == pytest.approx(186.12) and lo.value == pytest.approx(176.12)
    assert "median" in up.why and "design rule" in up.why and "196.13" in up.why
    assert "median" in lo.why and "190.89" in lo.why
    assert "capture mean" not in up.why.split("tablet")[0]     # the rule comes first, the capture after


def test_the_threshold_rows_keep_the_capture_wording_when_the_plan_is_a_capture_plan():
    p = PRESC.prescribe(mode="dual", threshold_plan=_capture_plan(),
                        candidate={"channel": "ZERO_TWO_LEFT", "center_hz": 24.5, "band_width_hz": 5.0})
    up = next(f for f in p.fields if f.name == "Upper LFP threshold")
    assert up.value == 196.13 and "capture mean" in up.why and "median" not in up.why


# --- the report's wiring -----------------------------------------------------------------------
def test_the_report_step_places_the_pair_from_the_record_and_keeps_the_capture_pair(monkeypatch):
    """`adapter._place_thresholds_from_record` with every collaborator stubbed: the median comes
    from the series, the design rule is fitted at that median (the provisional plan handed to
    `write_design_rule` has upper == lower == median), the pair is median +- the rule's minimum,
    and the capture pair rides along."""
    from ClosedLoopDeployment import adapter as AD
    seen = {}
    monkeypatch.setattr(AD, "simulation_inputs_for_participant",
                        lambda uid, **kw: {"t": 1_000_000.0 + 3.0 * np.arange(40),
                                           "power": np.r_[np.full(20, 100.0), np.full(20, 300.0)],
                                           "amp_obs": np.zeros(40)})
    monkeypatch.setattr(AD._tr_mod if hasattr(AD, "_tr_mod") else __import__(
        "ClosedLoopDeployment.timing_recommendation", fromlist=["for_participant"]),
        "for_participant", lambda uid: {"averaging_ms": {"value_ms": 3000},
                                        "onset_upper_ms": {"value_ms": 30000}})

    def _write(participant, *, candidate, hemisphere, threshold_plan, loaded=None, epochs=None):
        seen["provisional"] = (threshold_plan.upper, threshold_plan.lower)
        return {"written": True, "store_key": "design/x"}
    monkeypatch.setattr(AD, "write_design_rule", _write)
    monkeypatch.setattr(AD, "design_rule_if_stored",
                        lambda participant, candidate=None, *, hemisphere="Left":
                        {"refused": False, "model": "L1", "table": _table([(3.0, 30.0, 5.0)])})

    class _Rep:
        threshold = _capture_plan()
    cands = [{"channel": "ZERO_TWO_LEFT", "center_hz": 24.5}]
    plan, placement = AD._place_thresholds_from_record("uid", _Rep(), cands, hemisphere="Left")
    assert seen["provisional"] == (200.0, 200.0), "the design rule is fitted with its level at the median"
    assert placement["available"] is True and placement["placement_rule"] == "record"
    assert plan.upper == pytest.approx(205.0) and plan.lower == pytest.approx(195.0)
    assert plan.capture_upper == 196.13 and plan.capture_lower == 190.89
    assert plan.placement_rule == "record"
    assert placement["median"]["n_readings"] == 40 and placement["design_rule"]["model"] == "L1"


def test_the_report_step_leaves_the_capture_pair_when_the_series_is_absent(monkeypatch):
    from ClosedLoopDeployment import adapter as AD
    monkeypatch.setattr(AD, "simulation_inputs_for_participant",
                        lambda uid, **kw: {"t": np.empty(0), "power": np.empty(0), "amp_obs": np.empty(0),
                                           "absent_reason": "no tiles for this contact"})
    monkeypatch.setattr(__import__("ClosedLoopDeployment.timing_recommendation", fromlist=["x"]),
                        "for_participant", lambda uid: {"averaging_ms": {"value_ms": 3000},
                                                        "onset_upper_ms": {"value_ms": 30000}})

    class _Rep:
        threshold = _capture_plan()
    plan, placement = AD._place_thresholds_from_record(
        "uid", _Rep(), [{"channel": "ZERO_TWO_LEFT", "center_hz": 24.5}], hemisphere="Left")
    assert placement["available"] is False and "no tiles" in placement["reason"]
    assert plan.upper == 196.13 and plan.lower == 190.89 and plan.placement_rule == "capture"


def test_pipeline_run_hands_the_capture_plan_to_the_placement_hook_before_the_rows_are_built():
    """The live proof of 2026-09-16 found the `threshold` block carrying the record pair while the
    parameter card's rows still printed the capture values: the rows are built inside
    `pipeline.run`, which ran BEFORE the placement. `run(place_thresholds=...)` is called with the
    capture plan and its return value is what everything downstream reads -- pinned by reading the
    source, since a full `run` needs the live record."""
    import ast, inspect
    from ClosedLoopDeployment import pipeline as PL
    src = inspect.getsource(PL.run)
    assert "place_thresholds" in inspect.signature(PL.run).parameters
    i_place = src.index("A.threshold_placement(")
    i_hook = src.index("place_thresholds(")
    i_rows = src.index("prescribe_all_modes(")
    i_elig = src.index("check_eligibility")
    assert i_place < i_hook < i_elig and i_hook < i_rows, "the hook runs after the capture, before eligibility and the rows"
    # and the adapter passes its own step as the hook
    from ClosedLoopDeployment import adapter as AD
    asrc = inspect.getsource(AD.report_for_participant)
    assert "place_thresholds=" in asrc and "_place_thresholds_from_record" in asrc


def test_applying_twice_never_loses_the_capture_pair():
    """The live proof of 2026-09-16 found `capture_upper` equal to the RECORD upper: the placement
    had run twice and the second pass took the first pass's output for the capture. A plan already
    placed keeps its capture pair through any further application."""
    plan = _capture_plan()
    placement = TPL.record_pair(median=181.12, design_rows=_table([(3.0, 30.0, 5.0)]),
                                averaging_ms=3000, onset_ms=30000)
    once = TPL.apply(plan, placement)
    twice = TPL.apply(once, placement)
    assert twice.capture_upper == 196.13 and twice.capture_lower == 190.89
    assert twice.upper == once.upper and twice.lower == once.lower
