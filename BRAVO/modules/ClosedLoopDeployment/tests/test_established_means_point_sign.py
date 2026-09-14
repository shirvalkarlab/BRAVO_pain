"""The PI's rule of 2026-09-13, his words: "Established means mean only for flexibility."

Put to him as three readings, he chose "point sign decides, but flag as provisional":

- an edge is RESOLVED by the sign of its point estimate alone (``EdgeEstimate.resolved``);
- whether its interval excludes zero is a CAVEAT (``statistically_established``) that every page
  and ledger row prints beside the sign and that gates nothing;
- a report licensed while any interval spans zero is PROVISIONAL, and its serialised verdict
  reads "supported (point signs only; N of 3 intervals span zero)";
- decision 9 still holds: an edge with NO estimate (None or NaN) has no sign, is unresolved and
  still blocks; a wrong-way sign still blocks through the sign-agreement test.

Every case here is pinned on the value it produces, never on the shape of the answer.
"""
import math

try:
    from modules.ClosedLoopDeployment import (adapter as AD, authority as AU, consistency as C,
                                              pipeline as PL, types as TY)
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import (adapter as AD, authority as AU, consistency as C,
                                      pipeline as PL, types as TY)

from ClosedLoopDeployment.types import EdgeEstimate


def _e(name, est, ci, p=0.5):
    return EdgeEstimate(name, est, ci, p, 10, "u", 5)


# --- the edge --------------------------------------------------------------------------------------
def test_an_edge_with_a_nonzero_estimate_and_an_interval_spanning_zero_is_resolved_and_not_established():
    """RCS08's E1 at the band in the PI's browser on 2026-09-13: -3.79 per mA, interval -12.5 to
    +4.93, p 0.42. Under the old rule it was unresolved; under his rule it has a sign."""
    e = _e("E1", -3.788, (-12.505, 4.929), 0.419)
    assert e.sign == -1
    assert e.resolved is True
    assert e.statistically_established is False


def test_an_edge_whose_interval_excludes_zero_is_resolved_and_established():
    e = _e("E3", -0.154, (-0.269, -0.039), 0.0086)
    assert e.sign == -1 and e.resolved is True and e.statistically_established is True


def test_an_edge_with_no_estimate_is_unresolved_whatever_its_interval():
    """Decision 9: absence of evidence is not permission. None and NaN both mean "no estimate";
    a NaN used to read as sign -1 because ``nan > 0`` is False, which mattered nowhere while the
    interval gated and would have mattered everywhere once the sign alone did."""
    for est in (None, float("nan")):
        e = _e("E2", est, None, None)
        assert e.sign is None, est
        assert e.resolved is False, est
        assert e.statistically_established is False, est
    with_ci = _e("E2", float("nan"), (-1.0, 1.0), 0.5)
    assert with_ci.sign is None and with_ci.resolved is False


def test_an_estimate_of_exactly_zero_has_no_direction_and_is_unresolved():
    e = _e("E1", 0.0, (-1.0, 1.0), 0.99)
    assert e.sign == 0 and e.resolved is False and e.statistically_established is False


def test_an_edge_with_a_nonzero_estimate_and_no_interval_is_resolved_and_not_established():
    """An unbounded interval (four setting epochs, ``edges.actuation_edge``) is "no interval"."""
    e = _e("E1", -2.0, None, 0.125)
    assert e.resolved is True and e.statistically_established is False


# --- the report ------------------------------------------------------------------------------------
def _report(edges, eligible=True):
    rep = TY.DeploymentReport(participant="p")
    rep.eligibility = TY.EligibilityReport(eligible=eligible, checked=51)
    rep.edges = edges
    rep.coherence = C.coherence_report(edges["E1"], edges["E2"], edges["E3"])
    return rep


def _right_signs_all_spanning_zero():
    return {"E1": _e("E1", -3.788, (-12.505, 4.929), 0.419),
            "E2": _e("E2", 0.058, (-0.083, 0.197), 0.46),
            "E3": _e("E3", -0.10, (-0.30, 0.10), 0.30)}


def _right_signs_all_established():
    return {"E1": _e("E1", -3.6, (-6.0, -1.2), 0.01),
            "E2": _e("E2", 0.22, (0.11, 0.33), 0.001),
            "E3": _e("E3", -0.154, (-0.269, -0.039), 0.0086)}


def test_three_right_signs_all_spanning_zero_is_licensed_and_provisional_with_three_unestablished():
    rep = _report(_right_signs_all_spanning_zero())
    assert rep.coherence.coherent is True
    assert rep.is_licensed() is True
    assert rep.n_edges_unestablished == 3
    assert rep.provisional is True


def test_three_right_signs_all_established_is_licensed_and_not_provisional():
    rep = _report(_right_signs_all_established())
    assert rep.is_licensed() is True
    assert rep.n_edges_unestablished == 0
    assert rep.provisional is False


def test_two_of_three_spanning_zero_counts_two():
    """RCS08's own pattern on 2026-09-13 at both bands measured: E1 and E2 span zero, E3 does not."""
    edges = _right_signs_all_spanning_zero()
    edges["E3"] = _e("E3", -0.154, (-0.269, -0.039), 0.0086)
    rep = _report(edges)
    assert rep.is_licensed() is True and rep.provisional is True
    assert rep.n_edges_unestablished == 2
    d = AD.report_to_dict(rep)
    assert d["verdict"] == "supported (point signs only; 2 of 3 intervals span zero)"
    assert d["verdict_detail"]["unestablished_edges"] == ["E1", "E2"]


def test_one_wrong_way_sign_is_not_licensed_whatever_the_intervals():
    """The sign-agreement test still refuses a positive-feedback band: E1 positive means the
    device ramps up, power rises, and it ramps up again. Intervals do not rescue it either way."""
    for ci in ((0.5, 3.5), (-1.0, 5.0)):                      # established, and spanning zero
        edges = _right_signs_all_established()
        edges["E1"] = _e("E1", 2.0, ci, 0.3)
        rep = _report(edges)
        assert rep.coherence.coherent is False, ci
        assert rep.is_licensed() is False, ci
        assert rep.provisional is False, "an unlicensed report is never provisional"
        d = AD.report_to_dict(rep)
        assert d["verdict"] == "unsupported" and d["licensed"] is False


def test_an_edge_with_no_estimate_still_blocks_the_verdict():
    edges = _right_signs_all_established()
    edges["E2"] = _e("E2", None, None, None)
    rep = _report(edges)
    assert rep.coherence.coherent is None
    assert rep.is_licensed() is False and rep.provisional is False
    assert AD.report_to_dict(rep)["verdict"] == "unsupported"


def test_a_device_refusal_still_reads_blocked_not_provisional():
    rep = _report(_right_signs_all_spanning_zero(), eligible=False)
    d = AD.report_to_dict(rep)
    assert d["verdict"] == "blocked" and d["licensed"] is False
    assert d["verdict_detail"]["provisional"] is False


# --- the serialised verdict and caveats ----------------------------------------------------------
def test_the_serialised_verdict_string_for_the_provisional_case_reads_exactly_as_agreed():
    d = AD.report_to_dict(_report(_right_signs_all_spanning_zero()))
    assert d["verdict"] == "supported (point signs only; 3 of 3 intervals span zero)"
    assert d["licensed"] is True
    vd = d["verdict_detail"]
    assert vd["provisional"] is True and vd["n_edges_unestablished"] == 3 and vd["n_edges"] == 3
    assert vd["all_edges_resolved"] is True and vd["all_edges_statistically_established"] is False
    assert vd["unestablished_edges"] == ["E1", "E2", "E3"]
    for k in ("E1", "E2", "E3"):
        assert d["edges"][k]["resolved"] is True
        assert d["edges"][k]["statistically_established"] is False
    assert "PROVISIONAL: 3 of 3 intervals span zero" in d["coherence"]["note"]


def test_the_serialised_verdict_string_for_the_established_case_is_plain_supported():
    d = AD.report_to_dict(_report(_right_signs_all_established()))
    assert d["verdict"] == "supported"
    vd = d["verdict_detail"]
    assert vd["provisional"] is False and vd["n_edges_unestablished"] == 0
    assert vd["unestablished_edges"] == [] and vd["all_edges_statistically_established"] is True
    assert "PROVISIONAL" not in d["coherence"]["note"]


# --- D19 and D26 -----------------------------------------------------------------------------------
def test_d19_facts_carry_the_point_sign_and_the_established_flag_reads_the_interval():
    e1 = _e("E1", -3.788, (-12.505, 4.929), 0.419)
    e2 = _e("E2", 0.22, (0.11, 0.33), 0.001)
    f = PL._facts_for({}, e1, e2, "power_linear")
    assert f["power_slope_vs_amplitude_sign"] == -1
    assert f["power_slope_vs_amplitude_sign_established"] is False
    assert f["power_slope_vs_pain_sign"] == 1
    assert f["power_slope_vs_pain_sign_established"] is True


def test_d26_verdicts_follow_the_sign_and_carry_the_caveat():
    """Right-way slope, interval spanning zero: neither verdict indicated, no alert predicted,
    both sentences carry the caveat with the numbers. Wrong-way slope: inverted, alert predicted,
    caveat still present when the interval spans zero."""
    right = _e("E1", -3.788, (-12.505, 4.929), 0.419)
    v, warnings, alert = AU.d26_capture_verdicts(right)
    assert v["inverted"]["status"] == "not indicated" and v["too_close"]["status"] == "not indicated"
    assert v["pooled_slope_established"] is False
    assert alert is False
    assert len(warnings) == 2
    for w in warnings:
        assert "CAVEAT: the interval spans zero (interval -12.5 to +4.9, p 0.42)" in w
    wrong = _e("E1", +3.788, (-4.929, 12.505), 0.419)
    v, warnings, alert = AU.d26_capture_verdicts(wrong)
    assert v["inverted"]["status"] == "indicated" and alert is True
    assert v["inverted"]["sentence"].startswith("D26 inverted capture: INDICATED")
    assert "CAVEAT" in v["inverted"]["sentence"]
    established = _e("E1", -3.6, (-6.0, -1.2), 0.01)
    v, warnings, alert = AU.d26_capture_verdicts(established)
    assert warnings == [] and alert is False
    assert "CAVEAT" not in v["inverted"]["sentence"] and "CAVEAT" not in v["too_close"]["sentence"]
