"""Device rule D53: a band is WARNED about when a folded multiple of the stimulation rate lands
inside it or within 5 Hz of its edges. A warning only, never a refusal (the PI, 2026-10-18, decision
485: "make it a warning but not a blocker or not a refusal outright"); it refused for a few hours
that day (decision 481, item 7) and warned before that (decision 220).

At 250 samples a second a whole multiple of the stimulation rate above 125 Hz reappears at a lower
frequency (`Biomarkers.routines.analytics.harmonic_landings_hz`, multiples 1 to 8, the order every
existing caller uses). At 55 Hz the multiples land at 25, 30, 55, 60, 80, 85, 110 and 115 Hz.

Pinned on values: the 55 Hz warning names the rate, the landing and the multiple, and lists rates
that would clear it, and never blocks; 125 Hz (whose multiples fold to 0 or 125 Hz) clears every
adaptive band; the 5 Hz margin is inclusive at its edge; the landings come from the existing
function, not a copy; a missing rate is not determinable (reported, never blocking), and a
sensing-only candidate is not checked; `BRAVO_D53_REFUSES=1` puts the refusal back.
"""
from __future__ import annotations

import numpy as np
import pytest

from ClosedLoopDeployment import constraints

try:
    from Biomarkers.routines import analytics as AN
except ImportError:                                              # pragma: no cover
    from modules.Biomarkers.routines import analytics as AN

from .test_constraints import passing_candidate, resolved_participant


def _cand(rate, centre, **kw):
    return passing_candidate(rate_hz=rate, center_hz=centre, band_width_hz=5.0, **kw)


def test_d53_warns_about_a_band_at_55_hz_where_its_multiples_land_and_names_the_landing():
    c = _cand(55.0, 26.5)                                   # band 24-29 Hz; zone 19-34 Hz
    rep = constraints.check_eligibility(c, resolved_participant())
    rows = [r for r in rep.advisories if r["rule_id"] == "D53" and r["kind"] == "advisory_failed"]
    assert rows, "a landing at 25 Hz inside a 24-29 Hz band must warn"
    obs = rows[0]["observed"]
    assert "55 Hz" in obs and "25 Hz" in obs and "30 Hz" in obs
    assert "multiple 5" in obs and "multiple 4" in obs
    assert rows[0]["resolved_by"] == "configuration"


def test_d53_never_blocks_a_band_it_warns_about():
    c = _cand(55.0, 26.5)
    rep = constraints.check_eligibility(c, resolved_participant())
    assert "D53" not in {r["rule_id"] for r in rep.failures + rep.unknowns}
    clear = constraints.check_eligibility(_cand(125.0, 26.5), resolved_participant())
    # eligibility is what it is at a clearing rate: D53 no longer decides it
    assert rep.eligible == clear.eligible
    assert constraints.RULES_BY_ID["D53"].severity == "advisory"
    assert constraints.FOLDED_RATE_REFUSES is False


def test_d53_the_neutral_setting_puts_the_refusal_back():
    import os, subprocess, sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    code = ("from ClosedLoopDeployment import constraints as c\n"
            "from ClosedLoopDeployment.tests.test_constraints import passing_candidate, resolved_participant\n"
            "rep = c.check_eligibility(passing_candidate(rate_hz=55.0, center_hz=26.5, band_width_hz=5.0), resolved_participant())\n"
            "print(c.RULES_BY_ID['D53'].severity, 'D53' in {r['rule_id'] for r in rep.failures}, rep.eligible)")
    out = subprocess.run([sys.executable, "-c", code], cwd=here, capture_output=True, text=True,
                         env=dict(os.environ, BRAVO_D53_REFUSES="1", PYTHONPATH=here))
    assert out.stdout.split() == ["blocking", "True", "False"], (out.stdout, out.stderr[-2000:])


def test_d53_landings_are_the_existing_functions_not_a_copy(monkeypatch):
    calls = []
    real = AN.harmonic_landings_hz

    def spy(rate, lo, hi, **kw):
        calls.append((rate, lo, hi, kw.get("fs")))
        return real(rate, lo, hi, **kw)
    monkeypatch.setattr(AN, "harmonic_landings_hz", spy)
    chk = constraints.folded_rate_check(55.0, 26.5, 5.0)
    assert calls and calls[0][0] == 55.0 and calls[0][1] == 19.0 and calls[0][2] == 34.0
    assert calls[0][3] == constraints.SAMPLE_RATE_HZ
    want = [d for d in real(55.0, 19.0, 34.0, fs=250.0)]
    assert [(d["harmonic"], d["lands_at_hz"]) for d in chk["landings"]] == \
        [(d["harmonic"], d["lands_at_hz"]) for d in want]


def test_d53_125_hz_clears_every_adaptive_band_because_its_multiples_fold_to_0_or_125_hz():
    for centre in np.arange(10.5, 28.0, 1.0):
        assert constraints._p_d53(_cand(125.0, float(centre)), resolved_participant()) is True


def test_d53_the_5_hz_margin_is_inclusive_at_its_edge():
    # 110 Hz: multiple 7 is 770 Hz, which folds to 20 Hz; multiple 2 folds to 30 Hz.
    assert constraints._p_d53(_cand(110.0, 12.5), resolved_participant()) is False   # 15 + 5 = 20
    assert constraints._p_d53(_cand(110.0, 12.4), resolved_participant()) is True    # 19.9 < 20


def test_d53_lists_the_nearest_rates_that_clear_the_band_and_each_one_does():
    chk = constraints.folded_rate_check(55.0, 26.5, 5.0)
    clear = chk["clearing_rates_hz"]
    assert 0 < len(clear) <= constraints.FOLDED_RATE_CLEARING_SHOWN
    lo, hi = constraints.GENERAL_ENVELOPE["rate_hz"]
    for r in clear:
        assert lo <= r <= hi and r % constraints.FOLDED_RATE_STEP_HZ == 0
        assert constraints.folded_rate_check(r, 26.5, 5.0)["clear"] is True
    # nearest first: no clean rate on the grid is nearer to 55 Hz than the last one listed
    grid = np.arange(constraints.FOLDED_RATE_STEP_HZ, hi + 1e-9, constraints.FOLDED_RATE_STEP_HZ)
    cleanall = [float(r) for r in grid if constraints.folded_rate_check(float(r), 26.5, 5.0)["clear"]]
    nearest = sorted(cleanall, key=lambda r: (abs(r - 55.0), r))[:len(clear)]
    assert clear == nearest


def test_d53_a_missing_rate_is_not_determinable_and_is_reported_not_blocking():
    c = _cand(55.0, 26.5)
    c["rate_hz"] = None
    assert constraints._p_d53(c, resolved_participant()) is None
    rep = constraints.check_eligibility(c, resolved_participant())
    assert "D53" not in {r["rule_id"] for r in rep.unknowns}
    assert ("D53", "advisory_not_determinable") in {(r["rule_id"], r["kind"]) for r in rep.advisories}


def test_d53_does_not_check_a_sensing_only_candidate():
    c = _cand(55.0, 26.5, intent="sensing_only")
    assert constraints._p_d53(c, resolved_participant()) is True


def test_d53_a_pass_is_recorded_with_its_rate_and_nearest_landing():
    rep = constraints.check_eligibility(_cand(125.0, 20.0), resolved_participant())
    rec = [r for r in rep.advisories if r["rule_id"] == "D53" and r["kind"] == "recorded_value"]
    assert rec and "125 Hz" in rec[0]["observed"]


def test_d53_says_which_clearing_rates_the_device_has_run_in_a_brainsense_group_on_that_side(monkeypatch):
    def pairs(uid):
        assert uid == "TEST08"
        return {"Left": {(125.0, 70.0): 2}, "Right": {(50.0, 80.0): 3}}, "synthetic"
    monkeypatch.setattr(constraints._DF, "_programmed_pairs_for", pairs)
    obs = constraints._o_d53(_cand(55.0, 26.5, sensing_hemisphere="Left"), resolved_participant())
    assert "125 Hz (run in a BrainSense group on this side before)" in obs
    assert "50 Hz (run" not in obs


def test_d53_at_55_hz_clears_the_adaptive_centres_10_5_to_16_5_hz_and_warns_at_17_5_to_27_5():
    allowed = [c for c in np.arange(10.5, 28.0, 1.0)
               if constraints._p_d53(_cand(55.0, float(c)), resolved_participant())]
    assert allowed == [10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5]


def test_bad_numeric_input_and_no_visible_harmonics_are_explicit(monkeypatch):
    assert constraints.folded_rate_check(None, 25, 5) is None
    assert constraints.folded_rate_check('bad', 25, 5) is None
    monkeypatch.setattr(constraints, '_harmonic_landings', lambda *a: [])
    assert 'no multiple lands below half' in constraints._o_d53(_cand(250, 20), resolved_participant())


@pytest.mark.parametrize('values', [(float('nan'),20,5),(55,float('inf'),5),(55,20,0),(0,20,5),
                                   (55,-1,5),(55,20,float('nan'))])
def test_invalid_numeric_band_is_unknown_not_clear(values):
    assert constraints.folded_rate_check(*values) is None
    c = _cand(values[0], values[1]);c['band_width_hz'] = values[2]
    assert constraints._p_d53(c,resolved_participant()) is None
    assert 'invalid' in constraints._o_d53(c,resolved_participant())


def test_invalid_margin_cannot_yield_clearing_rates():
    assert constraints.folded_rate_check(55,20,5,margin_hz=-1) is None
    assert constraints.folded_rate_check(55,20,5,margin_hz='bad') is None
