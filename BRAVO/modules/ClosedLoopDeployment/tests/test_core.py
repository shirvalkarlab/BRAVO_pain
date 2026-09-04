"""Core tests: the joined table, the edges, coherence, authority and the ledger."""
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import adapter as AD, edges as E, consistency as C, authority as AU
from ClosedLoopDeployment.types import EdgeEstimate
from ClosedLoopDeployment.registry import Registry


# --- Phase 0 ------------------------------------------------------------------------------------
def test_linear_band_power_is_the_arithmetic_mean_not_the_exponentiated_mean_of_logs():
    """The distinction that motivates carrying both scales. On a peaked band the arithmetic mean of
    linear bin powers exceeds the geometric mean substantially, and rule D11 says the DEVICE uses
    the linear one while the biomarker pipeline validated on mean-of-log."""
    f = np.arange(8.0, 31.0, 1.0)
    lp = np.zeros(f.size)
    lp[(f >= 18) & (f < 23)] = [0.0, 10.0, 20.0, 10.0, 0.0]
    lin, log_of_lin, mean_of_log = AD.band_powers(lp, f, centers=(20.5,), width=5.0)
    assert log_of_lin[20.5] > mean_of_log[20.5] + 3.0, "the two scales must actually differ here"
    # and the linear value really is the arithmetic mean of the linear bins
    m = (f >= 18.0) & (f < 23.0)
    assert lin[20.5] == pytest.approx(np.mean(np.power(10.0, lp[m] / 10.0)))


def test_band_powers_rejects_a_mismatched_frequency_axis():
    with pytest.raises(ValueError):
        AD.band_powers(np.zeros(10), np.arange(5.0))


def test_epoch_assignment_is_half_open_so_a_sample_on_a_change_joins_the_new_epoch():
    ep = pd.DataFrame({"t_start": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]),
                       "t_end": pd.to_datetime(["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"])})
    boundary = pd.Timestamp("2026-01-01T01:00:00Z").timestamp()
    got = AD._assign_epoch([boundary - 1, boundary, boundary + 1], ep)
    assert list(got) == [0, 1, 1]
    assert AD._assign_epoch([pd.Timestamp("2020-01-01T00:00:00Z").timestamp()], ep)[0] == -1


def test_era_cuts_match_the_biomarker_module_and_reject_nan():
    assert (AD._era(0.05), AD._era(1.0), AD._era(3.0)) == ("OFF", "LOW", "HIGH")
    assert AD._era(float("nan")) is None and AD._era(None) is None


def _toy_table(n_epochs=6, per_epoch=5, slope=-2.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_epochs):
        amp = 1.0 + e * 0.5
        for _ in range(per_epoch):
            rows.append({"t": float(e), "channel": "CH", "setting_epoch": e, "center_hz": 20.5,
                         "amp_mA_Left": amp, "power_linear": 10.0 + slope * amp + rng.normal(0, 0.2),
                         "nrs": 5.0 + 0.5 * amp + rng.normal(0, 0.2), "report_id": f"r{e}"})
    return pd.DataFrame(rows)


# --- Phase 2 ------------------------------------------------------------------------------------
def test_actuation_edge_clusters_on_the_setting_epoch_and_says_so():
    T = _toy_table()
    e = E.actuation_edge(T, channel="CH", center_hz=20.5)
    assert e.cluster_unit == "setting epoch" and e.n_clusters == 6
    assert e.estimate == pytest.approx(-2.0, abs=0.3) and e.resolved and e.sign == -1
    # the confound label must travel with the number, not be added by a caller
    assert "SCREENING STATISTIC ONLY" in e.note and "time" in e.confounded_by


def test_actuation_edge_refuses_a_single_setting_epoch():
    """A within-subject slope is not identifiable from one setting, and returning a number here
    would be the pseudoreplication the audit was about."""
    T = _toy_table(n_epochs=1, per_epoch=30)
    e = E.actuation_edge(T, channel="CH", center_hz=20.5)
    assert e.estimate is None and not e.resolved and e.n_clusters <= 1


def test_state_edge_refuses_when_the_rating_cluster_is_absent():
    T = _toy_table().drop(columns=["report_id"])
    e = E.state_edge(T, channel="CH", center_hz=20.5)
    assert e.estimate is None and "rating-level cluster is unavailable" in e.note


def test_max_statistic_permutation_permutes_whole_epochs():
    T = _toy_table(n_epochs=6, per_epoch=6)
    out = E.max_statistic_permutation(T, channels=["CH"], centers=[20.5], n_perm=99, seed=1)
    assert out["available"] and out["n_epochs_permuted"] == 6
    assert 0.0 < out["p_fwer"] <= 1.0
    assert out["resolution"] == pytest.approx(1 / 100)
    # too few epochs must refuse rather than return a meaningless null
    assert E.max_statistic_permutation(_toy_table(n_epochs=2), channels=["CH"],
                                       centers=[20.5], n_perm=10)["available"] is False


# --- coherence ----------------------------------------------------------------------------------
def _edge(name, est, lo, hi, unit="rating"):
    return EdgeEstimate(name, est, (lo, hi), 0.01, 50, unit, 8)


def test_unresolved_edge_makes_coherence_unknown_not_false():
    """None and False mean different things: not established versus contradictory."""
    ok1, ok2 = _edge("E1", -1.0, -1.5, -0.5), _edge("E2", 1.0, 0.5, 1.5)
    spans = _edge("E3", -0.1, -0.6, 0.4)
    assert C.signs_coherent(ok1, ok2, spans) is None
    r = C.coherence_report(ok1, ok2, spans)
    assert r.coherent is None and "NOT ESTABLISHED" in r.note


def test_contradictory_triangle_is_detected():
    e1, e2 = _edge("E1", -1.0, -1.5, -0.5), _edge("E2", 1.0, 0.5, 1.5)
    e3_wrong = _edge("E3", 1.0, 0.5, 1.5)          # indirect says negative, total says positive
    assert C.signs_coherent(e1, e2, e3_wrong) is False
    assert "CONTRADICTORY" in C.coherence_report(e1, e2, e3_wrong).note


def test_internally_consistent_but_wrong_for_dual_threshold_is_still_refused():
    """E1 positive closes a positive-feedback loop. The triangle can be self-consistent and still
    be undeployable, and the report must distinguish those."""
    e1, e2, e3 = _edge("E1", 1.0, 0.5, 1.5), _edge("E2", -1.0, -1.5, -0.5), _edge("E3", -1.0, -1.5, -0.5)
    assert C.signs_coherent(e1, e2, e3) is True
    r = C.coherence_report(e1, e2, e3)
    assert r.coherent is False and "do NOT match the pattern Dual Threshold requires" in r.note


def test_the_deployable_pattern_passes():
    e1, e2, e3 = _edge("E1", -1.0, -1.5, -0.5), _edge("E2", 1.0, 0.5, 1.5), _edge("E3", -1.0, -1.5, -0.5)
    assert C.coherence_report(e1, e2, e3).coherent is True


# --- authority ----------------------------------------------------------------------------------
def test_control_authority_refuses_a_distribution_with_no_measured_spread():
    """The dangerous failure would be reporting excellent authority from one observation."""
    assert AU.control_authority([1.0], [5.0]) is None
    assert AU.control_authority([1.0, 1.0, 1.0], [1.0, 1.0, 1.0]) is None
    d = AU.control_authority([0, 0.1, -0.1, 0.05], [5, 5.1, 4.9, 5.05])
    assert d is not None and d > 3


def test_threshold_placement_flags_inverted_and_too_close_captures():
    rng = np.random.default_rng(0)
    lo, hi = rng.normal(10, 1, 40), rng.normal(4, 1, 40)      # power FALLS as amplitude rises
    good = AU.threshold_placement(lo, hi, amp_low=1.0, amp_high=3.0, expected_sign=-1)
    assert good.predicted_recapture_alert is False and good.upper > good.lower
    inv = AU.threshold_placement(hi, lo, amp_low=1.0, amp_high=3.0, expected_sign=-1)
    assert inv.predicted_recapture_alert is True
    assert any("inverted capture" in p for p in inv.problems)
    close = AU.threshold_placement(rng.normal(10, 1, 40), rng.normal(10.2, 1, 40),
                                   amp_low=1.0, amp_high=3.0, expected_sign=-1)
    assert any("too close" in p for p in close.problems)


def test_threshold_placement_enforces_the_d27_capture_artefact_ceiling():
    rng = np.random.default_rng(1)
    lo, hi = rng.normal(10, 1, 30), rng.normal(4, 1, 30)
    r = AU.threshold_placement(lo, hi, amp_low=1.0, amp_high=6.0, expected_sign=-1,
                               pulse_width_us=200.0)
    assert any("D27" in p and "6.00 mA" in p for p in r.problems)
    assert any("D27" in p and "200" in p for p in r.problems)


# --- ledger -------------------------------------------------------------------------------------
def test_registry_is_append_only_and_detects_tampering(tmp_path):
    p = tmp_path / "reg.json"
    r = Registry(p)
    r.register(candidates=["a"], estimators={"E1": "ols"}, alpha=0.05, correction="none",
               stopping_rule="fixed n", primary_outcome="nrs")
    r.amend(what_changed="alpha", why="stricter", fields={"alpha": 0.01})
    assert r.effective()["alpha"] == 0.01
    assert len(r.effective()["amendments_applied"]) == 1
    # the original registration entry is untouched
    assert r.entries[0]["alpha"] == 0.05
    import json
    d = json.loads(p.read_text()); d["entries"][0]["alpha"] = 0.5; p.write_text(json.dumps(d))
    assert Registry(p).tampered is True


def test_registry_refuses_an_unexplained_amendment(tmp_path):
    r = Registry(tmp_path / "r.json")
    r.register(candidates=["a"], estimators={}, alpha=0.05, correction="none",
               stopping_rule="x", primary_outcome="nrs")
    with pytest.raises(ValueError):
        r.amend(what_changed="alpha", why="")


def test_epoch_assignment_survives_microsecond_resolution_datetimes():
    """Regression, 2026-09-03. Under pandas 3 a datetime column may carry MICROSECOND resolution,
    and `.astype("int64")` returns the raw integer in the column's own unit. Dividing that by 1e9
    produced epoch seconds a thousand times too small, so every sample fell outside every epoch and
    the Phase 0 table came back empty — with no exception raised anywhere. Pinning both resolutions
    because the failure was silent and data-dependent."""
    for unit in ("ns", "us", "ms", "s"):
        ep = pd.DataFrame({
            "t_start": pd.Series(pd.to_datetime(["2026-01-01T00:00:00Z"])).astype(f"datetime64[{unit}, UTC]"),
            "t_end": pd.Series(pd.to_datetime(["2026-01-01T01:00:00Z"])).astype(f"datetime64[{unit}, UTC]"),
        })
        mid = pd.Timestamp("2026-01-01T00:30:00Z").timestamp()
        assert AD._assign_epoch([mid], ep)[0] == 0, f"failed at {unit} resolution"


def test_few_clusters_is_flagged_because_the_robust_estimator_is_anticonservative_there():
    """Observed on the real RCS08 record: cells with three setting epochs reported all eighteen
    bands as resolved, while the whole-epoch permutation on the same cells returned a family-wise
    p of 1.00. The cluster-robust variance estimator needs many clusters; with few it produces
    intervals that are too narrow, which manufactures resolution rather than losing it."""
    T = _toy_table(n_epochs=4, per_epoch=8)
    e = E.actuation_edge(T, channel="CH", center_hz=20.5)
    assert e.n_clusters == 4 and "FEW CLUSTERS" in e.note
    assert "few clusters" in e.confounded_by


def test_the_rendered_coherence_reason_states_the_device_direction_correctly():
    """Regression, 2026-09-03. An earlier version of this text said Dual Threshold ramps amplitude
    DOWN above the upper threshold. The white paper (p. 13) says UP. The required signs never
    depended on the erroneous sentence, but the sentence is what a clinician reads, and it appeared
    in the rendered report rather than only in a docstring."""
    exp = C.expected_pattern_for_dual_threshold()
    assert "ramps amplitude UP" in exp["why"]
    assert "DOWN above the upper threshold" not in exp["why"]
    assert (exp["E1"], exp["E2"], exp["E3"]) == (-1, +1, -1)
    e1, e2, e3 = _edge("E1", -1.0, -1.5, -0.5), _edge("E2", 1.0, 0.5, 1.5), _edge("E3", -1.0, -1.5, -0.5)
    assert "ramps amplitude UP" in C.coherence_report(e1, e2, e3).note


def test_an_unresolved_edge_does_not_supply_its_sign_to_the_device_gate():
    """Rule D19 asks which way the band moves. An unresolved edge HAS a point-estimate sign, but
    that sign is not established. Supplying it would let the most important safety gate be
    satisfied by a direction the data does not support."""
    from ClosedLoopDeployment.pipeline import _facts_for
    resolved = EdgeEstimate("E1", -1.0, (-1.5, -0.5), 0.01, 50, "setting epoch", 60)
    spans_zero = EdgeEstimate("E2", 0.9, (-0.2, 2.0), 0.2, 50, "rating", 60)
    f = _facts_for({"channel": "CH"}, resolved, spans_zero, "power_linear")
    assert f["power_slope_vs_amplitude_sign"] == -1
    assert "power_slope_vs_pain_sign" not in f, "an unresolved edge must not supply a sign"
    assert f["power_scale"] == "linear" and f["intent"] == "adaptive"
    # asking for the log scale must be reported honestly, not silently corrected to what D11 wants
    assert _facts_for({}, resolved, resolved, "power_mean_of_log")["power_scale"] == "log"


def test_the_payload_keeps_coherence_as_three_states():
    """None means 'not established' and False means 'the signs contradict'. Collapsing the first
    into the second makes the interface report a contradiction the data never showed."""
    from ClosedLoopDeployment.adapter import report_to_dict
    from ClosedLoopDeployment.types import DeploymentReport
    e_ok = _edge("E1", -1.0, -1.5, -0.5)
    e_unres = _edge("E2", 0.5, -0.2, 1.2)
    rep = DeploymentReport(participant="x", edges={"E1": e_ok, "E2": e_unres, "E3": e_ok})
    rep.coherence = C.coherence_report(e_ok, e_unres, e_ok)
    d = report_to_dict(rep)
    assert d["coherence"]["coherent"] is None
    assert d["verdict_detail"]["coherent"] is None, "None must not be collapsed to False"


# --- D09 as a per-bin advisory (PI decision 2026-09-04) -----------------------------------------
def test_d09_is_advisory_and_reports_which_bins_clear_the_capture_gate():
    """Softened from blocking on PI decision: the guide RECOMMENDS this amplitude and states it two
    ways (1.2 vs 1.1 uVp) without explaining the difference, so refusing outright would be stronger
    than the evidence. It now reports which bins clear and flags the shortfall.

    The per-bin form matters: threshold capture reads ONE frequency, so averaging a peak with its
    neighbours can hide a capturable peak or manufacture one that is not there.
    """
    from ClosedLoopDeployment import constraints as CN
    rule = CN.RULES_BY_ID["D09"]
    assert rule.severity == "advisory"

    band = {"center_hz": 24.5, "band_width_hz": 5.0}
    # RCS08's real shape: nothing in the beta band reaches the gate.
    below = dict(band, lfp_bins_uvp=[(22.5, 0.61), (23.5, 0.64), (24.5, 0.71), (25.5, 0.58)])
    assert rule.predicate(below, {}) is False
    obs = CN._OBSERVED["D09"](below, {})
    assert "NO bin" in obs and "0.71" in obs

    # A single clearing bin is enough, because capture reads one frequency.
    one = dict(band, lfp_bins_uvp=[(22.5, 0.61), (24.5, 1.35), (25.5, 0.58)])
    assert rule.predicate(one, {}) is True
    assert "1 of 3 bins" in CN._OBSERVED["D09"](one, {})

    # Bins outside the selected band must not rescue it: the alpha peak on this device sits at
    # ~9 Hz, and it says nothing about capturability at 24.5 Hz.
    outside = dict(band, lfp_bins_uvp=[(9.0, 4.0), (24.5, 0.4)])
    assert rule.predicate(outside, {}) is False

    # No bins in band at all is not determinable, not a pass.
    assert rule.predicate(dict(band, lfp_bins_uvp=[(9.0, 4.0)]), {}) is None
