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


# --- impedance facts, and why they are NOT read through the file loader (2026-09-04) ------------
class _Rec:
    """Minimal stand-in for a Recording row: the impedance payload lives on `metadata`."""
    def __init__(self, metadata, date=0):
        self.metadata, self.date, self.pointer, self.hashed = metadata, date, "", ""


def _imp(worst_left, status="GOOD", date=1, model="LEAD_B33015"):
    return _Rec({"Status": status,
                 "Left": {"LeadModel": model, "Monopolar": [2605.0] * 8,
                          "Bipolar": [[0.0, 5752.0, worst_left], [0.0, 0.0, 6641.0], [0.0, 0.0, 0.0]]},
                 "Right": {"LeadModel": model, "Monopolar": [4044.0] * 8,
                           "Bipolar": [[0.0, 4044.0, 4059.0], [0.0, 0.0, 3664.0], [0.0, 0.0, 0.0]]}},
                date=date)


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

    # a frame carrying none of the named columns is reported as such, never as a healthy hash
    assert AD._frame_fingerprint(pd.DataFrame({"zz": [1]}), ("t",))[0] == "no_columns"
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

    Updated 2026-09-04: a frame carrying NONE of the named columns now returns "no_columns" rather
    than "hashed". The old assertion accepted "hashed" for that case, which was the behaviour that
    let a fingerprint over a nonexistent column list look healthy while tracking nothing.
    """
    from ClosedLoopDeployment import adapter as AD
    psd, _ = _tiny_inputs()
    assert AD._frame_fingerprint(psd, ("t", "channel", "log_psd"))[0] == "hashed"
    assert AD._frame_fingerprint(None, ("x",)) == ("none",)
    assert AD._frame_fingerprint(psd, ("nonexistent",))[0] == "no_columns"
    # a partial overlap still hashes, over the columns that ARE present, and names them
    fp = AD._frame_fingerprint(psd, ("t", "nonexistent"))
    assert fp[0] == "hashed" and [c for c, _ in fp[2]] == ["t"]


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
