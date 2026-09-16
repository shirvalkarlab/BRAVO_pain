"""The display fields the Stim Optimizer page reads (2026-09-12, the page redesign, phase 3).

What these tests hold: the setting in force is reported PER SIDE from each side's own columns --
the right pulse width is the right column's value, never the left's, and an absent column is None
rather than the other side's number; the programmed cathode contacts are labelled in the page's
Medtronic form with a whole ring collapsed to its digit and no anode invented; a sensing contact
pair carries the same `display_short` the Biomarkers formatter prints everywhere else, taken from
that formatter and not re-derived; the band-response check's evidence carries the verdicts as
numbers equal, field for field, to the sentences' source; and the current-limits check names the
sides whose limits were defaulted.
"""
import math

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import bravo_service as BS
from StimOptimizer.routines import lfp_response as LFP
from StimOptimizer.routines import stage_gate as GATE


def _frame():
    d = pd.DataFrame([
        dict(epoch=122.0, freq_hz=55.0, amp_mA_Left=2.5, amp_mA_Right=2.0, pw_us_Left=60.0,
             pw_us_Right=60.0, cathode_Left="1a-1b-1c", cathode_Right="1a-1b-1c",
             t_start=pd.Timestamp("2026-08-01", tz="UTC")),
        dict(epoch=123.0, freq_hz=55.0, amp_mA_Left=3.0, amp_mA_Right=2.5, pw_us_Left=100.0,
             pw_us_Right=150.0, cathode_Left="2a-2b-2c", cathode_Right="1a-1b-1c-2a-2b-2c",
             t_start=pd.Timestamp("2026-09-03 20:07:11", tz="UTC")),
    ])
    d["t0"] = d["t_start"]
    return d


def test_each_side_reports_its_own_pulse_width_and_contacts_from_the_newest_epoch():
    out = BS.in_force_by_side(_frame())
    assert set(out) == {"Left", "Right"}
    assert out["Left"]["pulse_width_us"] == 100.0
    assert out["Right"]["pulse_width_us"] == 150.0          # the right column, not the left's 100
    assert out["Left"]["amplitude_mA"] == 3.0 and out["Right"]["amplitude_mA"] == 2.5
    assert out["Left"]["rate_hz"] == 55.0 and out["Right"]["rate_hz"] == 55.0
    assert out["Left"]["contacts_raw"] == "2a-2b-2c"
    assert out["Left"]["contacts_short"] == "L C+2-"
    assert out["Right"]["contacts_raw"] == "1a-1b-1c-2a-2b-2c"
    assert out["Right"]["contacts_short"] == "R C+1-2-"
    assert out["Left"]["epoch"] == 123.0 and out["Right"]["epoch"] == 123.0


def test_an_absent_column_is_none_never_the_other_sides_value():
    d = _frame().drop(columns=["pw_us_Right", "cathode_Right"])
    out = BS.in_force_by_side(d)
    assert out["Right"]["pulse_width_us"] is None
    assert out["Right"]["contacts_short"] is None and out["Right"]["contacts_raw"] is None
    assert out["Left"]["pulse_width_us"] == 100.0


def test_no_epochs_means_an_empty_block():
    assert BS.in_force_by_side(None) == {}
    assert BS.in_force_by_side(pd.DataFrame()) == {}


@pytest.mark.parametrize("cathode,side,expected", [
    ("2a-2b-2c", "Left", "L C+2-"),
    ("1a-1b-1c-2a-2b-2c", "Right", "R C+1-2-"),
    ("1a-1b", "Left", "L C+1a-1b-"),        # a partly used ring keeps its segments
    ("0", "Right", "R C+0-"),                   # a non-segmented contact
    ("none", "Left", None),
    ("", "Left", None),
    (None, "Left", None),
    (float("nan"), "Left", None),
])
def test_the_cathode_label_collapses_a_whole_ring_and_invents_no_anode(cathode, side, expected):
    assert BS.stim_contacts_short(cathode, side) == expected


def test_the_sensing_label_is_the_biomarkers_formatter_output_not_a_local_copy():
    try:
        from Biomarkers.routines import analytics as _an
    except ImportError:
        pytest.skip("the Biomarkers formatter is not importable on this runner")
    for raw in ("ZERO_TWO_LEFT", "ONE_THREE_LEFT", "ZERO_THREE_RIGHT"):
        got = BS.sensing_display(raw)
        ref = _an.format_channel(raw, region="")
        assert got == {"display_short": ref["short"], "display_hemisphere": ref["hemisphere"],
                       "display_contacts": ref["contacts"]}
    assert BS.sensing_display("ZERO_TWO_LEFT")["display_short"] == "L 0⁻2⁺"


def test_the_verdict_rows_equal_the_response_results_field_for_field():
    r = LFP.ResponseResult(responds=True, reason="x", n_low=3, n_high=4, amp_low_mA=1.5,
                           amp_high_mA=4.5, power_low=229.7, power_high=137.1,
                           separation_d=1.83, separation_d_on_log=2.37, slope_log_per_mA=-0.3251,
                           slope_p=0.0)
    row = GATE.verdict_row(23.5, r)
    assert row["center_hz"] == 23.5 and row["responds"] is True
    assert row["separation_d"] == 1.83 and row["separation_d_on_log"] == 2.37
    assert row["power_low"] == 229.7 and row["power_high"] == 137.1
    assert row["amp_low_mA"] == 1.5 and row["amp_high_mA"] == 4.5
    assert row["slope_log_per_mA"] == -0.3251 and row["slope_p"] == 0.0
    assert row["n_low"] == 3 and row["n_high"] == 4 and row["reason"] == "x"
    nan = LFP.ResponseResult(responds=None, reason="not assessed")
    row2 = GATE.verdict_row(10.5, nan)
    assert row2["responds"] is None and row2["separation_d"] is None and row2["power_low"] is None


def _responding_lfp(n=120, seed=0):
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.0, 3.0], n // 2)
    freqs = np.arange(4.0, 40.0, 0.5)
    mag = np.abs(rng.normal(1.0, 0.05, (n, freqs.size)))
    sel = (freqs >= 13.0) & (freqs <= 17.0)
    mag[:, sel] *= (np.exp(-0.9 * amp)[:, None] * 3.0)
    return GATE.LfpEvidence(amplitude_mA=amp, magnitude=mag, freqs=freqs,
                            era=np.tile(["a", "b"], n // 2), cluster=np.arange(n))


def _frozen():
    from StimOptimizer import stage1_openloop as S1
    hs = S1.HemisphereSetting(hemisphere="Left", rate_hz=55.0, pw_us=100.0, amp_star_mA=3.0,
                              amp_delivered_min_mA=1.0, amp_delivered_max_mA=4.8,
                              n_epochs_fitted=11, rate_resolved=False, pw_resolved=False,
                              reasons=(), detail={})
    return S1.FrozenConfiguration(settings=(hs,), primary_item="left_leg_vas",
                                  incumbent_epoch=123.0, incumbent_rate_hz=55.0,
                                  incumbent_pw_us=100.0, data_horizon="test", washin_min=1.0,
                                  n_epochs_total=92)


def test_the_band_check_evidence_carries_the_rows_the_floor_and_the_best_centre():
    c = GATE.check_adaptive_band(_frozen(), lfp=_responding_lfp())
    ev = c.evidence
    assert isinstance(ev.get("verdict_rows"), list) and ev["verdict_rows"]
    assert set(ev["verdicts"].keys()) == {r["center_hz"] for r in ev["verdict_rows"]}
    assert ev["min_sep_d"] == float(LFP.MIN_CAPTURE_SEPARATION_D)
    if c.passed is True:
        assert ev["best_center_hz"] in ev["passing_centers"]
        best = max((r for r in ev["verdict_rows"] if r["responds"] is True),
                   key=lambda r: r["separation_d"] if r["separation_d"] is not None else -math.inf)
        assert best["center_hz"] == ev["best_center_hz"]
    for r in ev["verdict_rows"]:
        sentence = ev["verdicts"][r["center_hz"]]
        assert (r["responds"] is True) == sentence.startswith("RESPONDS")


def test_the_limits_check_names_the_defaulted_sides_in_its_evidence():
    c = GATE.check_amplitude_limits(_frozen())
    assert c.evidence["defaulted"] == ["Left"]
    c2 = GATE.check_amplitude_limits(_frozen(), amp_limits={"Left": (1.0, 4.0)})
    assert c2.evidence["defaulted"] == []


def test_the_notation_is_the_clinic_sheets_own_case_positive_then_cathodes_with_a_hyphen():
    """Read off the lab's 2026-09-16 visit sheet ("L C+2- / R C+1-2-"): the case (C) is the
    anode, each cathode contact carries a plain hyphen, no space after "C+", never a superscript.
    Monopolar on the left, double monopolar on the right."""
    from StimOptimizer import bravo_service as BS
    assert BS.stim_contacts_short("2a-2b-2c", "Left") == "L C+2-"
    assert BS.stim_contacts_short("1a-1b-1c-2a-2b-2c", "Right") == "R C+1-2-"
    assert "\u207b" not in BS.stim_contacts_short("2a-2b-2c", "Left")
