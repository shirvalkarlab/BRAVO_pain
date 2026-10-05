"""E1, the current-to-power edge, from the stored pooled titration slope (redesign decision 9,
decision 124 in the log, the PI's choice on 2026-09-11).

Two rules held here: the pipeline swaps E1 for the pooled slope ONLY when a slope is stored, and
keeps the historical setting-epoch estimate on the report beside it; and the curvature answer
travels in the edge's note as a caveat, never as a second number the sign test could read.

Merged here 2026-10-05: test_d26_reads_pooled_slope.py.
"""
import numpy as np
import pandas as pd
import pytest

try:
    from modules.ClosedLoopDeployment import pipeline as PL, edges as E, adapter as AD
    from modules.ClosedLoopDeployment import authority as AU, types as TY
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import pipeline as PL, edges as E, adapter as AD
    from ClosedLoopDeployment import authority as AU, types as TY


def _row(**over):
    r = {"pooled_direction": "band power falls as current rises", "pooled_slope_per_mA": -3.6,
         "pooled_slope_stderr": 1.2, "pooled_slope_p": 0.01, "n": 13, "n_visits": 4,
         "verdict": "ok", "curves": False, "peaks_inside": False, "peak_mA": float("nan"),
         "p_curvature": 0.41, "r2_linear": 0.6, "r2_quadratic": 0.61}
    r.update(over)
    return r


def test_the_pooled_edge_carries_the_slope_its_interval_and_the_run_count():
    e = E.pooled_actuation_edge(_row(), scale="power_linear")
    assert e.name == "E1" and e.estimate == -3.6 and e.p == 0.01
    assert e.ci == (-3.6 - 1.96 * 1.2, -3.6 + 1.96 * 1.2)
    assert e.n == 13 and e.n_clusters == 4 and "run of stepped current" in e.cluster_unit
    assert e.sign == -1 and e.resolved is True
    assert "POOLED ACROSS 4 RUNS" in e.note and "No bend was detected" in e.note
    assert e.confounded_by == []


def test_a_detected_bend_is_a_caveat_in_the_note_and_a_named_confounder_never_a_number():
    e = E.pooled_actuation_edge(_row(curves=True, p_curvature=0.004, peaks_inside=True, peak_mA=2.6))
    assert "bend across the tested currents was detected (p = 0.004)" in e.note
    assert "peak near 2.6 mA" in e.note
    assert "curvature" in e.confounded_by
    assert e.estimate == -3.6, "the slope itself is untouched; the bend qualifies it in words"


def test_no_stored_slope_gives_an_unresolved_edge_that_says_why():
    e = E.pooled_actuation_edge(_row(pooled_slope_per_mA=float("nan"), pooled_slope_p=float("nan"),
                                     verdict="not assessed: 5 usable points"))
    assert e.estimate is None and e.resolved is False
    assert "not assessed: 5 usable points" in e.note


def test_few_runs_are_named_as_a_confounder():
    e = E.pooled_actuation_edge(_row(n_visits=2))
    assert "few runs" in e.confounded_by


def _toy_table(n_epochs=6, per_epoch=5, slope=-2.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_epochs):
        amp = 1.0 + k * 0.5
        for _ in range(per_epoch):
            lin = 10.0 + slope * amp + rng.normal(0, 0.2)
            rows.append({"t": float(k), "channel": "CH", "setting_epoch": k, "center_hz": 20.5,
                         "amp_mA_Left": amp, "power_linear": lin,
                         # the manifest's scale check reads both scales; the pipeline is the
                         # thing under test, so the table carries what the real one carries
                         "nrs": 5.0 + 0.5 * amp + rng.normal(0, 0.2), "report_id": f"r{k}"})
    return pd.DataFrame(rows)


def _run_pipeline(monkeypatch, pooled_e1):
    T = _toy_table()
    monkeypatch.setattr(AD, "joined_table_cached", lambda *a, **k: T)
    monkeypatch.setattr(PL, "_optional", lambda name: None)      # no device rules, no replay
    return PL.run("p", psd_frame=pd.DataFrame({"x": [1]}), epochs=pd.DataFrame({"x": [1]}),
                  design_matrix=None, candidates=[{"channel": "CH", "center_hz": 20.5}],
                  pooled_e1=pooled_e1)


def test_the_pipeline_uses_the_pooled_slope_and_keeps_the_historical_edge(monkeypatch):
    rep = _run_pipeline(monkeypatch, _row())
    assert rep.edges["E1"].estimate == -3.6
    assert "run of stepped current" in rep.edges["E1"].cluster_unit
    hist = rep.edges_historical["E1"]
    assert hist.cluster_unit == "setting epoch", "the setting-epoch estimate must be kept"
    assert hist.estimate is not None and hist.estimate != -3.6


def test_without_a_stored_slope_the_pipeline_keeps_the_setting_epoch_edge(monkeypatch):
    for pooled in (None, {}, _row(pooled_slope_per_mA=float("nan"))):
        rep = _run_pipeline(monkeypatch, pooled)
        assert rep.edges["E1"].cluster_unit == "setting epoch"
        assert rep.edges_historical == {}


# ---------------------------------------------------------------------------------------------
# Review 2026-09-15, finding C1: E1 must SAY which estimate it is, so a page can draw the
# screening statistic differently from the pooled titration slope
# ---------------------------------------------------------------------------------------------
def test_e1_without_a_stored_slope_names_itself_the_screening_statistic(monkeypatch):
    rep = _run_pipeline(monkeypatch, None)
    assert rep.edges["E1"].source == "screening_historical"


def test_the_response_carries_the_source_of_every_edge(monkeypatch):
    """The page reads the dict, not the dataclass: `source` has to survive serialisation on the live
    edge. The historical edge kept beside it stays on the report object only since 2026-09-23 (panel
    D item 10: nothing read it on the response); `test_unread_fields_leave_the_response.py` pins that."""
    rep = _run_pipeline(monkeypatch, _row())
    d = AD.report_to_dict(rep)
    assert d["edges"]["E1"]["source"] == "pooled_titration"
    assert rep.edges_historical["E1"].source == "screening_historical"
    # E2 and E3 are neither: they carry the key so a reader never has to guess whether it exists
    assert "source" in d["edges"]["E2"] and d["edges"]["E2"]["source"] is None

# ------------------------------------------------------------------------------------------------
# The two D26 capture verdicts read the pooled slope (from test_d26_reads_pooled_slope.py,
# merged 2026-10-05)
# ------------------------------------------------------------------------------------------------
# The two D26 capture verdicts -- "inverted capture" and "thresholds too close" -- read the
# POOLED TITRATION SLOPE and WARN rather than block. PI decision 2026-09-12, his words "b and c".
#
# What is pinned here, each by the value it produces and not by the shape of the answer:
#
# - a negative, established pooled slope gives neither warning;
# - a positive, established slope gives "inverted" as a WARNING and never as a blocker;
# - a slope whose interval spans zero, with the right sign, gives BOTH verdicts "not indicated" on
#   the point sign, each carrying the interval and p as a CAVEAT, as warnings that gate nothing
#   (PI rule 2026-09-13, "established means mean only": the verdict follows the sign);
# - no stored slope gives "not assessed" on both, with the between-visit separation reported beside
#   them and labelled as the comparison decision 124 distrusts;
# - ``is_licensed`` reads none of this: a report that would otherwise be licensed stays licensed
#   with a warning present, and a warning never appears in ``blockers``;
# - the two threshold VALUES, the two capture amplitudes and the separation number are what the old
#   computation gave on the same frames, whichever slope the verdicts are judged on.
#
# The report is built through ``pipeline.run`` on the same stubbed frames as the tests above.


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
    assert rep.edges["E1"].resolved is True and rep.edges["E1"].statistically_established is True
    assert rep.edges["E1"].sign == -1
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
    assert rep.edges["E1"].resolved is True and rep.edges["E1"].statistically_established is True
    assert rep.edges["E1"].sign == +1
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


def test_a_pooled_slope_whose_interval_spans_zero_is_judged_on_its_sign_with_the_caveat_as_warnings(monkeypatch):
    """PI rule 2026-09-13, his words "Established means mean only for flexibility", read as
    "point sign decides, but flag as provisional". Until that date this slope -- RCS08's own
    -4.445 per mA with an interval spanning zero -- gave "too close: not established" and raised
    the predicted RECAPTURE THRESHOLDS alert. Now both verdicts follow the point sign (right way,
    so neither is indicated and no alert is predicted), and the interval and p travel on both
    sentences as a CAVEAT, which lands in the warnings so it is on the page and gates nothing."""
    rep = _run(monkeypatch, _row(pooled_slope_per_mA=-4.445, pooled_slope_stderr=7.23,
                                 pooled_slope_p=0.5387))
    e1 = rep.edges["E1"]
    assert e1.resolved is True and e1.sign == -1, "the point sign resolves the edge"
    assert e1.statistically_established is False, "the interval spans zero: the caveat"
    assert len(rep.warnings) == 2 and rep.warnings == rep.threshold.warnings
    inv, close = rep.warnings
    assert inv.startswith("D26 inverted capture: NOT indicated")
    assert "-4.45 device units per mA" in inv
    assert "CAVEAT: the interval spans zero (interval -18.6 to +9.7, p 0.54)" in inv
    assert "not statistically established" in inv
    assert close.startswith("D26 thresholds too close: NOT indicated")
    assert "CAVEAT: the interval spans zero (interval -18.6 to +9.7, p 0.54)" in close
    assert "RECAPTURE THRESHOLDS" in close and "that is a caveat, not the verdict" in close
    assert _d26(rep.blockers) == []
    v = rep.threshold.capture_verdicts
    assert v["inverted"]["status"] == "not indicated" and v["inverted"]["established"] is False
    assert v["too_close"]["status"] == "not indicated" and v["too_close"]["established"] is False
    assert v["pooled_slope_per_mA"] == -4.445 and v["pooled_slope_established"] is False
    assert rep.threshold.predicted_recapture_alert is False, "the alert follows the sign"


def test_an_inverted_pooled_slope_whose_interval_spans_zero_is_still_indicated_on_its_sign(monkeypatch):
    """The other half of the same rule: a wrong-way point sign is "inverted" whether or not the
    interval excludes zero; the caveat says the sign is not statistically established, and the
    alert is predicted because the verdict follows the sign."""
    rep = _run(monkeypatch, _row(pooled_slope_per_mA=+2.0, pooled_slope_stderr=3.0,
                                 pooled_slope_p=0.5))
    assert rep.edges["E1"].sign == +1 and rep.edges["E1"].statistically_established is False
    v = rep.threshold.capture_verdicts
    assert v["inverted"]["status"] == "indicated" and v["inverted"]["established"] is False
    assert v["inverted"]["sentence"].startswith("D26 inverted capture: INDICATED")
    assert "CAVEAT: the interval spans zero" in v["inverted"]["sentence"]
    assert v["too_close"]["status"] == "not indicated"
    assert rep.threshold.predicted_recapture_alert is True
    assert _d26(rep.blockers) == [], "still a warning, never a blocker"


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


def test_the_capture_artefact_ceiling_and_the_unmeasurable_spread_still_block():
    """Only the two D26 sentences moved; the other capture problems keep blocking. (Since review
    C10, 2026-09-12, the ceiling sentences name the PROPOSED capture amplitude and no longer begin
    "D27:", because the ledger's D27 row judges a different amplitude -- test_core pins the
    wording; this pins that they still block.)"""
    rng = np.random.default_rng(1)
    lo, hi = rng.normal(10, 1, 30), rng.normal(4, 1, 30)
    e = TY.EdgeEstimate("E1", -3.6, (-6.0, -1.2), 0.01, 13, "run", 4, "power_linear")
    r = AU.threshold_placement(lo, hi, amp_low=1.0, amp_high=6.0, expected_sign=-1,
                               pulse_width_us=200.0, pooled_slope=e)
    assert any("artefact ceiling" in p and "6.00 mA" in p for p in r.problems)
    assert any("artefact ceiling" in p and "200 us" in p for p in r.problems)
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
