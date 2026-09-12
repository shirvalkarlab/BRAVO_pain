"""Review of 2026-09-12, findings S3 and S4: the gate's band-response check reads the side the
evidence came from, and it applies the SAME rule the readiness screen applies.

Values, not shapes: which side passed, which side is not assessed, which sentence names it, and
that the gate's blocking reasons for a cell are the screen's blocking reasons for the same cell.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import pipeline as PL
from StimOptimizer import stage1_openloop as S1
from StimOptimizer.routines import lfp_evidence as EV
from StimOptimizer.routines import lfp_response as LR
from StimOptimizer.routines import stage_gate as GATE


def _setting(hemisphere, rate_hz=130.0, pw_us=60.0):
    return S1.HemisphereSetting(
        hemisphere=hemisphere, rate_hz=rate_hz, pw_us=pw_us, amp_star_mA=2.0,
        amp_delivered_min_mA=1.0, amp_delivered_max_mA=3.0, n_epochs_fitted=20,
        rate_resolved=True, pw_resolved=True, reasons=("fixture",))


def _frozen(*sides):
    return S1.FrozenConfiguration(
        settings=tuple(_setting(h) for h in sides), primary_item="left_leg",
        incumbent_epoch=1.0, incumbent_rate_hz=55.0, incumbent_pw_us=60.0,
        data_horizon="test", washin_min=1.0, n_epochs_total=40)


def _responding_lfp(hemisphere=None, n=120, seed=0):
    """Magnitude suppressed by amplitude at 13-17 Hz: 19 of the gate's 35 default bands respond
    and carry a significant negative era-blocked slope (measured 2026-09-12), so the cell clears
    the screen's majority rule."""
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.0, 3.0], n // 2)
    freqs = np.arange(4.0, 40.0, 0.5)
    mag = np.abs(rng.normal(1.0, 0.05, (n, freqs.size)))
    sel = (freqs >= 13.0) & (freqs <= 17.0)
    mag[:, sel] *= (np.exp(-0.9 * amp)[:, None] * 3.0)
    return GATE.LfpEvidence(amplitude_mA=amp, magnitude=mag, freqs=freqs,
                            era=np.tile(["a", "b"], n // 2), cluster=np.arange(n),
                            hemisphere=hemisphere)


COND = "adaptive_band_passes_lfp_response"


# ---------------------------------------------------------------------------------------------
# S3: one side's evidence licenses only that side
# ---------------------------------------------------------------------------------------------
def test_left_only_evidence_leaves_the_right_side_not_assessed_and_blocks():
    g = GATE.evaluate_gate(_frozen("Left", "Right"), lfp=_responding_lfp(hemisphere="Left"))
    c = g.condition(COND)
    assert c.passed is None, c.detail
    assert g.passed is False
    per = c.evidence["per_hemisphere"]
    assert per["Left"]["passed"] is True
    assert per["Right"]["passed"] is None
    assert per["Right"]["reason"] == "no evidence for this side"
    assert "Right: NOT ASSESSED" in c.detail and "Left: PASS" in c.detail
    assert c.evidence["top_level_side"] == "Left"
    assert c.evidence["n_passing"] == per["Left"]["n_passing"] == 19


def test_evidence_per_side_for_both_sides_passes():
    lfp = {"Left": _responding_lfp("Left"), "Right": _responding_lfp("Right", seed=1)}
    c = GATE.evaluate_gate(_frozen("Left", "Right"), lfp=lfp).condition(COND)
    assert c.passed is True, c.detail
    per = c.evidence["per_hemisphere"]
    assert per["Left"]["passed"] is True and per["Right"]["passed"] is True
    assert per["Left"]["n_passing"] == 19 and per["Right"]["n_passing"] == 19


def test_one_side_failing_fails_the_condition_even_when_the_other_passes():
    rng = np.random.default_rng(3)
    amp = np.repeat([1.0, 3.0], 60)
    freqs = np.arange(4.0, 40.0, 0.5)
    flat = GATE.LfpEvidence(amplitude_mA=amp, magnitude=np.abs(rng.normal(1.0, 0.05, (120, freqs.size))),
                            freqs=freqs, era=np.tile(["a", "b"], 60), cluster=np.arange(120),
                            hemisphere="Right")
    c = GATE.evaluate_gate(_frozen("Left", "Right"),
                           lfp={"Left": _responding_lfp("Left"), "Right": flat}).condition(COND)
    assert c.passed is False
    assert c.evidence["per_hemisphere"]["Left"]["passed"] is True
    assert c.evidence["per_hemisphere"]["Right"]["passed"] is False
    assert "Right: FAIL" in c.detail


def test_untagged_evidence_is_attributed_to_the_only_frozen_side():
    c = GATE.evaluate_gate(_frozen("Right"), lfp=_responding_lfp(hemisphere=None)).condition(COND)
    assert c.passed is True
    assert list(c.evidence["per_hemisphere"]) == ["Right"]
    assert "attributed to the only frozen side (Right)" in c.evidence["evidence_attribution"]


def test_untagged_evidence_with_two_frozen_sides_is_attributed_to_neither():
    c = GATE.evaluate_gate(_frozen("Left", "Right"), lfp=_responding_lfp(hemisphere=None)).condition(COND)
    assert c.passed is None
    assert c.evidence["per_hemisphere"]["Left"]["passed"] is None
    assert c.evidence["per_hemisphere"]["Right"]["passed"] is None
    assert "attributed to none of them" in c.evidence["evidence_attribution"]


def test_tagged_evidence_never_licenses_the_other_side():
    c = GATE.evaluate_gate(_frozen("Right"), lfp=_responding_lfp(hemisphere="Left")).condition(COND)
    assert c.passed is None
    assert c.evidence["per_hemisphere"]["Right"]["passed"] is None


def test_evidence_by_side_and_for_side_agree():
    left = _responding_lfp("Left")
    by, _ = GATE.evidence_by_side(left, ["Left", "Right"])
    assert by == {"Left": left}
    assert GATE.evidence_for_side(left, "Left") is left
    assert GATE.evidence_for_side(left, "Right") is None
    assert GATE.evidence_for_side({"Right": left}, "Right") is left
    assert GATE.evidence_for_side(None, "Left") is None


def test_the_live_selection_hands_one_cell_per_side_from_one_build():
    """`select_for_side` on a `LiveEvidence` carrying every built cell picks the best
    deployable cell of THAT side at THAT rate; a side with none gets nothing and a reason."""
    left = _responding_lfp("Left")
    cells = {("ONE_THREE_LEFT", "Left", 130.0): left,
             ("ZERO_TWO_RIGHT", "Right", 130.0): _responding_lfp("Right", seed=1)}
    screen = pd.DataFrame([
        dict(channel="ONE_THREE_LEFT", hemisphere="Left", rate_hz=130.0, laterality="ipsilateral",
             responding_fraction=0.6, median_separation_d=2.0, deployable=True),
        dict(channel="ZERO_TWO_RIGHT", hemisphere="Right", rate_hz=130.0, laterality="ipsilateral",
             responding_fraction=0.6, median_separation_d=2.0, deployable=False),
    ])
    ev = PL.LiveEvidence(selected=left, selected_key=("ONE_THREE_LEFT", "Left", 130.0),
                         selection_note="screened best", screen=screen, audit=pd.DataFrame(),
                         cells=cells)
    sel, key, note = PL.select_for_side(ev, "Left", 130.0)
    assert sel is left and key == ("ONE_THREE_LEFT", "Left", 130.0)
    sel, key, note = PL.select_for_side(ev, "Right", 130.0)
    assert sel is None and key is None
    assert note == "no deployable cell on the Right side at 130 Hz (1 screened, none passed)"


# ---------------------------------------------------------------------------------------------
# S4: the gate's rule IS the screen's rule
# ---------------------------------------------------------------------------------------------
BANDS = [(float(c), 5.0) for c in np.arange(10.5, 27.51, 1.0)]        # the cache's 18 bands


def _three_of_eighteen_respond_none_era_negative(n=120, seed=5):
    """3 of 18 bands fall at the high amplitude (direction + separation pass), but era is
    perfectly confounded with amplitude (era a = low, era b = high), so no band can have a
    significant negative era-blocked slope."""
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.0, 3.0], n // 2)
    era = np.repeat(["a", "b"], n // 2)
    bp = {}
    for i, (c, w) in enumerate(BANDS):
        base = np.abs(rng.normal(100.0, 2.0, n))
        if i < 3:
            base = base * np.where(amp > 2.0, 0.5, 1.0)
        bp[(round(c, 6), round(w, 6))] = base
    return GATE.LfpEvidence(amplitude_mA=amp, band_power=bp, era=era, cluster=np.arange(n),
                            hemisphere="Left")


def test_a_cell_the_screen_refuses_is_refused_by_the_gate_for_the_same_reasons():
    ev = _three_of_eighteen_respond_none_era_negative()
    screen, best = EV.screen_cells({("ONE_THREE_LEFT", "Left", 55.0): ev},
                                   response_fn=LR.assess_response)
    assert best is None and bool(screen["deployable"].iloc[0]) is False
    assert int(screen["n_responding"].iloc[0]) == 3
    assert int(screen["n_era_negative_significant"].iloc[0]) == 0
    c = GATE.evaluate_gate(_frozen("Left"), lfp=ev, band_centers=[b[0] for b in BANDS],
                           band_width_hz=5.0).condition(COND)
    assert c.passed is False, c.detail
    side = c.evidence["per_hemisphere"]["Left"]
    assert side["n_passing"] == 3 and side["n_era_negative_significant"] == 0
    # the SAME sentences, word for word
    assert "; ".join(side["rule_blocking_reasons"]) == screen["blocking_reasons"].iloc[0]
    assert "only 3 of 18 bands respond" in c.detail


def test_the_shared_rule_counts_both_majorities():
    ev = _responding_lfp("Left")
    res = [LR.assess_response(ev.power_for(c, 5.0), ev.amplitude_mA, era=ev.era, cluster=ev.cluster)
           for c in GATE.DEFAULT_BAND_CENTERS_HZ]
    v = EV.cell_response_verdict(res)
    assert v["n_bands"] == 35 and v["n_responding"] == 19 and v["n_era_negative_significant"] == 19
    assert v["responds"] is True and v["blocking_reasons"] == []
    assert EV.cell_response_verdict([])["responds"] is None


def test_verdict_rows_carry_the_era_blocked_flag_for_the_strip():
    c = GATE.evaluate_gate(_frozen("Left"), lfp=_responding_lfp("Left")).condition(COND)
    rows = c.evidence["verdict_rows"]
    assert len(rows) == 35
    flagged = [r["center_hz"] for r in rows if r["era_negative_significant"]]
    responding = [r["center_hz"] for r in rows if r["responds"]]
    assert flagged == responding == [float(v) for v in np.arange(10.5, 19.51, 0.5)]
    assert rows[0]["era_negative_significant"] is True and rows[-1]["era_negative_significant"] is False


def test_the_page_counts_come_from_the_screen_rule():
    """Once a cell passes, the condition's numbers are the screen's: the passing count AND the
    negative-slope count, and the sentence carries both."""
    c = GATE.evaluate_gate(_frozen("Left"), lfp=_responding_lfp("Left")).condition(COND)
    assert c.passed is True
    assert "19 of 35 tested bands respond and 19 of 35 carry a significant negative era-blocked slope" in c.detail
    assert c.evidence["n_era_negative_significant"] == 19
