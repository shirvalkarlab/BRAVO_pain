"""The two D26 capture verdicts -- "inverted capture" and "thresholds too close" -- read the
POOLED TITRATION SLOPE and WARN rather than block. PI decision 2026-09-12, his words "b and c".

What is pinned here, each by the value it produces and not by the shape of the answer:

- a negative, established pooled slope gives neither warning;
- a positive, established slope gives "inverted" as a WARNING and never as a blocker;
- an unresolved slope gives "not yet established" on both verdicts, as warnings;
- no stored slope gives "not assessed" on both, with the between-visit separation reported beside
  them and labelled as the comparison decision 124 distrusts;
- ``is_licensed`` reads none of this: a report that would otherwise be licensed stays licensed
  with a warning present, and a warning never appears in ``blockers``;
- the two threshold VALUES, the two capture amplitudes and the separation number are what the old
  computation gave on the same frames, whichever slope the verdicts are judged on.

The report is built through ``pipeline.run`` on the same stubbed frames ``test_pooled_e1`` uses.
"""
import numpy as np
import pytest

try:
    from modules.ClosedLoopDeployment import (pipeline as PL, adapter as AD, authority as AU,
                                              types as TY)
    from modules.ClosedLoopDeployment.tests.test_pooled_e1 import _row, _toy_table
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import pipeline as PL, adapter as AD, authority as AU, types as TY
    from ClosedLoopDeployment.tests.test_pooled_e1 import _row, _toy_table


def _run(monkeypatch, pooled_e1, T=None):
    T = _toy_table() if T is None else T
    monkeypatch.setattr(AD, "joined_table_cached", lambda *a, **k: T)
    monkeypatch.setattr(PL, "_optional", lambda name: None)      # no device rules, no replay
    return PL.run("p", psd_frame=T.iloc[:1], epochs=T.iloc[:1], design_matrix=None,
                  candidates=[{"channel": "CH", "center_hz": 20.5}], pooled_e1=pooled_e1)


def _d26(sentences):
    return [s for s in sentences if s.startswith("D26 ")]


# --- the four slope cases ------------------------------------------------------------------------
def test_a_negative_established_pooled_slope_gives_neither_d26_warning(monkeypatch):
    rep = _run(monkeypatch, _row(pooled_slope_per_mA=-3.6, pooled_slope_stderr=1.2))
    assert rep.edges["E1"].resolved is True and rep.edges["E1"].sign == -1
    assert rep.warnings == [] and rep.threshold.warnings == []
    assert _d26(rep.blockers) == [] and _d26(rep.threshold.problems) == []
    v = rep.threshold.capture_verdicts
    assert v["assessed"] is True and v["judged_on"] == AU.D26_JUDGED_ON
    assert v["inverted"]["status"] == "not indicated" and v["inverted"]["established"] is True
    assert v["too_close"]["status"] == "not indicated" and v["too_close"]["established"] is True
    assert "NOT indicated" in v["inverted"]["sentence"]
    assert "-3.60 device units per mA" in v["inverted"]["sentence"]
    assert "power falls as current rises, as the control law needs" in v["inverted"]["sentence"]
    assert rep.threshold.predicted_recapture_alert is False


def test_a_positive_established_pooled_slope_gives_inverted_as_a_warning_not_a_blocker(monkeypatch):
    rep = _run(monkeypatch, _row(pooled_slope_per_mA=+3.6, pooled_slope_stderr=1.2))
    assert rep.edges["E1"].resolved is True and rep.edges["E1"].sign == +1
    assert len(rep.warnings) == 1 and rep.warnings == rep.threshold.warnings
    w = rep.warnings[0]
    assert w.startswith("D26 inverted capture: INDICATED")
    assert "+3.60 device units per mA" in w
    assert "power rises as current rises, the opposite of what the control law assumes" in w
    assert "drive the loop the wrong way" in w
    assert _d26(rep.blockers) == [], "the inverted verdict must never be a blocker"
    v = rep.threshold.capture_verdicts
    assert v["inverted"]["status"] == "indicated" and v["inverted"]["established"] is True
    # the response IS established, so "too close" is not indicated even though the sign is wrong
    assert v["too_close"]["status"] == "not indicated"
    assert rep.threshold.predicted_recapture_alert is True


def test_an_unresolved_pooled_slope_gives_not_yet_established_on_both_verdicts_as_warnings(monkeypatch):
    # RCS08's own numbers at the committed band: -4.445 per mA, se such that the interval spans zero
    rep = _run(monkeypatch, _row(pooled_slope_per_mA=-4.445, pooled_slope_stderr=7.23,
                                 pooled_slope_p=0.5387))
    e1 = rep.edges["E1"]
    assert e1.resolved is False and e1.sign == -1
    assert len(rep.warnings) == 2 and rep.warnings == rep.threshold.warnings
    inv, close = rep.warnings
    assert inv.startswith("D26 inverted capture: NOT indicated")
    assert "-4.45 device units per mA" in inv and "though not yet established" in inv
    assert "interval -18.6 to +9.7" in inv and "p 0.54" in inv
    assert close.startswith("D26 thresholds too close: the pooled slope's interval spans zero")
    assert "not yet established" in close and "RECAPTURE THRESHOLDS" in close
    assert _d26(rep.blockers) == []
    v = rep.threshold.capture_verdicts
    assert v["inverted"]["status"] == "not indicated" and v["inverted"]["established"] is False
    assert v["too_close"]["status"] == "not established"
    assert v["pooled_slope_per_mA"] == -4.445 and v["pooled_slope_established"] is False
    assert rep.threshold.predicted_recapture_alert is True


def test_no_pooled_slope_gives_not_assessed_on_both_and_reports_the_distrusted_separation(monkeypatch):
    for pooled in (None, {}, _row(pooled_slope_per_mA=float("nan"))):
        rep = _run(monkeypatch, pooled)
        assert rep.edges["E1"].cluster_unit == "setting epoch", "no swap happened"
        assert len(rep.warnings) == 2
        for w in rep.warnings:
            assert "not assessed -- no pooled titration slope is stored for this band" in w
            assert "between-visit comparison decision 124 distrusts" in w
            assert "it is not the verdict" in w
        assert _d26(rep.blockers) == []
        v = rep.threshold.capture_verdicts
        assert v["assessed"] is False and v["judged_on"] is None
        assert v["inverted"]["status"] == "not assessed"
        assert v["too_close"]["status"] == "not assessed"
        h = v["historical"]
        assert h["label"] == AU.D26_HISTORICAL_LABEL
        # the separation number IS reported, as the same value the plan calls control_authority
        assert h["separation_pooled_sd"] == rep.threshold.control_authority
        assert h["separation_pooled_sd"] is not None
        assert f"{abs(h['separation_pooled_sd']):.2f} pooled standard deviations" in rep.warnings[1]
        # a prediction made from no number would be a fabrication
        assert rep.threshold.predicted_recapture_alert is None


# --- the verdict is not changed by any of this --------------------------------------------------
def _licensed_report(**over):
    e = lambda name, est, lo, hi: TY.EdgeEstimate(name, est, (lo, hi), 0.01, 10, "u", 5)
    rep = TY.DeploymentReport(participant="p")
    rep.eligibility = TY.EligibilityReport(eligible=True, checked=51)
    rep.edges = {"E1": e("E1", -1.0, -1.5, -0.5), "E2": e("E2", 1.0, 0.5, 1.5),
                 "E3": e("E3", -1.0, -1.5, -0.5)}
    rep.coherence = TY.CoherenceReport(coherent=True, p_coherent=0.99)
    for k, v in over.items():
        setattr(rep, k, v)
    return rep


def test_is_licensed_reads_blockers_and_not_warnings():
    assert _licensed_report().is_licensed() is True
    with_warning = _licensed_report(warnings=["D26 inverted capture: INDICATED -- ..."])
    assert with_warning.is_licensed() is True, "a warning gates nothing"
    with_blocker = _licensed_report(blockers=["anything at all"])
    assert with_blocker.is_licensed() is False, "a blocker still blocks"
    d = AD.report_to_dict(with_warning)
    assert d["licensed"] is True and d["verdict"] == "supported"
    assert d["verdict_detail"]["warnings"] == with_warning.warnings
    assert d["verdict_detail"]["blockers"] == []


def test_a_d26_warning_never_lands_in_blockers_whatever_the_slope(monkeypatch):
    for pooled in (None, _row(pooled_slope_per_mA=+3.6), _row(pooled_slope_per_mA=-4.4,
                                                              pooled_slope_stderr=7.0)):
        rep = _run(monkeypatch, pooled)
        assert not any(b.startswith("D26 ") for b in rep.blockers)
        assert all(w.startswith("D26 ") for w in rep.warnings)
        # the serialised form carries both lists side by side
        d = AD.report_to_dict(rep)
        assert d["verdict_detail"]["warnings"] == rep.warnings
        assert d["threshold"]["warnings"] == rep.threshold.warnings
        assert d["threshold"]["capture_verdicts"]["inverted"]["status"] == \
            rep.threshold.capture_verdicts["inverted"]["status"]


def test_the_d27_ceiling_and_the_unmeasurable_spread_still_block():
    """Only the two D26 sentences moved; the other capture problems keep blocking."""
    rng = np.random.default_rng(1)
    lo, hi = rng.normal(10, 1, 30), rng.normal(4, 1, 30)
    e = TY.EdgeEstimate("E1", -3.6, (-6.0, -1.2), 0.01, 13, "run", 4, "power_linear")
    r = AU.threshold_placement(lo, hi, amp_low=1.0, amp_high=6.0, expected_sign=-1,
                               pulse_width_us=200.0, pooled_slope=e)
    assert any("D27" in p and "6.00 mA" in p for p in r.problems)
    assert any("D27" in p and "200" in p for p in r.problems)
    assert r.warnings == []
    r2 = AU.threshold_placement([1.0], [5.0], amp_low=1.0, amp_high=3.0, pooled_slope=e)
    assert any("control authority is not estimable" in p for p in r2.problems)


# --- the numbers the device programs are untouched ----------------------------------------------
def _old_threshold_numbers(T, power_scale="power_linear"):
    """The threshold VALUES exactly as the pipeline computed them before 2026-09-12: the mean band
    power at the lowest therapeutic current on record and at the highest, the larger placed as the
    upper threshold, and the separation between the two samples in pooled standard deviations."""
    d = T[(T.channel == "CH") & np.isclose(T.center_hz, 20.5)].dropna(subset=[power_scale])
    amps = d["amp_mA_Left"].astype(float)
    ther = amps[amps > 0]
    lo_a, hi_a = float(ther.min()), float(ther.max())
    low = d.loc[(amps > 0) & (amps <= lo_a), power_scale].to_numpy()
    high = d.loc[(amps > 0) & (amps >= hi_a), power_scale].to_numpy()
    lo_mean, hi_mean = float(np.mean(low)), float(np.mean(high))
    return {"upper": max(lo_mean, hi_mean), "lower": min(lo_mean, hi_mean),
            "capture_amp_low": lo_a, "capture_amp_high": hi_a,
            "control_authority": AU.control_authority(low, high)}


def test_threshold_values_and_capture_amplitudes_equal_the_old_computation_for_every_slope(monkeypatch):
    T = _toy_table()
    old = _old_threshold_numbers(T)
    seen = []
    for pooled in (None, _row(pooled_slope_per_mA=-3.6), _row(pooled_slope_per_mA=+3.6),
                   _row(pooled_slope_per_mA=-4.4, pooled_slope_stderr=7.0)):
        rep = _run(monkeypatch, pooled, T=T)
        new = {k: getattr(rep.threshold, k) for k in old}
        # field for field, exact, never a tolerance
        assert new == old, f"{pooled and pooled.get('pooled_slope_per_mA')}: {new} != {old}"
        seen.append(new)
    assert all(s == seen[0] for s in seen), "the slope the verdicts read must not move a number"
    assert old["capture_amp_low"] == 1.0 and old["capture_amp_high"] == 3.5
    assert old["upper"] > old["lower"]
