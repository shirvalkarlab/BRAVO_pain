"""Core tests: the joined table, the edges, coherence, authority and the ledger."""
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import adapter as AD, edges as E, consistency as C, authority as AU
from ClosedLoopDeployment.types import EdgeEstimate


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
    """The wording of the refusal changed when this calculation moved onto the biomarker page, and
    the new sentence is checked here instead of the old one. It now names the column that was
    missing and says in ordinary words what would go wrong without it, rather than calling it a
    "rating-level cluster"; the refusal itself, and the absent slope, are unchanged.
    """
    T = _toy_table().drop(columns=["report_id"])
    e = E.state_edge(T, channel="CH", center_hz=20.5)
    assert e.estimate is None
    assert "no report_id column" in e.note, e.note
    assert "pseudoreplication" in e.note, e.note


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


def test_an_unresolved_edge_supplies_its_point_sign_to_d19_and_is_flagged_as_not_established():
    """PI decision 2026-09-12, reversing the rule this test used to pin. Rule D19 asks which way
    the band moves. An unresolved edge HAS a point-estimate sign, and it is now supplied -- with a
    sibling flag saying it is NOT statistically established, and the edge's interval and p-value,
    so nothing downstream loses the distinction the old rule enforced by omission."""
    from ClosedLoopDeployment.pipeline import _facts_for
    resolved = EdgeEstimate("E1", -1.0, (-1.5, -0.5), 0.01, 50, "setting epoch", 60)
    spans_zero = EdgeEstimate("E2", 0.9, (-0.2, 2.0), 0.2, 50, "rating", 60)
    f = _facts_for({"channel": "CH"}, resolved, spans_zero, "power_linear")
    assert f["power_slope_vs_amplitude_sign"] == -1
    assert f["power_slope_vs_amplitude_sign_established"] is True
    assert f["power_slope_vs_amplitude_ci"] == [-1.5, -0.5]
    assert f["power_slope_vs_amplitude_p"] == 0.01
    assert f["power_slope_vs_pain_sign"] == 1, "an unresolved edge now supplies its point sign"
    assert f["power_slope_vs_pain_sign_established"] is False
    assert f["power_slope_vs_pain_ci"] == [-0.2, 2.0]
    assert f["power_slope_vs_pain_p"] == 0.2
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


# --- impedance facts, and why they are NOT read through the file loader (2026-09-04) ------------
class _Rec:
    """Minimal stand-in for a Recording row: the impedance payload lives on `metadata`."""
    def __init__(self, metadata, date=0):
        self.metadata, self.date, self.pointer, self.hashed = metadata, date, "", ""


def _imp(worst_left, status="GOOD", date=1, model="LEAD_B33015", amplitude=None):
    """``amplitude`` mirrors the raw, no-space-before-the-unit strings on RCS08's own export:
    "Automatic increasemA", "0.4mA", "1.0mA". ``None`` (the default) omits the field entirely, the
    same shape every impedance test written before 2026-09-12 already used, so every existing test
    that leaves it unset keeps exercising the pre-measurement-current fallback path."""
    meta = {"Status": status,
            "Left": {"LeadModel": model, "Monopolar": [2605.0] * 8,
                     "Bipolar": [[0.0, 5752.0, worst_left], [0.0, 0.0, 6641.0], [0.0, 0.0, 0.0]]},
            "Right": {"LeadModel": model, "Monopolar": [4044.0] * 8,
                      "Bipolar": [[0.0, 4044.0, 4059.0], [0.0, 0.0, 3664.0], [0.0, 0.0, 0.0]]}}
    if amplitude is not None:
        meta["Amplitude"] = amplitude
    return _Rec(meta, date=date)


def test_impedance_is_read_from_metadata_because_these_rows_have_no_file():
    """`MedtronicDeviceImpedance` rows carry an EMPTY pointer — the payload is inline. Calling
    Database.loadSourceFile on them trips its path-PREFIX guard and raises "Malicious Attempt at
    Accessing Other Data in the Computer", which reads like a security incident and is not one; the
    HMAC integrity guard is a different exception ("DANGER: Unauthorized Modification of Data") and
    never fired. This test exists so nobody re-diagnoses that as data corruption.
    """
    from ClosedLoopDeployment import device_facts as DF
    f = DF.impedance_facts([_imp(6322.0, date=1), _imp(10125.0, status="INVESTIGATE", date=2)])
    assert f["available"] is True and f["n_records"] == 2
    assert f["status_newest"] == "INVESTIGATE", "the NEWEST record must win, not the first"
    assert f["status_counts"] == {"GOOD": 1, "INVESTIGATE": 1}
    assert f["lead_type"] == "sensight" and f["lead_model"] == "LEAD_B33015"
    assert DF.impedance_facts([])["available"] is False


def test_impedance_reports_the_worst_pair_not_the_average():
    """D16 is a FAULT check. One open contact matters even when the other seven are healthy, so
    averaging is precisely the operation that would hide it."""
    from ClosedLoopDeployment import device_facts as DF
    f = DF.impedance_facts([_imp(10125.0)])
    assert f["Left"]["bipolar_max_ohm"] == 10125.0
    assert f["Left"]["bipolar_median_ohm"] < f["Left"]["bipolar_max_ohm"]
    assert DF.candidate_impedance_ohm(f, "Left") == 10125.0
    assert DF.candidate_impedance_ohm(f, "Right") == 4059.0
    assert DF.candidate_impedance_ohm({"available": False}, "Left") is None


def test_an_open_circuit_bipolar_pair_fails_d16():
    """The real RCS08 reading. 10125 ohm on the left lead is above the 10000 ohm open limit, so the
    sensing hemisphere for a left-sided candidate fails rather than merely warning."""
    from ClosedLoopDeployment import constraints as CN
    bad = CN.check_eligibility({"impedance_ohms": 10125.0, "impedance_tested": True},
                               {"lead_type": "sensight"})
    assert "D16" in {x["rule_id"] for x in bad.failures}
    ok = CN.check_eligibility({"impedance_ohms": 6322.0, "impedance_tested": True},
                              {"lead_type": "sensight"})
    assert "D16" not in {x["rule_id"] for x in ok.failures}
    shorted = CN.check_eligibility({"impedance_ohms": 200.0, "impedance_tested": True},
                                   {"lead_type": "sensight"})
    assert "D16" in {x["rule_id"] for x in shorted.failures}


# --- the measurement-current fix for D16, PI decision 2026-09-12 ---------------------------------
# The device's DEFAULT impedance test steps a low measurement current up automatically, and at
# that low current a healthy lead can read above the open-circuit limit even though the same lead
# reads normal at a fixed, higher current. Measured on RCS08: 351 of 544 automatic-mode tests read
# the Left lead's worst pair above 10,000 ohms, against 0 of 18 fixed-current tests. The PI ruled
# that a high reading produced only by the automatic mode must not gate D16 by itself.

def test_impedance_facts_prefers_the_newest_fixed_current_reading_over_a_newer_automatic_one():
    from ClosedLoopDeployment import device_facts as DF
    fixed = _imp(7000.0, date=1, amplitude="0.4mA")
    automatic = _imp(10500.0, date=2, amplitude="Automatic increasemA")
    f = DF.impedance_facts([fixed, automatic])
    assert f["measurement_current"] == 0.4
    assert f["Left"]["bipolar_max_ohm"] == 7000.0, ("D16 must trust the FIXED-current reading, "
                                                     "not the newer automatic-mode one")
    assert f["status_newest"] == "GOOD", "status_newest still names the truly newest record"


def test_impedance_facts_falls_back_to_the_newest_automatic_reading_with_no_fixed_current_test():
    from ClosedLoopDeployment import device_facts as DF
    a1 = _imp(9000.0, date=1, amplitude="Automatic increasemA")
    a2 = _imp(10261.0, date=2, amplitude="Automatic increasemA")
    f = DF.impedance_facts([a1, a2])
    assert f["measurement_current"] == "automatic_increase"
    assert f["Left"]["bipolar_max_ohm"] == 10261.0, "no fixed test exists, so the fallback is the newest of any kind"
    assert "automatic_newest_ohm" not in f["Left"], "there is no separate fixed reading to compare it against"


def test_impedance_automatic_spurious_fail_fields_appear_only_when_the_case_holds():
    from ClosedLoopDeployment import device_facts as DF
    fixed_ok = _imp(7286.0, date=1, amplitude="0.4mA")
    auto_bad = _imp(10261.0, date=2, amplitude="Automatic increasemA")
    holds = DF.impedance_facts([fixed_ok, auto_bad])
    assert holds["Left"]["automatic_newest_ohm"] == 10261.0
    assert holds["Left"]["automatic_newest_date"] is not None

    auto_ok = _imp(8000.0, date=2, amplitude="Automatic increasemA")
    not_over_limit = DF.impedance_facts([fixed_ok, auto_ok])
    assert "automatic_newest_ohm" not in not_over_limit["Left"], "the automatic reading is inside the limit too"

    no_fixed_at_all = DF.impedance_facts([auto_bad])
    assert "automatic_newest_ohm" not in no_fixed_at_all["Left"], "nothing to compare a fixed reading against"


def test_impedance_history_reports_the_fixed_current_subset_alongside_the_full_history():
    from ClosedLoopDeployment import device_facts as DF
    fixed1 = _imp(7000.0, date=1, amplitude="0.4mA")
    fixed2 = _imp(9500.0, date=2, amplitude="1.0mA")
    auto_high = _imp(13000.0, date=3, amplitude="Automatic increasemA")
    f = DF.impedance_facts([fixed1, fixed2, auto_high])
    hist = f["history"]["Left"]
    assert hist["n_readings_fixed"] == 6, "3 bipolar pairs per record, 2 fixed-current records"
    assert hist["bipolar_max_ohm_ever_fixed"] == 9500.0, "the automatic-mode reading must not count here"
    assert hist["n_above_open_limit_fixed"] == 0
    assert hist["bipolar_max_ohm_ever"] == 13000.0, "the unrestricted history still sees every reading"
    assert hist["n_above_open_limit"] == 1


def test_o_d16_names_the_measurement_current_and_the_spurious_fail_case():
    from ClosedLoopDeployment import constraints as CN
    spurious = {"impedance_ohms": 7286.0, "impedance_tested": True,
                "impedance_measurement_current": 0.4, "impedance_measured_at": "2026-09-02",
                "impedance_ohms_automatic_newest": 10261.0,
                "impedance_automatic_measured_at": "2026-09-11"}
    text = CN._o_d16(spurious, {"lead_type": "sensight"})
    assert "0.4 mA" in text and "2026-09-02" in text
    assert "10261" in text and "2026-09-11" in text
    assert "ruled a spurious fail" in text, "the PI's ruling, on a reading actually contradicted by a fixed-current test"

    no_fixed_test = {"impedance_ohms": 10261.0, "impedance_tested": True,
                     "impedance_measurement_current": "automatic_increase",
                     "impedance_measured_at": "2026-09-11"}
    text2 = CN._o_d16(no_fixed_test, {"lead_type": "sensight"})
    assert "automatic low-current mode" in text2
    assert "fixed-current" in text2 and "would settle" in text2
    assert "ruled a spurious fail" not in text2, "there is no fixed-current test to have contradicted this reading"


def test_d16_is_recorded_as_an_advisory_value_when_it_passes():
    from ClosedLoopDeployment import constraints as CN
    r = CN.check_eligibility({"impedance_ohms": 6322.0, "impedance_tested": True,
                              "impedance_measurement_current": 0.4,
                              "impedance_measured_at": "2026-09-02"},
                             {"lead_type": "sensight"})
    row = next(a for a in r.advisories if a["rule_id"] == "D16")
    assert row["kind"] == "recorded_value"
    assert "0.4 mA" in row["observed"]
    assert "D16" not in {f["rule_id"] for f in r.failures}


def test_participant_scoped_device_facts_reach_the_participant_dict():
    """A fact one dictionary away from the rule that reads it is invisible, and the symptom is
    indistinguishable from missing data: the rule reports "input not supplied" and blocks.

    D04 reads n_neurostimulators and D16 reads lead_type from the PARTICIPANT dict, not the
    candidate. Merging every device fact into the candidate left both unevaluable while the values
    were present — which is what the live RCS08 report did before this fix, showing D04 and D16 as
    unknown with n_neurostimulators=1 and lead_type='sensight' sitting one dict away.
    """
    from ClosedLoopDeployment import pipeline as PL, constraints as CN
    assert "n_neurostimulators" in CN.PARTICIPANT_KEYS
    assert "lead_type" in CN.PARTICIPANT_KEYS

    dev = {"n_neurostimulators": 1, "lead_type": "sensight", "impedance_ohms": 6322.0,
           "impedance_tested": True, "_provenance": {"x": "y"}}
    pf = PL._participant_facts("uid-x", dev, CN)
    assert pf["n_neurostimulators"] == 1
    assert pf["lead_type"] == "sensight"
    assert "_provenance" not in pf, "provenance is diagnostics, never a predicate input"
    assert "impedance_ohms" not in pf, "candidate-scoped facts must NOT leak into participant"
    assert pf["programming_mode"] == "parkinsons"

    cf = PL._facts_for({"center_hz": 24.5, "band_width_hz": 5.0}, None, None, "power_linear",
                       device_facts=dev)
    assert cf["impedance_ohms"] == 6322.0

    # end to end: both rules become evaluable
    r = CN.check_eligibility(cf, pf)
    unknown = {u["rule_id"] for u in r.unknowns}
    assert "D04" not in unknown and "D16" not in unknown
    assert "D16" not in {f["rule_id"] for f in r.failures}, "6322 ohm is inside both limits"

    # scope is read from the constraint module, so an unknown module strands nothing silently
    assert PL._participant_facts("uid-x", dev, None)["uid"] == "uid-x"


# --- the Phase 0 cache (2026-09-04) -------------------------------------------------------------
def _tiny_inputs():
    """A psd frame and epoch frame in the REAL shapes, which are not the obvious ones.

    The psd frame is one row per (sample, channel) as `lfp_evidence.frame_from_matrix` emits it:
    `t` is EPOCH SECONDS as a float, and the whole spectrum lives in `log_psd` as a numpy array with
    its axis in `freqs`. It is not long-per-frequency. The epoch frame keeps tz-aware Timestamps,
    because that is what `exposure_epochs` produces. Both mistakes were made while writing these
    tests and both failed loudly here but would have failed SILENTLY in the cache fingerprint.
    """
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    f_set = np.arange(8.0, 31.0, 1.0)
    rows = []
    for k in range(6):
        rows.append({"t": float((t0 + pd.Timedelta(minutes=5 * k)).timestamp()),
                     "channel": "CH", "source": "td",
                     "log_psd": np.sin(f_set) + float(k), "freqs": f_set})
    psd = pd.DataFrame(rows)
    eps = pd.DataFrame({"t_start": [t0], "t_end": [t0 + pd.Timedelta(hours=1)],
                        "amp_mA_Left": [2.0], "amp_mA_Right": [2.0], "freq_hz": [165.0],
                        "pw_us_Left": [60.0]})
    return psd, eps


def _bump_spectrum(psd, row=0, by=10.0):
    """Change the CONTENT of one spectrum, leaving every shape and timestamp identical."""
    out = psd.copy()
    out.at[row, "log_psd"] = np.asarray(out.at[row, "log_psd"], float) + by
    return out


def test_fingerprint_tracks_array_valued_spectra_and_not_merely_the_timestamps():
    """Regression, 2026-09-04, for a cache bug that would have served stale tables while looking
    verified.

    The first fingerprint listed column names that do not exist on the real psd frame
    ("frequency", "log_power", "center_hz"). Absent columns are skipped by design, so it hashed
    only `t` and `channel`, reported its mode as "hashed", and DID NOT CHANGE when the spectra
    changed. A re-decoded recording with unchanged timestamps would have been served the previous
    joined table by a cache whose key claimed to be a content hash.

    Separately, hash_pandas_object cannot hash a column of numpy arrays, so naming the array
    columns without special handling degraded the mode to "shape_only" instead.
    """
    from ClosedLoopDeployment import adapter as AD
    psd, _ = _tiny_inputs()
    fp = AD._frame_fingerprint(psd, ("t", "channel", "source", "log_psd", "freqs"))
    assert fp[0] == "hashed", "array columns must be hashed, not degrade to shape_only"
    bumped = AD._frame_fingerprint(_bump_spectrum(psd), ("t", "channel", "source", "log_psd", "freqs"))
    assert bumped != fp, "a spectral change MUST move the fingerprint"

    # the signature used by the cache must inherit that sensitivity
    a = AD._joined_signature(psd, None, (20.5,), 5.0)
    b = AD._joined_signature(_bump_spectrum(psd), None, (20.5,), 5.0)
    assert a != b

    # A frame carrying none of the named columns now RAISES. It used to return a "no_columns"
    # marker, which was still safer than a false hash, but only in the case where EVERY name was
    # missing; one missing name out of five went unreported, which is the case that actually
    # happened. See test_adapter_caching.py for the full set of conditions on this.
    with pytest.raises(KeyError):
        AD._frame_fingerprint(pd.DataFrame({"zz": [1]}), ("t",))
    assert AD._frame_fingerprint(None, ("t",)) == ("none",)


def test_joined_cache_returns_the_same_object_on_a_repeat_call():
    from ClosedLoopDeployment import adapter as AD
    AD.clear_joined_cache()
    psd, eps = _tiny_inputs()
    a = AD.joined_table_cached(psd, eps)
    b = AD.joined_table_cached(psd, eps)
    assert a is b, "a repeat call must not rebuild"
    assert AD.joined_cache_stats()["entries"] == 1


def test_joined_cache_invalidates_on_a_CONTENT_change_that_leaves_the_shape_identical():
    """The property that justifies a content hash over a row count.

    A corrected amplitude, a re-decoded spectrum or a moved epoch boundary can change the data
    without changing its size. A shape-keyed cache would serve the stale table, and on a module
    whose output authorises programming a neurostimulator that is far worse than rebuilding.
    """
    from ClosedLoopDeployment import adapter as AD
    AD.clear_joined_cache()
    psd, eps = _tiny_inputs()
    first = AD.joined_table_cached(psd, eps)

    moved = eps.copy()
    moved.loc[0, "amp_mA_Left"] = 3.5          # same shape, different value
    second = AD.joined_table_cached(psd, moved)
    assert second is not first, "an amplitude change must invalidate"
    assert AD.joined_cache_stats()["entries"] == 2

    AD.clear_joined_cache()
    p1 = AD.joined_table_cached(psd, eps)
    p2 = AD.joined_table_cached(_bump_spectrum(psd), eps)
    assert p2 is not p1, "a spectral change must invalidate"


def test_joined_cache_is_bounded_and_evicts():
    """Entries are 100k-row frames, so the memo must not grow without bound."""
    from ClosedLoopDeployment import adapter as AD
    AD.clear_joined_cache()
    psd, eps = _tiny_inputs()
    for amp in (1.0, 2.0, 3.0, 4.0):
        e = eps.copy(); e.loc[0, "amp_mA_Left"] = amp
        AD.joined_table_cached(psd, e)
    st = AD.joined_cache_stats()
    assert st["entries"] == st["max"] == AD._JOINED_MEMO_MAX


def test_force_refresh_rebuilds_and_replaces_the_entry():
    from ClosedLoopDeployment import adapter as AD
    AD.clear_joined_cache()
    psd, eps = _tiny_inputs()
    a = AD.joined_table_cached(psd, eps)
    b = AD.joined_table_cached(psd, eps, force_refresh=True)
    assert b is not a, "force_refresh must rebuild"
    assert AD.joined_table_cached(psd, eps) is b, "and the fresh table must replace the entry"


def test_fingerprint_says_when_it_could_not_hash_rather_than_degrading_silently():
    """A fingerprint that quietly fell back to the shape would reintroduce the stale-table risk the
    content hash exists to remove, so the mode is the first element of the returned tuple.

    Updated 2026-09-04: a frame carrying NONE of the named columns returned "no_columns" rather
    than "hashed". The original assertion accepted "hashed" for that case, which was the behaviour
    that let a fingerprint over a nonexistent column list look healthy while tracking nothing.

    Updated again 2026-09-06, and this is the change that closes the hole properly. Returning a
    marker only helped when EVERY named column was missing. The mistake that actually happened was
    two names right and three wrong, which still returned "hashed" over the two that existed. A
    named column that is not on the frame now raises, so the case cannot arise at all. The
    conditions on the four ways of naming columns live in test_adapter_caching.py.
    """
    from ClosedLoopDeployment import adapter as AD
    psd, _ = _tiny_inputs()
    assert AD._frame_fingerprint(psd, ("t", "channel", "log_psd"))[0] == "hashed"
    assert AD._frame_fingerprint(None, ("x",)) == ("none",)
    with pytest.raises(AD.MissingFingerprintColumn):
        AD._frame_fingerprint(psd, ("nonexistent",))
    # and a PARTIAL overlap raises too, which is the case that bit us
    with pytest.raises(AD.MissingFingerprintColumn):
        AD._frame_fingerprint(psd, ("t", "nonexistent"))


def test_annotating_a_column_the_join_ignores_does_not_invalidate():
    """Downstream code adds columns. Invalidating on those would defeat the cache for no gain."""
    from ClosedLoopDeployment import adapter as AD
    AD.clear_joined_cache()
    psd, eps = _tiny_inputs()
    a = AD.joined_table_cached(psd, eps)
    annotated = psd.copy(); annotated["reviewer_note"] = "looks fine"
    assert AD.joined_table_cached(annotated, eps) is a, \
        "a column the join never reads must not invalidate"


def test_recording_set_signature_folds_in_each_recordings_own_hash():
    """Keyed on recording IDENTITY, not a count or a max date.

    A re-decode that replaces a recording in place changes neither the count nor the newest date,
    and a count alone also misses a deletion balanced by an insertion. This project has already
    lost a session to a plot that looked frozen because files were never ingested, so the cache must
    invalidate exactly when the recording set changes and never on a timer.
    """
    from ClosedLoopDeployment import adapter as AD

    class _R:
        def __init__(self, uid, hashed, type_="X"):
            self.uid, self.hashed, self.type = uid, hashed, type_

    class _P:
        uid = "p1"

    import sys, types
    fake = types.ModuleType("Server"); fake_models = types.ModuleType("Server.models")
    state = {"recs": [_R("a", "h1"), _R("b", "h2")], "sfs": ["s1"]}
    fake_models.SourceFile = type("SF", (), {"find_all": staticmethod(lambda **k: state["sfs"])})
    fake_models.Recording = type("R", (), {"find_all": staticmethod(lambda **k: state["recs"])})
    fake.models = fake_models
    saved = (sys.modules.get("Server"), sys.modules.get("Server.models"))
    sys.modules["Server"], sys.modules["Server.models"] = fake, fake_models
    try:
        base = AD.recording_set_signature(_P())
        assert AD.recording_set_signature(_P()) == base, "must be stable for identical input"

        state["recs"] = [_R("a", "h1_REDECODED"), _R("b", "h2")]
        assert AD.recording_set_signature(_P()) != base, \
            "a re-decode changes no count and no date, so the hash must carry it"

        state["recs"] = [_R("a", "h1"), _R("c", "h2")]     # one deleted, one inserted
        assert AD.recording_set_signature(_P()) != base, \
            "a swap keeps the count identical and must still invalidate"

        state["recs"] = [_R("b", "h2"), _R("a", "h1")]     # order must not matter
        assert AD.recording_set_signature(_P()) == base
    finally:
        for k, v in zip(("Server", "Server.models"), saved):
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


# --- session-report facts, and the impedance current-vs-historical distinction (2026-09-04) -----
def test_impedance_reports_the_newest_reading_AND_the_historical_worst():
    """Regression for a verdict that flipped with no code change.

    D16 read 10885 ohm and FAILED; an ingest brought in a newer, better measurement and it read
    6869 ohm and PASSED. Both numbers were correct — the fact is the worst pair within the NEWEST
    recording — but the provenance string said "across N recordings", which invites a reader to
    take a currently-sound lead for a never-faulty one. On the real record the left lead is
    intermittent: 1265 of 15540 readings exceed the open-circuit limit while the newest is inside
    it. Both answers must therefore be carried, because "is it sound now" and "has it ever failed"
    are different clinical questions.
    """
    from ClosedLoopDeployment import device_facts as DF

    def rec(worst, date, status="GOOD"):
        return _Rec({"Status": status,
                     "Left": {"LeadModel": "LEAD_B33015",
                              "Monopolar": [1000.0] * 8,
                              "Bipolar": [[1000.0, worst]]},
                     "Right": {"LeadModel": "LEAD_B33015",
                               "Monopolar": [1000.0] * 8,
                               "Bipolar": [[900.0, 950.0]]}}, date)

    f = DF.impedance_facts([rec(13262.0, 1, "INVESTIGATE"), rec(6869.0, 2, "GOOD")])
    assert f["Left"]["bipolar_max_ohm"] == 6869.0, "the fact is the NEWEST record's worst pair"
    assert f["status_newest"] == "GOOD"
    hist = f["history"]["Left"]
    assert hist["bipolar_max_ohm_ever"] == 13262.0, "the historical worst must survive"
    assert hist["n_above_open_limit"] == 1
    assert f["status_counts"] == {"GOOD": 1, "INVESTIGATE": 1}

    # the provenance handed to the interface must carry BOTH numbers
    facts = DF.facts_for_participant("uid-x", [rec(13262.0, 1, "INVESTIGATE"), rec(6869.0, 2)],
                                     hemisphere="Left")
    p = (facts.get("_provenance") or {}).get("impedance_ohms", "")
    assert "NEWEST" in p and "worst EVER" in p and "13262" in p, p


def test_survey_channel_names_are_reconciled_and_never_guessed():
    """A candidate says ONE_THREE_LEFT; the survey says ONE_AND_THREE_Left. A failed match must
    return None so the rule reports "not determinable" — inventing "no artefact present" is how a
    contaminated channel would pass the check it exists to fail."""
    from ClosedLoopDeployment import device_facts as DF
    m = {"ONE_AND_THREE_Left": {"ARTIFACT_NOT_PRESENT": 5},
         "ONE_AND_THREE_Right": {"SQC_ARTIFACT_PRESENT": 3}}
    assert DF._match_survey_channel(m, "ONE_THREE_LEFT", "Left") == "ONE_AND_THREE_Left"
    assert DF._match_survey_channel(m, "ONE_THREE_LEFT", "Right") == "ONE_AND_THREE_Right"
    assert DF._match_survey_channel(m, "ZERO_TWO_LEFT", "Left") is None
    assert DF._match_survey_channel(m, None, "Left") is None


def test_scan_folder_skips_an_unreadable_report_without_abandoning_the_batch(tmp_path):
    """One truncated export must not cost the other eleven hundred."""
    import json as _json
    from ClosedLoopDeployment import session_report_facts as SRF
    good = {"Groups": {"Final": [{"ProgramSettings": {"RateInHertz": 110.0, "SensingChannel": [
        {"HemisphereLocation": "HemisphereLocationDef.Left",
         "LowerCaptureAmplitudeInMilliAmps": 3.0,
         "UpperCaptureAmplitudeInMilliAmps": 5.0,
         "PulseWidthInMicroSecond": 100}]}}]}}
    (tmp_path / "ok.json").write_text(_json.dumps(good))
    (tmp_path / "broken.json").write_text("{not json")
    S = SRF.scan_folder(str(tmp_path))
    assert S["n_files"] == 2 and S["n_unreadable"] == 1
    assert S["capture_newest"]["Left"]["upper_mA"] == 5.0
    # 100 us is inside the 120 us ceiling, so this record is not a D27 violation
    assert S["capture_ceiling_violations"]["Left"] == {"violating": 0, "total": 1}


# --- D32 scope: the group we would program, not the device's history (2026-09-04) ---------------
def test_cycling_is_read_from_the_newest_active_sensing_group_not_device_wide(tmp_path):
    """Two bugs in one, both of which inflated a D32 failure.

    First, `Cycling.Enabled` was matched by path SUBSTRING, which also caught
    `DiagnosticData.LfpFrequencySnapshotEvents[].Cycling` — so an earlier pass reported cycling
    enabled in 15187 records when the group setting lives at `GroupSettings.Cycling.Enabled`.

    Second, and more important, D32 asks whether cycling is enabled in the BrainSense group being
    configured. Counting every group ever recorded answers "has this device ever cycled", a
    different question: across the real record cycling is enabled in 868 of 1867 active sensing
    groups, so a device-wide read fails the rule while the newest active sensing group has it off.
    """
    import json as _json
    from ClosedLoopDeployment import session_report_facts as SRF

    def report(stamp, cycling, has_sensing=True, active=True):
        ch = [{"HemisphereLocation": "HemisphereLocationDef.Left",
               "PulseWidthInMicroSecond": 100,
               "LowerCaptureAmplitudeInMilliAmps": 3.0,
               "UpperCaptureAmplitudeInMilliAmps": 5.0}] if has_sensing else []
        return {"Groups": {"Final": [{
            "ActiveGroup": active,
            "GroupSettings": {"Cycling": {"Enabled": cycling}},
            "ProgramSettings": {"RateInHertz": 110.0, "SensingChannel": ch}}]},
            # a snapshot event that also contains the word Cycling, which the substring match
            # used to fold into the group count
            "DiagnosticData": {"LfpFrequencySnapshotEvents": [{"Cycling": True}]}}

    (tmp_path / "a_20250101.json").write_text(_json.dumps(report("a", True)))
    (tmp_path / "b_20260101.json").write_text(_json.dumps(report("b", False)))
    S = SRF.scan_folder(str(tmp_path))

    # the device HAS cycled in a sensing group historically
    assert S["cycling_in_sensing_group"] is True
    # but the newest active sensing group has it off, and that is what D32 reads
    assert S["d32_newest_active_sensing_group"]["cycling_in_group"] is False
    # the snapshot event must not have been counted as a group setting
    assert not any("Cycling" in k and "snapshot" in k.lower()
                   for k in S["cycling_by_group_kind"])
    assert sum(S["cycling_by_group_kind"].values()) == 2, "one group setting per file, no extras"


def test_pocket_adaptor_stays_unknown_rather_than_assumed_absent(tmp_path, monkeypatch):
    """The session report does not carry it, so D32 must keep it unknown. Assuming absence would
    let a rule pass on a fact nobody checked, which is the failure mode this module exists to
    avoid.

    Pointed at a temporary store with the background rebuild switched off (2026-09-12). Since
    commit 56d04cfc the facts resolve through the store and, on a stale summary, START a real
    rebuild against the production root; a test reaching that path from the live record is the
    decision-96 class of accident, and this one did as soon as the daily ingest made the stored
    summary stale. The committed 2026-09-05 file is the fallback the test now exercises, which is
    the one that carries no pocket-adaptor field, so the assertion is unchanged.
    """
    from ClosedLoopDeployment import device_facts as DF
    try:
        from modules.CacheStore import store as st
    except ImportError:
        from CacheStore import store as st
    prev = st.DIR_OVERRIDE
    st.DIR_OVERRIDE = str(tmp_path)
    monkeypatch.setattr(DF, "SESSION_REPORT_SUMMARY_BACKGROUND", False)
    monkeypatch.setattr(DF, "_spawn_detached",
                        lambda argv, log: (_ for _ in ()).throw(AssertionError("launcher fired")))
    try:
        f, _p = DF.session_report_facts_for("2e3c75c00d7f4f37b53a048d195f11da",
                                            channel="ONE_THREE_LEFT", hemisphere="Left")
    finally:
        st.clear()                    # while still pointed at tmp_path; never the real root
        st.DIR_OVERRIDE = prev
    assert "has_pocket_adaptor" not in f or f["has_pocket_adaptor"] is None


def test_capture_amplitudes_exclude_zero_because_both_must_be_therapeutic():
    """Regression, 2026-09-04, found by running the prescription on the real RCS08 record.

    The pipeline selected the two capture amplitudes as the plain min and max of the observed
    amplitudes. On RCS08 the minimum is 0.0 mA, so the lower capture amplitude was stimulation
    switched OFF, which breaks two different things.

    It reintroduces the artefact confound the amplitude-response screen exists to remove: band
    power at 0 mA has no stimulation artefact in it and band power at 4.8 mA has a large one, so
    the difference is not interpretable as a physiological response to amplitude.

    And it produces a prescription the device rejects, because the adaptive amplitude limits
    inherit the capture amplitudes (D28) and the lower limit must be strictly above zero (D07).
    """
    import numpy as np
    import pandas as pd
    from ClosedLoopDeployment import pipeline as PL

    src = open(PL.__file__).read()
    assert "amps[amps > 0]" in src, "the therapeutic restriction is missing from the pipeline"
    assert "amps.min(), amps.max()" not in src, \
        "the unrestricted min/max selection is back; zero amplitude would be captured again"

    # the arms handed to threshold_placement must also carry the restriction, or the amplitudes
    # would be therapeutic while the power arms still contained stimulation-off samples
    assert "(amps > 0) & (amps <= lo_a)" in src
    assert "(amps > 0) & (amps >= hi_a)" in src


# --- the prescription: mode-dependent field sets and a validated time base (2026-09-04) --------
def test_the_programmable_field_set_depends_on_the_number_of_thresholds():
    """Dual Threshold has two thresholds and TWO onset durations; Single has one computed
    threshold and ONE onset duration; Single Inverse cannot drive therapy and has none.

    This is not a cosmetic difference. The manufacturer's troubleshooting table adjusts "Upper
    Onset" and "Lower Onset" in OPPOSITE directions to fix stimulation that is transiently too low
    (D51), which is only possible if they are two independently settable fields. And the single
    threshold is not typed in at all: the device computes it as 0.75 x (Upper - Lower) + Lower
    (D20), so presenting it as an editable field would invite a clinician to enter a value the
    device will overwrite.
    """
    from StimOptimizer.routines import percept_adaptive as PA
    from ClosedLoopDeployment import prescription as PR, types as TY

    tp = TY.ThresholdPlan(upper=10.0, lower=6.0, capture_amp_low=3.0, capture_amp_high=5.0)

    dual = PR.prescribe(mode=PA.DUAL, threshold_plan=tp, timing=PA.timing_plan(mode=PA.DUAL))
    names = [f.name for f in dual.fields]
    assert "Upper onset duration" in names and "Lower onset duration" in names
    assert "Upper LFP threshold" in names and "Lower LFP threshold" in names
    assert "Onset duration" not in names, "dual mode must not present a single merged onset"

    single = PR.prescribe(mode=PA.SINGLE, threshold_plan=tp, timing=PA.timing_plan(mode=PA.SINGLE))
    snames = [f.name for f in single.fields]
    assert "Onset duration" in snames
    assert "Upper onset duration" not in snames and "Lower onset duration" not in snames
    assert "Single LFP threshold" in snames
    # and it carries the device's own formula, not either captured threshold
    sf = next(f for f in single.fields if f.name == "Single LFP threshold")
    assert abs(float(sf.value) - (0.75 * (10.0 - 6.0) + 6.0)) < 1e-9

    inv = PR.prescribe(mode=PA.SINGLE_INVERSE, threshold_plan=tp)
    assert inv.fields == [], "a sensing-only mode has no closed-loop prescription"
    assert "cannot drive therapy" in inv.note


def test_the_onset_duration_is_reported_as_inoperative_when_it_spans_one_window():
    """The interaction most likely to be missed, and it silently removes a safety feature.

    Averaging is non-overlapping (D14), so the onset expresses itself as ceil(onset / averaging)
    controller steps. At one step the onset does nothing: the first averaged sample past a
    threshold already satisfies it. Because the published dual-mode onset range tops out at 2 s,
    ANY averaging duration of 2 s or more makes the onset inoperative at every value the clinician
    can choose — including the 4096 ms this module recommends to match the validated biomarker.
    """
    from ClosedLoopDeployment import prescription as PR

    # the manufacturer's own defaults are exactly one window, so the onset does nothing there either
    assert PR.onset_windows(1200.0, 1200.0)["windows"] == 1
    assert PR.onset_windows(1200.0, 1200.0)["inoperative"] is True

    # only the top of the range against the default averaging gives a real filter
    assert PR.onset_windows(2000.0, 1200.0)["windows"] == 2
    assert PR.onset_windows(2000.0, 1200.0)["inoperative"] is False

    # at the biomarker-matched averaging duration, nothing in the published range is operative
    for onset in (1200.0, 1600.0, 2000.0):
        r = PR.onset_windows(onset, 4096.0)
        assert r["windows"] == 1 and r["inoperative"] is True, onset
        assert "does NOTHING" in r["why"]

    with pytest.raises(ValueError):
        PR.onset_windows(1200.0, 0.0)


def test_a_degenerate_time_base_suppresses_the_per_hour_figures():
    """Regression, 2026-09-04. A caller converted epoch SECONDS as though they were nanoseconds,
    compressing fourteen months into one second of 1970. The interval collapsed toward zero and
    transitions-per-hour came out as 3.4 billion against an observed span of zero hours. A rate
    against a near-zero denominator is broken rather than large, so it is now refused."""
    import numpy as np
    from ClosedLoopDeployment import prescription as PR

    rng = np.random.default_rng(0)
    power = rng.normal(1.0, 0.3, 400)

    bad = PR.duty_cycle(power, upper=1.2, lower=0.8, dt_s=1e-9, averaging_ms=1200.0)
    assert bad.transitions_per_hour is None
    assert bad.hours_observed is None
    assert any("outside the plausible range" in c for c in bad.caveats)

    # a sane time base still produces the figures
    t = np.arange(400) * 60.0
    ok = PR.duty_cycle(power, upper=1.2, lower=0.8, t_s=t, averaging_ms=1200.0)
    assert ok.hours_observed is not None and ok.hours_observed > 0
    assert abs(ok.hours_observed - (399 * 60.0) / 3600.0) < 1e-6

    # elapsed time is the SPAN, not the sample count times the interval: with a gap in the middle
    # the two differ, and using the count would inflate every per-hour figure
    t_gap = np.concatenate([np.arange(200) * 60.0, np.arange(200) * 60.0 + 100 * 3600.0])
    gapped = PR.duty_cycle(power, upper=1.2, lower=0.8, t_s=t_gap, averaging_ms=1200.0)
    assert gapped.hours_observed > 100, "the span must include the gap"


def test_duplicate_timestamps_do_not_collapse_the_sample_interval():
    """The real joined table has 1079 rows on 1023 distinct timestamps for one band-cell. Taking
    the median of ALL differences would include zeros and drive the interval to zero, which is the
    same failure as the unit error above by a different route."""
    import numpy as np
    from ClosedLoopDeployment import prescription as PR

    t = np.repeat(np.arange(300) * 120.0, 2)          # every timestamp duplicated
    power = np.tile(np.linspace(0.5, 1.5, 300), 2)
    r = PR.duty_cycle(power, upper=1.2, lower=0.8, t_s=t, averaging_ms=1200.0)
    assert r.hours_observed is not None
    assert any("share a timestamp" in c for c in r.caveats)


def test_the_pipeline_resolves_the_amplitude_column_instead_of_guessing_its_name():
    """Regression, 2026-09-04, and it is the second instance of this failure class in this module.

    The pipeline built the column name as an f-string, `f"amp_{hemisphere}"`, while the joined
    table spells it `amp_mA_Left` with the unit in the name. The membership test failed on every
    real report, so the threshold-placement block was SKIPPED — silently, because skipping a block
    raises nothing. `rep.threshold` came back None, the prescription was therefore absent, and the
    payload was indistinguishable from a participant who genuinely had no amplitude on record.

    The test asserts the name comes from `adapter.canonical_amp_col`, which is the single
    definition, and that a genuinely missing column now produces a BLOCKER rather than silence.
    """
    from ClosedLoopDeployment import adapter as AD, pipeline as PL

    assert AD.canonical_amp_col("Left") == "amp_mA_Left"
    src = open(PL.__file__).read()
    assert 'adapter.canonical_amp_col(hemisphere)' in src
    assert 'amp_col = f"amp_{hemisphere}"' not in src, "the hardcoded name is back"
    # a missing column must announce itself
    assert "no {hemisphere} amplitude column in the joined table" in src or \
           "amplitude column in the joined table" in src


def test_sparse_coverage_forbids_reporting_the_fractions_as_percentages_of_the_day():
    """The single most misreadable number the module produces, so it carries a structural flag.

    A chronic Percept record is sampled in short bursts minutes apart. On RCS08 one band-cell holds
    1079 samples of a 4.096 s window — about 1.2 hours of signal — spread across roughly 9,900
    hours of elapsed time, a coverage of about one part in eight thousand. So "half the samples sat
    above the upper threshold" is emphatically not "half the day sat above the upper threshold",
    and an interface that prints the latter overstates the result by orders of magnitude. The flag
    exists so the interface can refuse rather than relying on a caveat being read.
    """
    import numpy as np
    from ClosedLoopDeployment import prescription as PR

    rng = np.random.default_rng(1)
    power = rng.normal(1.0, 0.4, 500)

    # bursty: one sample every 230 s, each standing for a 4.096 s window
    sparse = PR.duty_cycle(power, upper=1.2, lower=0.8,
                           t_s=np.arange(500) * 230.0, averaging_ms=4096.0)
    assert sparse.fractions_are_of_observed_samples is True
    assert sparse.coverage_frac is not None and sparse.coverage_frac < 0.05
    assert any("must not be reported as" in c for c in sparse.caveats)
    # the fractions are still computed, because they remain useful for COMPARING configurations
    assert sparse.lfp_frac_above is not None

    # continuous: samples one averaging window apart, so the fractions are fractions of time
    dense = PR.duty_cycle(power, upper=1.2, lower=0.8,
                          t_s=np.arange(500) * 4.096, averaging_ms=4096.0)
    assert dense.fractions_are_of_observed_samples is False
    assert dense.coverage_frac > 0.9
    assert not any("must not be reported as" in c for c in dense.caveats)


def test_every_duty_cycle_field_reaches_the_payload():
    """Guards a bug that already happened: `coverage_frac`,
    `fractions_are_of_observed_samples` and `hours_of_signal` were added to the DutyCycle
    dataclass but not to the serialiser's key tuple, so the caveat text carried the coverage
    figures while the fields themselves serialised as null. An interface reading the fields alone
    could then have printed "49.6% of the day" for a record whose coverage is 0.012%.

    Comparing the dataclass against the serialiser mechanically means the next field cannot be
    forgotten, which is the point: this class of omission is invisible in every unit test that
    exercises the dataclass directly.
    """
    import dataclasses
    import re
    from ClosedLoopDeployment import adapter as AD, prescription as PR

    declared = {f.name for f in dataclasses.fields(PR.DutyCycle)}
    src = open(AD.__file__).read()
    i = src.index('"duty": None if rep.prescription.duty is None else {')
    block = src[i:i + 1800]
    # The character class must admit capitals: `mean_amplitude_mA` carries the unit in the name and
    # a lowercase-only pattern silently excluded it, which made this guard report a phantom
    # omission on its first run. A test that cries wolf gets disabled, so the pattern matches the
    # identifiers the codebase actually uses.
    emitted = set(re.findall(r'"([A-Za-z_]+)"', block))
    missing = declared - emitted
    assert not missing, f"DutyCycle fields never serialised to the payload: {sorted(missing)}"


def test_segment_replay_splits_at_gaps_instead_of_loosening_the_uniformity_guard():
    """A chronic Percept record is streaming bursts separated by days, and `dual_threshold`
    correctly REFUSES it: the controller advances its ramp by a rate times an interval, so a
    series whose interval jumps by six orders of magnitude would attribute a month-long recording
    gap to the ramp and march the amplitude to a limit nothing in the data supports. On the real
    RCS08 cell the largest departure from the median interval is over a million percent.

    Loosening the tolerance would turn a correct refusal into a wrong number, so the record is
    split at its gaps instead and each contiguous stretch replayed separately.
    """
    import numpy as np
    import pytest as _pytest
    from ClosedLoopDeployment import replay as RP, types as TY

    plan = TY.ThresholdPlan(upper=1.2, lower=0.8, capture_amp_low=1.4, capture_amp_high=4.8)
    rng = np.random.default_rng(3)

    # Three bursts of 40 uniform samples, separated by two multi-day gaps. The WITHIN-burst
    # cadence is the device's own averaging window rather than the chronic-snapshot cadence,
    # because a 230 s cadence now trips the ramp-resolution refusal before segmentation is even
    # reached — see the test below. That refusal is correct and this test is about the gap
    # splitting, so the bursts are sampled densely enough for the ramp to be representable.
    bursts = [np.arange(40) * 4.096 + off for off in (0.0, 5e5, 1.2e6)]
    t = np.concatenate(bursts)
    power = rng.normal(1.0, 0.35, t.size)

    # the single-shot replay must still refuse this, which is the premise of the whole function
    with _pytest.raises(Exception):
        RP.dual_threshold({"t_s": t, "power": power}, plan)

    r = RP.dual_threshold_segments(t, power, plan)
    assert r.params["n_segments"] == 3
    assert r.params["n_segments_used"] == 3
    assert r.frac_time_at_upper is not None and r.frac_time_at_lower is not None
    # coverage must be reported, because these fractions are of OBSERVED stretches only
    assert r.params["coverage_frac"] is not None and r.params["coverage_frac"] < 0.05
    assert "NOT fractions of the patient's day" in r.note

    # segments too short to exercise the control law are skipped and counted, not averaged in
    short = np.concatenate([np.arange(40) * 4.096, np.array([9e5, 9e5 + 4.096])])
    r2 = RP.dual_threshold_segments(short, rng.normal(1.0, 0.35, short.size), plan)
    assert r2.params["n_segments"] == 2 and r2.params["n_segments_used"] == 1
    assert r2.params["n_segments_skipped"] == 1, (
        "a 2-sample trailing segment is below the 3-step floor and must be skipped, not averaged in")

    # duplicated timestamps are collapsed rather than read as zero-length intervals
    dup = np.repeat(np.arange(40) * 4.096, 2)
    r3 = RP.dual_threshold_segments(dup, rng.normal(1.0, 0.35, dup.size), plan)
    assert r3.params.get("n_segments_used", 0) >= 1


def test_replay_refuses_a_cadence_that_cannot_represent_the_ramp():
    """The finding that matters more than the segmentation, and it is easy to miss.

    The device moves amplitude gradually: 2.5 minutes up, 5 minutes down by default. A replay
    advances the ramp by a rate times the sample interval, so samples arriving FARTHER APART than
    the transition duration make one step traverse the entire amplitude range. The simulated
    controller then jumps between the limits instantaneously, which is a bang-bang controller with
    the same thresholds and not the law the device implements, so its time-at-limit fractions
    describe a trajectory the device would never produce.

    On the real RCS08 record the chronic snapshots arrive every 230 s against a 150 s transition
    up, so the whole record fails this — which is why the honest output is a refusal naming the
    cadence rather than a set of plausible-looking fractions.
    """
    import numpy as np
    from ClosedLoopDeployment import replay as RP, types as TY

    plan = TY.ThresholdPlan(upper=1.2, lower=0.8, capture_amp_low=1.4, capture_amp_high=4.8)
    rng = np.random.default_rng(7)

    coarse = np.arange(60) * 230.0                      # the real RCS08 cadence
    r = RP.dual_threshold_segments(coarse, rng.normal(1.0, 0.35, 60), plan)
    assert r.params["ramp_resolvable"] is False
    assert r.frac_time_at_upper is None and r.n_transitions is None
    assert "NOT RESOLVABLE" in r.note
    assert "230" in r.note and "150" in r.note, "the note must name both durations"

    # sampled at the device's averaging rate, the ramp is resolvable and fractions are produced
    fine = np.arange(400) * 4.096
    r2 = RP.dual_threshold_segments(fine, rng.normal(1.0, 0.35, 400), plan)
    assert r2.params["ramp_resolvable"] is True
    assert r2.frac_time_at_upper is not None


def test_every_report_section_reaches_the_payload():
    """Generalises a bug that happened twice in one session.

    `replay` and `protocol` were both computed by the pipeline and then dropped on the floor,
    because `report_to_dict` simply had no key for them. Nothing failed: the panel rendered
    without a section it had no way to know existed, and the payload was indistinguishable from a
    run where those steps had not been reached. The duty-cycle fields went the same way an hour
    later.

    Comparing the DeploymentReport dataclass against the serialiser mechanically means the third
    instance cannot happen silently. Fields deliberately withheld are named here with the reason,
    so withholding stays a decision rather than an oversight.
    """
    import dataclasses
    import re
    from ClosedLoopDeployment import adapter as AD
    from ClosedLoopDeployment.types import DeploymentReport

    # `candidates` and `manifest` are diagnostics rather than sections; `participant` is echoed at
    # the top level rather than nested. Everything else must appear as a payload key.
    WITHHELD = {"candidates", "manifest", "participant", "blockers"}

    src = open(AD.__file__).read()
    i = src.index("def report_to_dict(rep)")
    j = src.index("\ndef ", i + 10)
    body = src[i:j]
    emitted = set(re.findall(r'"([A-Za-z_]+)"\s*:', body))

    declared = {f.name for f in dataclasses.fields(DeploymentReport)} - WITHHELD
    missing = declared - emitted
    assert not missing, (
        f"DeploymentReport sections computed but never serialised: {sorted(missing)}. "
        f"Add a key to report_to_dict, or add the name to WITHHELD with a reason.")

    # AND RECURSE INTO THE NESTED SECTIONS, which is where this guard first failed. The version
    # above walked only the top-level report and therefore passed while `EligibilityReport.deferred`
    # was missing from the payload — the exact omission it was written to catch, one level down. A
    # completeness check that only checks the outer layer gives false assurance, which is worse than
    # no check, because it stops anyone looking.
    from ClosedLoopDeployment.types import (EligibilityReport, CoherenceReport, ThresholdPlan,
                                            ReplayResult, Protocol, EdgeEstimate)
    NESTED_WITHHELD = {
        # The replay's per-step trajectories — the time base, the state sequence and the amplitude
        # itself — are one value per controller step over months of recording. Far too large for a
        # payload, and the fractions plus the transition count are what a reader acts on. Withheld
        # deliberately and declared here, which is the distinction this guard exists to enforce: a
        # field absent by decision is listed with its reason, and a field absent by oversight fails
        # the test. `amplitude_mA` was found by the recursion on its first run.
        ReplayResult: {"t_s", "state", "amplitude_mA"},
        # Rendered through as_rows() rather than field by field.
        Protocol: set(),
        EligibilityReport: set(),
        CoherenceReport: set(),
        ThresholdPlan: set(),
        EdgeEstimate: set(),
    }
    for cls, withheld in NESTED_WITHHELD.items():
        want = {f.name for f in dataclasses.fields(cls)} - withheld
        gone = want - emitted
        assert not gone, (
            f"{cls.__name__} fields never serialised to the payload: {sorted(gone)}. "
            f"Add them to report_to_dict, or to NESTED_WITHHELD with a reason.")


def test_the_capture_separation_floor_has_exactly_one_definition():
    """Regression, 2026-09-05. `MIN_CAPTURE_SEPARATION_D` was declared in TWO modules at DIFFERENT
    values for the SAME unpublished manufacturer rule: 0.5 in StimOptimizer's response test and 1.0
    in this module's threshold placement. Nothing linked them, so any cell with d between the two
    cleared the screen and was then called too-close downstream — and on RCS08 at 55 Hz every band
    that cleared separation sat between 0.51 and 0.93, i.e. entirely inside the gap.

    The PI's decision was to use the looser value for both. This asserts the mechanism rather than
    the number: `authority` must read the SAME object as `lfp_response`, so a future change moves
    both. Asserting only equality would pass again the moment someone re-typed the literal.
    """
    from StimOptimizer.routines import lfp_response as LR
    from ClosedLoopDeployment import authority as AU

    assert AU.MIN_CAPTURE_SEPARATION_D is LR.MIN_CAPTURE_SEPARATION_D, (
        "authority must import the constant, not restate it — two literals is how this drifted "
        "to a factor of two in the first place")
    assert LR.MIN_CAPTURE_SEPARATION_D == 0.5

    # and the source really does import rather than assign
    import inspect
    src = inspect.getsource(AU)
    assert "from StimOptimizer.routines.lfp_response import" in src
    assigns = [ln for ln in src.splitlines()
               if ln.strip().startswith("MIN_CAPTURE_SEPARATION_D") and "=" in ln
               and not ln.strip().startswith("#")]
    assert not assigns, f"authority re-assigns the constant: {assigns}"


# =============================================================================================
# E2 IS NO LONGER A SLOPE. It is how well the band tells high pain from low pain, it is computed
# on the biomarker page, and this module reads it.
#
# The PI rejected the straight-line slope this used to be: the stimulator switches state when band
# power crosses a value programmed into it, which is a yes-or-no decision about the state of the
# brain signal, so the quantity that decides whether a band is worth driving that decision with has
# to be a quantity about telling two states apart. That is the area under the curve.
# =============================================================================================
def _auc_export_for(channel="CH", center_hz=20.5, auc=0.72, lo=0.61, hi=0.83,
                    answer=None, n_reports=30, n_samples=120):
    """A table shaped exactly like the one the biomarker page exports, with values put in by hand.

    Hand-made rather than computed so that a test of the PACKING cannot pass or fail because of
    something the estimator did. What is being checked here is that this module reads the table
    correctly, and that requires knowing the answer in advance.
    """
    from Biomarkers.routines import analytics
    if answer is None:
        answer = (analytics.BAND_PAIN_ESTABLISHED if (lo > 0.5 or hi < 0.5)
                  else analytics.BAND_PAIN_NOT_RESOLVED)
    return pd.DataFrame([{
        "channel": channel, "contacts": "0-2", "brain_side": "Left",
        "band_center_hz": float(center_hz), "band_low_hz": center_hz - 2.5,
        "band_high_hz": center_hz + 2.5, "band_width_hz": 5.0,
        "band_fully_inside_8_to_30_hz": True,
        "answer": answer, "auc": auc, "auc_low": lo, "auc_high": hi,
        "no_relationship_value": 0.5, "p_two_sided": 0.01,
        "n_pain_reports": n_reports, "n_spectral_samples": n_samples,
        "n_high_pain_samples": 60, "n_low_pain_samples": 60,
        "pain_split_rule": "the pain scores were split into thirds, using one score per pain report",
        "confidence_level": 0.95, "power_feature": "a standardised logarithm of band power",
        "why": "a sentence from the biomarker page",
    }])


def test_state_edge_reads_the_table_the_biomarker_page_exported():
    """The intended route, and what the PI asked for: the number is worked out once on the biomarker
    page and inherited here. Nothing is recomputed, so the deployment panel and the biomarker page
    cannot print two different numbers for the same band."""
    tbl = _auc_export_for(auc=0.72, lo=0.61, hi=0.83)
    e = E.state_edge(tbl, channel="CH", center_hz=20.5)
    assert e.name == "E2"
    assert abs(e.estimate - (0.72 - 0.5)) < 1e-12, e.estimate
    assert abs(e.ci[0] - (0.61 - 0.5)) < 1e-12 and abs(e.ci[1] - (0.83 - 0.5)) < 1e-12, e.ci
    assert (e.n, e.n_clusters) == (120, 30), (e.n, e.n_clusters)
    assert e.resolved is True and e.sign == 1
    assert "read out of the table the biomarker page exported" in e.note, e.note
    # the raw value has to be legible on the estimate, not only the shifted one
    assert "0.720" in e.note and "0.610 to 0.830" in e.note, e.note
    assert "split into thirds" in e.note, e.note


def test_state_edge_stores_the_value_measured_against_half_so_resolved_still_means_something():
    """THE CORRECTNESS POINT OF THE WHOLE REWIRING, and the one that would fail silently.

    An EdgeEstimate defines `resolved` as its interval excluding ZERO, and everything downstream
    reads only `resolved` and `sign`. An area under the curve is measured against 0.5, and its
    interval lies between 0 and 1, so storing it raw would make `resolved` true for every band ever
    computed and would destroy the one check this module exists to perform. 0.5 is therefore
    subtracted from the value and from both ends of its interval.

    A band whose interval runs from 0.47 to 0.66 has established nothing. Stored raw, that interval
    excludes zero and would read as established. Stored shifted, it spans zero and reads as
    unresolved, which is the truth.
    """
    established = E.state_edge(_auc_export_for(auc=0.72, lo=0.61, hi=0.83),
                               channel="CH", center_hz=20.5)
    undecided = E.state_edge(_auc_export_for(auc=0.56, lo=0.47, hi=0.66),
                             channel="CH", center_hz=20.5)
    assert established.resolved is True, established.ci
    assert undecided.resolved is False, undecided.ci
    assert undecided.estimate is not None, "an unresolved band must still carry its value"
    assert undecided.ci[0] < 0.0 < undecided.ci[1], undecided.ci
    # both raw intervals sit wholly above zero, which is exactly why the shift is load-bearing
    assert 0.61 > 0 and 0.47 > 0
    # and a band where more power goes with LESS pain reads as a negative sign, not as absent
    other_way = E.state_edge(_auc_export_for(auc=0.28, lo=0.17, hi=0.39),
                             channel="CH", center_hz=20.5)
    assert other_way.resolved is True and other_way.sign == -1, (other_way.ci, other_way.sign)
    assert abs(other_way.estimate + 0.22) < 1e-12, other_way.estimate


def test_state_edge_names_the_quantity_so_nobody_reads_it_as_a_slope():
    """It used to be a slope in pain points per unit of power. It is not one now, and the estimate
    has to say so on itself, because a reader who assumes the old meaning will read 0.22 as a tiny
    effect when it is in fact a band that separates high pain from low pain 72% of the time."""
    e = E.state_edge(_auc_export_for(), channel="CH", center_hz=20.5)
    assert "coin flipping" in e.scale, e.scale
    assert "area under the curve minus 0.5" in e.scale, e.scale
    assert e.scale == E.E2_QUANTITY
    assert "slope" not in e.scale.lower(), e.scale


def test_state_edge_returns_exactly_what_the_biomarker_page_computes_on_this_modules_own_table():
    """The second route. When no exported table is handed in, this module's own table of spectral
    samples goes to the SAME estimator on the biomarker side.

    Every field is compared against the biomarker page's own result on the same rows. An equality
    check rather than a tolerance, because these are meant to be the same numbers and not merely
    close ones -- a tolerance here would let a second implementation creep back in.
    """
    from Biomarkers.routines import analytics
    T = _toy_table(n_epochs=45, per_epoch=4, seed=5)
    e = E.state_edge(T, channel="CH", center_hz=20.5)
    out = analytics.band_pain_auc_from_table(T, channel="CH", center_hz=20.5, pain_column="nrs",
                                             power_column="power_linear",
                                             group_column="report_id", n_boot=500, seed=0)
    assert e.estimate == out["auc"] - 0.5, (e.estimate, out["auc"])
    assert e.ci == (out["auc_low"] - 0.5, out["auc_high"] - 0.5), (e.ci, out["auc_low"])
    assert e.p == out["p_two_sided"], (e.p, out["p_two_sided"])
    assert (e.n, e.n_clusters) == (out["n_spectral_samples"], out["n_pain_reports"])
    assert e.cluster_unit == "report_id"
    assert "computed by the biomarker page's own estimator" in e.note, e.note


def test_state_edge_does_not_do_the_arithmetic_itself():
    """Asserted on the source, because the failure this guards against is someone pasting a
    calculation back into this function for convenience. Two copies would then drift and the panel
    and the biomarker page could print different numbers for the same band."""
    import inspect
    src = inspect.getsource(E.state_edge)
    assert ("band_pain_auc_from_table(" in src and "read_band_pain_auc_from_export(" in src), \
        "E2 must ask the biomarker page for the answer by one of its two routes"
    assert "_cluster_ols(" not in src, "E2 must not fit its own regression"
    assert "_small_sample_inference(" not in src, "E2 must not run its own bootstrap switch"
    assert "roc_auc_score" not in src, "E2 must not compute its own area under the curve"
    assert "_weighted_auc_matrix" not in src, "E2 must not compute its own area under the curve"


def test_state_edge_keeps_never_assessed_apart_from_nothing_established():
    """Three answers, and the two negative-looking ones must not be interchangeable.

    "We could not assess this band" has no value at all. "We assessed it and established nothing"
    has a value and an interval that spans 0.5. A reader who cannot tell these apart will throw away
    a band that was never measured, which has already happened three times in this project.
    """
    from Biomarkers.routines import analytics
    never = E.state_edge(_toy_table().drop(columns=["report_id"]), channel="CH", center_hz=20.5)
    assert never.estimate is None and never.ci is None and never.p is None
    assert never.resolved is False
    assert "NOT ASSESSED" in never.note, never.note
    assert "must not be read as a measurement" in never.note, never.note
    assert "no report_id column" in never.note, never.note
    assert "pseudoreplication" in never.note, never.note

    undecided = E.state_edge(_auc_export_for(auc=0.53, lo=0.44, hi=0.62),
                             channel="CH", center_hz=20.5)
    assert undecided.estimate is not None, "a band that was assessed must still carry its value"
    assert undecided.resolved is False
    # and the two states are genuinely different, not the same one twice
    assert (never.estimate is None) != (undecided.estimate is None)

    # a band that is simply not in the exported table is "not assessed", never a value near 0.5
    absent = E.state_edge(_auc_export_for(channel="CH"), channel="OTHER_CH", center_hz=20.5)
    assert absent.estimate is None and absent.resolved is False, absent
    assert "no row for contact pair" in absent.note, absent.note

    # the words on the biomarker side agree with the packing on this side
    assert analytics.band_pain_auc_from_table(
        _toy_table().drop(columns=["report_id"]), channel="CH",
        center_hz=20.5)["answer"] == analytics.BAND_PAIN_NOT_ASSESSED


def test_a_noise_band_is_not_resolved_on_this_modules_own_table_either():
    """The same three-way answer has to survive the route that does not go through the exported
    table, or the two routes would disagree about a band with nothing in it."""
    rng = np.random.default_rng(11)
    noisy = _toy_table(n_epochs=45, per_epoch=4, seed=11)
    noisy["nrs"] = rng.normal(5.0, 2.0, len(noisy))          # pain unrelated to power
    e = E.state_edge(noisy, channel="CH", center_hz=20.5)
    assert e.estimate is not None, "an unresolved edge must still carry its value"
    assert e.resolved is False, e.ci
    assert "Nothing is established" in e.note, e.note


def test_the_biomarker_module_still_does_not_import_the_closed_loop_module():
    """The import direction is load-bearing and this is the only way to check it honestly.

    ClosedLoopDeployment may import Biomarkers. Biomarkers must never import
    ClosedLoopDeployment, or the two would wait for each other and neither would load. The check
    runs in a FRESH interpreter on purpose: asking `sys.modules` inside this test process proves
    nothing, because this process imported the closed-loop module at the top of the file, so the
    name would be present whether or not Biomarkers pulled it in.
    """
    import subprocess, sys, os
    code = ("import sys;"
            "from Biomarkers.routines import analytics;"
            "print([m for m in sys.modules if m.startswith('ClosedLoopDeployment')])")
    # edges.py sits at <modules>/ClosedLoopDeployment/edges.py, so two levels up is <modules>,
    # which is the directory both packages are found under.
    modules_dir = os.path.dirname(os.path.dirname(os.path.abspath(E.__file__)))
    env = dict(os.environ, PYTHONPATH=modules_dir)
    r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr[-600:]
    assert r.stdout.strip().endswith("[]"), r.stdout


def test_the_closed_loop_module_reaches_the_biomarker_page_for_this_and_re_exports_the_toolkit():
    """The other half of the direction: this module DOES depend on Biomarkers now, and the names it
    used to define are still reachable under their old spellings so nothing downstream broke."""
    from Biomarkers.routines import analytics
    assert E.band_pain_auc_from_table is analytics.band_pain_auc_from_table
    assert E.read_band_pain_auc_from_export is analytics.read_band_pain_auc_from_export
    assert E.MIN_RELIABLE_CLUSTERS == analytics.MIN_RELIABLE_CLUSTERS
    for name in ("estimator_for", "wild_cluster_bootstrap_t", "wild_cluster_bootstrap_ci",
                 "_cluster_ols", "_small_sample_inference", "_BootstrapPlan",
                 "_rademacher_weights", "_cr0_variance", "MAX_ENUMERABLE_CLUSTERS",
                 "BAND_PAIN_ESTABLISHED", "BAND_PAIN_NOT_RESOLVED", "BAND_PAIN_NOT_ASSESSED"):
        assert getattr(E, name) == getattr(analytics, name), name
    # the deleted straight-line calculation must not be reachable from this module either
    for gone in ("band_pain_tracking", "band_pain_tracking_from_detail", "PAIN_TRACKING_TRACKS",
                 "PAIN_TRACKING_NOT_RESOLVED", "PAIN_TRACKING_NOT_ASSESSED"):
        assert not hasattr(E, gone), f"{gone} is still reachable from the closed-loop module"
