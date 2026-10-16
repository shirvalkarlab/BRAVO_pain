"""Decision 199 (2026-09-17), the PI's ruling on the readiness screen's rule:

    "'at least 50% of the scanned bands respond' doesn't need to be true. We literally only need
    one actual band that meets the criteria. What we need is for the band to have a positive
    relationship with the biomarker and a negative relationship with stimulation. Those contact
    and rate combinations should be chosen as responsive and displayed on the Stim Optimizer
    screen."

So a (contact, stimulation side, rate) cell is responsive when AT LEAST ONE band (a) has a
significant NEGATIVE era-blocked slope of band power on current (falls with stimulation) AND
(b) has an ESTABLISHED POSITIVE correlation with pain on the stored Biomarkers grid for that
contact (rises with pain). Both signs together are the device's fixed control polarity: more
current, less power, less pain. The two majority rules of decision 143 are gone; the capture
counts stay on the row as information.

Values, not shapes: which cells pass, which reason names which missing half, and that the gate
and the screen give the same sentences.

Merged here 2026-10-05: test_harmonic_warning.py (each under its own heading below).
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import pipeline as PL
from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer.routines import pain_relationship as PR
from StimOptimizer.routines import stage_gate as GATE
from StimOptimizer.tests import _helpers as H
import ast
import inspect

from StimOptimizer import bravo_service as BS
from StimOptimizer import titration_plan as TP


# --- fixtures: a real ResponseResult per band, a stub evidence cell -------------------------------
_Res = H.stub_result


CENTRES = H.CENTRES
COND = "adaptive_band_passes_lfp_response"


_Ev = H.BandStubEvidence


_fn_negative_at = H.fn_negative_at


# --- the rule itself -------------------------------------------------------------------------------
def test_one_band_falling_with_current_and_rising_with_pain_makes_the_cell_responsive():
    ev = {("ch", "Left", 55.0): _Ev()}
    screen, best = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                   pain_positive_by_channel={"ch": {24.0}})
    row = screen.iloc[0]
    assert row.n_era_negative_significant == 1
    assert row.n_pain_positive == 1 and row.n_qualifying == 1
    assert list(row.qualifying_centers_hz) == [24.0]
    assert bool(row.deployable) is True and row.blocking_reasons == ""
    assert best == ("ch", "Left", 55.0)


def test_the_two_halves_must_meet_on_the_SAME_band():
    """Falling at 24 Hz and rising with pain at 12 Hz is two half-findings, not one finding."""
    ev = {("ch", "Left", 55.0): _Ev()}
    screen, best = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                   pain_positive_by_channel={"ch": {12.0}})
    row = screen.iloc[0]
    assert row.n_era_negative_significant == 1 and row.n_pain_positive == 1
    assert row.n_qualifying == 0 and bool(row.deployable) is False and best is None
    assert "no band both falls with current and rises with pain" in row.blocking_reasons
    assert "24 Hz" in row.blocking_reasons and "12 Hz" in row.blocking_reasons


def test_no_established_positive_pain_band_on_the_contact_refuses_and_says_so():
    """The live case the rule was written for, inverted: L 1-3+ has 18 of 18 bands falling with
    current at 55 Hz and NOT ONE band whose power rises with pain (every r is negative)."""
    ev = {("ONE_THREE_LEFT", "Left", 55.0): _Ev()}
    screen, best = EV.screen_cells(ev, response_fn=_fn_negative_at(CENTRES),
                                   pain_positive_by_channel={"ONE_THREE_LEFT": set()})
    row = screen.iloc[0]
    assert row.n_era_negative_significant == 18 and row.n_pain_positive == 0
    assert bool(row.deployable) is False and best is None
    assert ("no band on this contact has a supported positive relationship with pain"
            in row.blocking_reasons)


def test_a_contact_absent_from_the_grid_is_not_assessed_rather_than_refused_or_passed():
    ev = {("ch", "Left", 55.0): _Ev()}
    screen, best = EV.screen_cells(ev, response_fn=_fn_negative_at(CENTRES),
                                   pain_positive_by_channel={"other": {24.0}})
    row = screen.iloc[0]
    assert row.n_pain_positive is None or (isinstance(row.n_pain_positive, float)
                                            and np.isnan(row.n_pain_positive))
    assert bool(row.deployable) is False and best is None
    assert "not known" in row.blocking_reasons and "Biomarkers" in row.blocking_reasons
    # and with NO grid at all, the same
    screen2, best2 = EV.screen_cells(ev, response_fn=_fn_negative_at(CENTRES),
                                     pain_positive_by_channel=None)
    assert "not known" in screen2.iloc[0].blocking_reasons and best2 is None


def test_the_majority_rules_are_gone():
    assert not hasattr(EV, "MIN_RESPONDING_BAND_FRACTION")
    ev = {("ch", "Left", 55.0): _Ev()}
    with pytest.raises(TypeError):
        EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]), min_responding_fraction=0.5)
    # one band of eighteen IS a finding when it is the right band
    screen, best = EV.screen_cells(ev, response_fn=_fn_negative_at([24.0]),
                                   pain_positive_by_channel={"ch": set(CENTRES)})
    assert best is not None and "correlated family" not in screen.iloc[0].blocking_reasons


def test_the_verdict_takes_results_keyed_by_centre_and_reports_both_halves():
    res = {c: _Res(True, 0.001, 1.0, -0.2 if c in (20.0, 21.0) else +0.2) for c in CENTRES}
    v = EV.cell_response_verdict(res, pain_positive_centers={21.0, 22.0})
    assert v["n_bands"] == 18 and v["n_era_negative_significant"] == 2
    assert v["n_pain_positive"] == 2 and v["n_qualifying"] == 1
    assert v["qualifying_centers_hz"] == [21.0]
    assert v["responds"] is True and v["blocking_reasons"] == []
    assert EV.cell_response_verdict({}, pain_positive_centers={21.0})["responds"] is None
    assert EV.cell_response_verdict(res, pain_positive_centers=None)["responds"] is None


def test_matching_by_centre_tolerates_float_spelling():
    res = {24.5: _Res(True, 0.001, 1.0, -0.2)}
    v = EV.cell_response_verdict(res, pain_positive_centers={24.500000001})
    assert v["n_qualifying"] == 1


def test_ranking_prefers_more_qualifying_bands_then_separation():
    # `a` gets one qualifying band with a huge separation, `b` three with a modest one
    sa, _ = EV.screen_cells({("a", "Left", 55.0): _Ev()},
                            response_fn=_fn_negative_at([24.0]),
                            pain_positive_by_channel={"a": {24.0}})
    sb, _ = EV.screen_cells({("b", "Left", 55.0): _Ev()},
                            response_fn=_fn_negative_at([22.0, 23.0, 24.0]),
                            pain_positive_by_channel={"b": {22.0, 23.0, 24.0}})
    sa["median_separation_d"] = 9.9
    screen = pd.concat([sa, sb], ignore_index=True)
    assert EV.best_deployable(screen) == ("b", "Left", 55.0)


# --- reading the Biomarkers grid ----------------------------------------------------------------
def _grid():
    """The shape `ClosedLoopDeployment.adapter.band_sweep_grid_for_closed_loop` returns."""
    def rows(spec):
        # (centre, r, interval low, interval high, q, answer): the interval is the grid's own
        # block-bootstrap interval on the best-of-lengths correlation (decision 183)
        return [dict(band_center_hz=c, pearson_r=r, pearson_r_low=lo, pearson_r_high=hi,
                     family_wise_q_8_to_30hz=q, answer=a) for c, r, lo, hi, q, a in spec]
    return {
        "available": True,
        "grid_settings": {"sweep_metric": "nrs", "metric_label": "NRS (0-10)",
                          "stored_utc": "2026-09-17T01:02:03Z"},
        "band_time_sweep": {
            "ONE_THREE_RIGHT": {"best_correlation_rows": rows([
                (24.5, 0.43, 0.23, 0.60, 0.016, "established"), (25.5, 0.44, 0.23, 0.60, 0.016, "established"),
                (14.5, 0.30, 0.10, 0.48, 0.124, "established"),
                # SUPPORTED: interval wholly above zero, but under the selection-aware shuffle bar
                (26.5, 0.23, 0.05, 0.41, 0.62, "not_resolved"),
                # positive point value whose interval includes zero: not supported
                (12.5, 0.10, -0.06, 0.24, 0.60, "not_resolved"),
                (8.5, -0.20, -0.36, -0.03, 0.30, "not_resolved")])},
            "ONE_THREE_LEFT": {"best_correlation_rows": rows([
                (12.5, -0.47, -0.62, -0.30, 0.0017, "established"), (24.5, -0.10, -0.26, 0.05, 0.5, "not_resolved")])},
            "ZERO_TWO_LEFT": {"best_correlation_rows": []},
        },
    }


def test_pain_positive_centres_are_positive_bands_whose_interval_lies_above_zero():
    """Decision 210 (the PI, 2026-09-20: loosen the rule so the best-supported bands pass): a band
    counts when its correlation is positive and its own block-bootstrap interval is wholly above
    zero. Clearing the grid's extra selection-aware bar ("established") is reported, not required.
    A positive point value whose interval includes zero still does not count."""
    by = PR.pain_positive_centers_by_channel(_grid())
    assert by["ONE_THREE_RIGHT"] == frozenset({24.5, 25.5, 14.5, 26.5})
    assert by["ONE_THREE_LEFT"] == frozenset()          # a NEGATIVE band does not count, established or not
    assert by["ZERO_TWO_LEFT"] == frozenset()
    assert "ZERO_THREE_LEFT" not in by                  # absent from the grid: unknown, not empty


def test_the_stricter_reading_is_still_available_and_reported():
    by = PR.pain_positive_centers_by_channel(_grid(), level=PR.ESTABLISHED)
    assert by["ONE_THREE_RIGHT"] == frozenset({24.5, 25.5, 14.5})
    s = PR.summarise(_grid())["by_channel"]["ONE_THREE_RIGHT"]
    assert s["n_supported_positive"] == 4 and s["n_established_positive"] == 3
    assert s["n_positive_not_supported"] == 1
    assert s["supported_not_established_hz"] == [26.5]


def test_a_row_without_an_interval_cannot_be_supported():
    g = _grid()
    for r in g["band_time_sweep"]["ONE_THREE_RIGHT"]["best_correlation_rows"]:
        r.pop("pearson_r_low"); r.pop("pearson_r_high")
    by = PR.pain_positive_centers_by_channel(g)
    assert by["ONE_THREE_RIGHT"] == frozenset({24.5, 25.5, 14.5})   # only the established ones remain


def test_an_unavailable_grid_gives_no_mapping():
    assert PR.pain_positive_centers_by_channel({"available": False, "reason": "x"}) is None
    assert PR.pain_positive_centers_by_channel(None) is None


def test_the_summary_names_the_score_the_stamp_and_every_contacts_bands():
    s = PR.summarise(_grid())
    assert s["available"] is True and s["score"] == "nrs" and s["score_label"] == "NRS (0-10)"
    assert s["stored_utc"] == "2026-09-17T01:02:03Z"
    assert s["by_channel"]["ONE_THREE_RIGHT"]["centers_hz"] == [14.5, 24.5, 25.5, 26.5]
    assert s["by_channel"]["ONE_THREE_RIGHT"]["n_established_positive"] == 3
    assert s["by_channel"]["ONE_THREE_RIGHT"]["n_supported_positive"] == 4
    assert s["by_channel"]["ONE_THREE_LEFT"]["n_established_negative"] == 1
    assert s["rule"].startswith("a band counts when")
    assert "wholly above zero" in s["rule"] and "established" in s["rule"]


# --- the gate applies the same rule and the same sentences --------------------------------------
def test_the_gate_passes_a_side_on_one_qualifying_band_and_names_it():
    ev = GATE.LfpEvidence(amplitude_mA=np.array([1.0, 3.0] * 30, float),
                          band_power={(c, 5.0): np.full(60, c) for c in CENTRES},
                          era=np.tile(["a", "b"], 30), cluster=np.arange(60), hemisphere="Left")
    ev.channel = "ch"
    fn = _fn_negative_at([24.0])
    c = GATE.evaluate_gate(H.frozen(H.setting("Left")), lfp=ev, band_centers=CENTRES, band_width_hz=5.0,
                           pain_positive_by_channel={"ch": {24.0}},
                           response_fn=fn).condition(COND)
    assert c.passed is True, c.detail
    side = c.evidence["per_hemisphere"]["Left"]
    assert side["n_qualifying"] == 1 and side["qualifying_centers_hz"] == [24.0]
    assert side["best_center_hz"] == 24.0


def test_the_gate_and_the_screen_refuse_with_the_same_words():
    ev = GATE.LfpEvidence(amplitude_mA=np.array([1.0, 3.0] * 30, float),
                          band_power={(c, 5.0): np.full(60, c) for c in CENTRES},
                          era=np.tile(["a", "b"], 30), cluster=np.arange(60), hemisphere="Left")
    ev.channel = "ch"
    screen, _ = EV.screen_cells({("ch", "Left", 55.0): ev}, response_fn=_fn_negative_at([24.0]),
                                pain_positive_by_channel={"ch": {12.0}})
    c = GATE.evaluate_gate(H.frozen(H.setting("Left")), lfp=ev, band_centers=CENTRES, band_width_hz=5.0,
                           pain_positive_by_channel={"ch": {12.0}},
                           response_fn=_fn_negative_at([24.0])).condition(COND)
    assert c.passed is False
    assert "; ".join(c.evidence["per_hemisphere"]["Left"]["rule_blocking_reasons"]) == \
        screen["blocking_reasons"].iloc[0]
    assert "majority" not in c.detail


def test_live_evidence_threads_the_mapping_to_the_screen(monkeypatch):
    """`pipeline.live_evidence(pain_positive_by_channel=...)` reaches `screen_cells`."""
    seen = {}
    real = EV.screen_cells

    def spy(evidence, **kw):
        seen["pain"] = kw.get("pain_positive_by_channel")
        return real(evidence, **kw)
    monkeypatch.setattr(EV, "screen_cells", spy)
    from StimOptimizer import adapter as AD
    monkeypatch.setattr(AD, "evidence_for_participant",
                        lambda *a, **k: ({("ch", "Left", 55.0): _Ev()}, pd.DataFrame()))
    from StimOptimizer.routines import lfp_response as LR
    monkeypatch.setattr(LR, "assess_response", _fn_negative_at([24.0]))
    le = PL.live_evidence(object(), pain_positive_by_channel={"ch": {24.0}})
    assert seen["pain"] == {"ch": {24.0}}
    assert le.selected_key == ("ch", "Left", 55.0)


# ================================================================================================
# From test_harmonic_warning.py (merged here 2026-10-05).
# The harmonic rule on the readiness screen is a WARNING, never a refusal (the PI, 2026-09-21:
# "put a warning for the harmonic rule, but don't make it blocking").
#
# Decision 199 left the titration card's harmonic rule (a band centre within 2.5 Hz of a folded
# multiple of the rate, or its 1/2, 1/4 or 3/4 sub-harmonic, carries a folded multiple of the
# stimulation rate -- advisory, never a claim that the band measures the stimulator rather than the
# brain, the PI's correction of 2026-09-06; decision 146) as information beside each row and asked
# the PI whether the screen should apply it. His ruling: warn. So a row that is usable ONLY through
# qualifying bands sitting on a stimulator harmonic carries a warning sentence and a flag, the
# screen's summary counts such rows and says whether the selected best is one of them, and
# `deployable` is never changed by any of it.
#
# FIXED 2026-09-25: `harmonic_avoidance` (`titration_plan.py`, which this all rests on) used to fold
# only |250 - rate|, missing every higher multiple of the rate; it now calls
# `Biomarkers.routines.analytics.harmonic_landings_hz`, one home for the fold. The examples below use
# 20.5 Hz where they once used 24.5 Hz, because 24.5 Hz now correctly catches 55 Hz's and 145 Hz's
# fifth-multiple landing (folded to 25 Hz) and is no longer a clear band at either rate.
# ================================================================================================


def test_usable_only_through_harmonic_bands_is_a_warning_not_a_refusal():
    # 27.5 Hz is half of 55 Hz: the one qualifying band is on a harmonic.
    h = TP.harmonic_warning(55.0, [27.5], usable=True)
    assert h["only_through_harmonics"] is True
    assert h["near_hz"] == [27.5] and h["clear_hz"] == []
    assert "half the rate" in h["notes"]["27.5"]
    w = h["warning"]
    assert "only through" in w and "27.5" in w and "stimulator" in w
    assert "usable" in w and "not" in w.lower()            # says it stays usable, not refused
    assert "2026-09-21" in w                               # the ruling's date


def test_a_clear_band_beside_a_harmonic_one_is_a_note_not_a_warning():
    # 24.5 Hz was the example used here before 2026-09-25: the fix means it now catches the fifth
    # multiple of 55 Hz (folded to 25 Hz), so it is no longer clear; 20.5 Hz genuinely is.
    h = TP.harmonic_warning(55.0, [20.5, 27.5], usable=True)
    assert h["only_through_harmonics"] is False
    assert h["near_hz"] == [27.5] and h["clear_hz"] == [20.5]
    assert h["warning"] is None
    assert "20.5" in h["note"] and "clear" in h["note"]


def test_a_cell_that_is_not_usable_gets_no_warning_and_no_false_clear_band():
    """Caught live on RCS08 (rule 11): a refused cell whose qualifying bands all sit on a harmonic
    was given the note "... Hz is clear" with no band named. The note must not claim a clear band
    that does not exist."""
    h = TP.harmonic_warning(55.0, [27.5], usable=False)
    assert h["only_through_harmonics"] is False and h["warning"] is None
    assert h["near_hz"] == [27.5] and h["clear_hz"] == []  # the information is still there
    assert "is clear" not in h["note"]
    assert "every qualifying band" in h["note"] and "27.5" in h["note"] and "not usable" in h["note"]


def test_no_qualifying_band_and_two_genuinely_clear_centres_give_nothing():
    # 145 Hz is no longer harmonic-free everywhere after the 2026-09-25 fix (its fifth and seventh
    # multiples fold to 25 and 15 Hz), so this uses two centres that stay clear at that rate.
    assert TP.harmonic_warning(55.0, [], usable=True)["warning"] is None
    h = TP.harmonic_warning(145.0, [20.5, 21.5], usable=True)
    assert h["near_hz"] == [] and h["only_through_harmonics"] is False and h["warning"] is None


def test_the_row_fields_and_the_screen_summary():
    # 20.5 Hz replaces the 24.5 Hz this test used before 2026-09-25: the fix means 24.5 Hz now
    # catches 55 Hz's and 145 Hz's fifth-multiple landing (folded to 25 Hz), so it is no longer a
    # clear band at either rate; 20.5 Hz genuinely is clear at both.
    cells = [
        {"rate_hz": 55.0, "qualifying_centers_hz": [27.5], "deployable": True, "channel": "A", "hemisphere": "Left"},
        {"rate_hz": 55.0, "qualifying_centers_hz": [20.5, 27.5], "deployable": True, "channel": "B"},
        {"rate_hz": 110.0, "qualifying_centers_hz": [27.5], "deployable": False, "channel": "C"},
        {"rate_hz": 145.0, "qualifying_centers_hz": [20.5], "deployable": True, "channel": "D"},
    ]
    summary = BS.attach_harmonic_warnings(cells, selected={"channel": "A", "hemisphere": "Left", "rate_hz": 55.0})
    by = {c["channel"]: c for c in cells}
    # the row fields decision 199 added are unchanged in name and meaning
    assert by["A"]["qualifying_near_stim_harmonic_hz"] == [27.5]
    assert by["B"]["qualifying_clear_of_stim_harmonics_hz"] == [20.5]
    assert by["C"]["qualifying_near_stim_harmonic_hz"] == [27.5]      # 110/4
    # the new flag and sentence
    assert by["A"]["harmonic_only"] is True and by["A"]["harmonic_warning"]
    assert by["B"]["harmonic_only"] is False and by["B"]["harmonic_warning"] is None
    assert by["C"]["harmonic_only"] is False                          # not usable: nothing to warn about
    assert by["D"]["harmonic_only"] is False and by["D"]["harmonic_warning"] is None
    # nothing touched `deployable`
    assert [c["deployable"] for c in cells] == [True, True, False, True]
    # the summary
    assert summary["n_usable"] == 3
    assert summary["n_usable_only_through_harmonics"] == 1
    assert summary["cells_only_through_harmonics"] == [{"channel": "A", "hemisphere": "Left", "rate_hz": 55.0}]
    assert summary["selected_only_through_harmonics"] is True
    assert "1 of 3" in summary["sentence"] and "warning" in summary["sentence"].lower()
    assert "best" in summary["sentence"]                              # names that the selected one is affected


def test_the_summary_is_quiet_when_no_usable_cell_depends_on_a_harmonic():
    cells = [{"rate_hz": 145.0, "qualifying_centers_hz": [20.5], "deployable": True, "channel": "D"}]
    summary = BS.attach_harmonic_warnings(cells, selected=None)
    assert summary["n_usable_only_through_harmonics"] == 0 and summary["sentence"] is None
    assert summary["selected_only_through_harmonics"] is False


def test_the_readiness_screen_never_reassigns_deployable_from_the_harmonic_information():
    """Read off the source: inside the readiness assembly and the helper, `deployable` is read,
    never written, so the warning cannot become a refusal by accident."""
    for fn in (BS.closed_loop_readiness, BS.attach_harmonic_warnings):
        src = inspect.getsource(fn)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant):
                        assert t.slice.value != "deployable", "deployable is assigned in " + fn.__name__
