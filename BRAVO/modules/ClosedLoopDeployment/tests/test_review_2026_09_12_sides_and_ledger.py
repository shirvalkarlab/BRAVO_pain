"""The findings of the 2026-09-12 review of this module
(``artifacts/review_2026-09-12_ClosedLoopDeployment.md``), each pinned on the VALUE it changes.

C1  a band on a RIGHT contact is judged on the right lead and the right stimulator;
C2  the D26 ledger row is fed from the threshold plan this same run placed;
C3  D31 is told the 55 Hz BrainSense minimum, imported from Stim Optimizer, not retyped;
C5  D15 is measured from the summary's per-contact sensing-channel counts;
C11 the lead family used for D16's short limit is the sensing lead's own;
C12 one therapeutic current on record appends a blocker instead of silently placing nothing.
"""
import numpy as np
import pandas as pd
import pytest

try:
    from modules.ClosedLoopDeployment import (pipeline as PL, adapter as AD, device_facts as DF,
                                              constraints as CO)
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import (pipeline as PL, adapter as AD, device_facts as DF,
                                      constraints as CO)


# ------------------------------------------------------------------------------------------------
# a joined table with BOTH sides' currents, where only the right side moves the power
# ------------------------------------------------------------------------------------------------
def _two_sided_table(channel, n_epochs=8, per_epoch=6, right_slope=-40.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_epochs):
        amp_r = 1.0 + k * 0.5                       # the right stimulator is stepped up
        amp_l = 2.0 if k % 2 == 0 else 2.2          # the left stimulator barely moves
        for _ in range(per_epoch):
            lin = 600.0 + right_slope * amp_r + rng.normal(0, 3.0)
            rows.append({"t": float(k * 100), "channel": channel, "setting_epoch": k,
                         "center_hz": 24.5, "amp_mA_Left": amp_l, "amp_mA_Right": amp_r,
                         "power_linear": lin,
                         "nrs": 8.0 - 0.6 * amp_r + rng.normal(0, 0.1), "report_id": f"r{k}"})
    return pd.DataFrame(rows)


def _design_matrix(n=24, seed=1):
    rng = np.random.default_rng(seed)
    amp_r = np.repeat(np.array([1.0, 2.0, 3.0, 4.0]), n // 4)
    amp_l = np.where(np.arange(n) % 2 == 0, 2.0, 2.2)
    return pd.DataFrame({"epoch": np.arange(n, dtype=float), "amp_mA_Left": amp_l,
                         "amp_mA_Right": amp_r,
                         "nrs": 8.0 - 1.2 * amp_r + rng.normal(0, 0.1, n)})


def _run(monkeypatch, candidate, *, hemisphere="Left", pooled_e1=None, table=None,
         with_rules=False, design_matrix=None):
    T = table if table is not None else _two_sided_table(candidate["channel"])
    monkeypatch.setattr(AD, "joined_table_cached", lambda *a, **k: T)
    if not with_rules:
        monkeypatch.setattr(PL, "_optional", lambda name: None)
    return PL.run("p", psd_frame=pd.DataFrame({"x": [1]}), epochs=pd.DataFrame({"x": [1]}),
                  design_matrix=design_matrix, candidates=[candidate], hemisphere=hemisphere,
                  pooled_e1=pooled_e1, n_boot=50)


# ------------------------------------------------------------------------------------------------
# C1 -- the pipeline reads the band's own side
# ------------------------------------------------------------------------------------------------
def test_c1_a_right_side_candidate_is_read_against_the_right_current(monkeypatch):
    """The page always sent "Left"; the candidate says Right. E1, the manifest, the capture
    currents and E3 must all follow the candidate."""
    cand = {"channel": "ZERO_THREE_RIGHT", "center_hz": 24.5, "sensing_hemisphere": "Right",
            "actuated_hemisphere": "Right"}
    rep = _run(monkeypatch, cand, hemisphere="Left", design_matrix=_design_matrix())
    assert rep.manifest["hemisphere"] == "Right"
    e1 = rep.edges["E1"]
    assert e1.sign == -1 and e1.resolved is True, (e1.estimate, e1.ci)
    # the capture currents are the RIGHT stimulator's range: 1.0 to 4.5 mA, never the left's 2.0-2.2
    assert rep.threshold is not None
    assert (rep.threshold.capture_amp_low, rep.threshold.capture_amp_high) == (1.0, 4.5)
    # E3 regressed pain on the RIGHT current, where the relationship was planted
    e3 = rep.edges["E3"]
    assert e3.sign == -1 and e3.resolved is True, (e3.estimate, e3.ci, e3.note)
    assert "amp_mA_Right" in (e3.note or "") or e3.n == 24


def test_c1_the_same_table_read_on_the_left_side_finds_no_current_to_power_slope(monkeypatch):
    """The control: the left current barely moves in the same table, so a candidate that names
    the left side gets a flat, unresolved E1 and the left capture range. This is what every
    right-side band was being handed before the fix."""
    cand = {"channel": "ZERO_THREE_RIGHT", "center_hz": 24.5, "sensing_hemisphere": "Left",
            "actuated_hemisphere": "Left"}
    rep = _run(monkeypatch, cand, hemisphere="Right")
    assert rep.manifest["hemisphere"] == "Left"
    assert (rep.threshold.capture_amp_low, rep.threshold.capture_amp_high) == (2.0, 2.2)


def test_c1_a_candidate_naming_only_its_sensing_side_is_read_on_that_side(monkeypatch):
    cand = {"channel": "ZERO_THREE_RIGHT", "center_hz": 24.5, "sensing_hemisphere": "Right"}
    rep = _run(monkeypatch, cand, hemisphere="Left")
    assert rep.manifest["hemisphere"] == "Right"
    assert rep.threshold.capture_amp_high == 4.5


def test_c1_a_candidate_with_no_side_falls_back_to_the_callers_side(monkeypatch):
    cand = {"channel": "ZERO_THREE_RIGHT", "center_hz": 24.5}
    rep = _run(monkeypatch, cand, hemisphere="Right")
    assert rep.manifest["hemisphere"] == "Right"
    rep = _run(monkeypatch, cand, hemisphere="Left")
    assert rep.manifest["hemisphere"] == "Left"


# ------------------------------------------------------------------------------------------------
# C1 / C11 -- the device facts read the SENSING lead, and the STIMULATED side's capture
# ------------------------------------------------------------------------------------------------
class _Rec:
    def __init__(self, metadata, date):
        self.metadata, self.date = metadata, date


def _imp_rec(date, left_worst, right_worst, left_model="LEAD_B33015", right_model="LEAD_3389",
             amplitude="0.4mA"):
    return _Rec({"Status": "GOOD", "Amplitude": amplitude,
                 "Left": {"LeadModel": left_model, "Monopolar": [1000.0] * 8,
                          "Bipolar": [[1000.0, left_worst]]},
                 "Right": {"LeadModel": right_model, "Monopolar": [1000.0] * 8,
                           "Bipolar": [[900.0, right_worst]]}}, date)


_SUMMARY = {
    "n_files": 3,
    "capture_newest": {"Left": {"lower_mA": 2.0, "upper_mA": 3.0, "pw_us": 100.0},
                       "Right": {"lower_mA": 1.5, "upper_mA": 2.5, "pw_us": 160.0}},
    "artifact_status": {"ZERO_AND_THREE_Left": {"ARTIFACT_NOT_PRESENT": 10},
                        "ZERO_AND_THREE_Right": {"SQC_ARTIFACT_PRESENT": 9, "ARTIFACT_NOT_PRESENT": 1}},
    "lfp_bins_median_uvp": {"ZERO_AND_THREE_Left": {"24.41": 0.5},
                            "ZERO_AND_THREE_Right": {"24.41": 2.0, "25.39": 1.9}},
    "sensing_channels": {"ZERO_AND_THREE": 100, "ZERO_THREE_LEFT": 5, "ZERO_THREE_RIGHT": 21975,
                         "ZERO_TWO_LEFT": 626},
}


@pytest.fixture
def summary(monkeypatch):
    monkeypatch.setattr(DF, "_load_summary",
                        lambda uid: (_SUMMARY, {"source": "current", "sentence": "test summary",
                                                "launch": None}))


def test_c1_and_c11_sensing_facts_come_from_the_sensing_lead_and_capture_from_the_actuated_side(summary):
    recs = [_imp_rec(1, 7286.0, 4100.0)]
    f = DF.facts_for_participant("2e3c75c00d7f4f37b53a048d195f11da", recs,
                                 sensing_hemisphere="Right", actuated_hemisphere="Right",
                                 channel="ZERO_THREE_RIGHT")
    prov = f["_provenance"]
    # D16: the RIGHT lead's worst pair and the RIGHT lead's family
    assert f["impedance_ohms"] == 4100.0 and "on the Right lead" in prov["impedance_ohms"]
    assert f["lead_type"] == "1x4" and "LEAD_3389 on the Right lead" in prov["lead_type"]
    # D17: the RIGHT survey, whose artefact is the prevailing state
    assert f["artifact_flags"] == ["SQC_ARTIFACT_PRESENT"]
    assert "channel ZERO_AND_THREE_Right" in prov["artifact_flags"]
    # D09: the RIGHT survey's bins
    assert f["lfp_bins_uvp"] == [(24.41, 2.0), (25.39, 1.9)]
    # D24/D27/D28 and D34: the RIGHT (stimulated) side's capture and paused amplitude
    assert (f["capture_amp_low_mA"], f["capture_amp_high_mA"], f["capture_pulse_width_us"]) == (1.5, 2.5, 160.0)
    assert f["paused_amplitude_mA"] == 2.0 and "Right hemisphere" in prov["paused_amplitude_mA"]

    # the same record asked about on the left: every one of those values is the left's
    g = DF.facts_for_participant("2e3c75c00d7f4f37b53a048d195f11da", recs,
                                 sensing_hemisphere="Left", actuated_hemisphere="Left",
                                 channel="ZERO_THREE_LEFT")
    assert g["impedance_ohms"] == 7286.0 and g["lead_type"] == "sensight"
    assert g["artifact_flags"] == [] and g["lfp_bins_uvp"] == [(24.41, 0.5)]
    assert (g["capture_amp_low_mA"], g["capture_amp_high_mA"], g["capture_pulse_width_us"]) == (2.0, 3.0, 100.0)
    assert g["paused_amplitude_mA"] == 2.5


def test_c1_a_contralateral_pairing_reads_the_sensing_lead_and_the_stimulated_side_separately(summary):
    recs = [_imp_rec(1, 7286.0, 4100.0)]
    f = DF.facts_for_participant("2e3c75c00d7f4f37b53a048d195f11da", recs,
                                 sensing_hemisphere="Right", actuated_hemisphere="Left",
                                 channel="ZERO_THREE_RIGHT")
    assert f["impedance_ohms"] == 4100.0                          # the sensing lead
    assert f["lfp_bins_uvp"] == [(24.41, 2.0), (25.39, 1.9)]      # the sensing survey
    assert (f["capture_amp_low_mA"], f["capture_amp_high_mA"]) == (2.0, 3.0)   # the stimulated side
    assert f["paused_amplitude_mA"] == 2.5


def test_c1_the_plain_hemisphere_keyword_still_means_both_sides(summary):
    """A caller that names one side gets one-sided facts, exactly as before the split."""
    recs = [_imp_rec(1, 7286.0, 4100.0)]
    f = DF.facts_for_participant("2e3c75c00d7f4f37b53a048d195f11da", recs, hemisphere="Right",
                                 channel="ZERO_THREE_RIGHT")
    assert f["impedance_ohms"] == 4100.0 and f["capture_amp_high_mA"] == 2.5


# ------------------------------------------------------------------------------------------------
# C5 -- D15 measured per contact
# ------------------------------------------------------------------------------------------------
def test_c5_d15_is_measured_from_the_summarys_sensing_channel_counts(summary):
    f, p = DF.session_report_facts_for("2e3c75c00d7f4f37b53a048d195f11da",
                                       channel="ZERO_THREE_LEFT", sensing_hemisphere="Left",
                                       actuated_hemisphere="Left")
    assert f["channel_is_brainsense_setup_channel"] is True
    assert "measured: 5 groups carried ZERO_THREE_LEFT as a SensingChannel on the Left side" \
        in p["channel_is_brainsense_setup_channel"]
    # a contact the record never configured for sensing on that side: False, not a copied True
    f, p = DF.session_report_facts_for("2e3c75c00d7f4f37b53a048d195f11da",
                                       channel="ONE_THREE_RIGHT", sensing_hemisphere="Right",
                                       actuated_hemisphere="Right")
    assert f["channel_is_brainsense_setup_channel"] is False
    assert "0 groups" in p["channel_is_brainsense_setup_channel"]
    # the sideless key (ZERO_AND_THREE: 100) is never attributed to a side
    assert DF.setup_channel_count(_SUMMARY["sensing_channels"], "ZERO_THREE_LEFT", "Left") == 5
    assert DF.setup_channel_count(_SUMMARY["sensing_channels"], "ZERO_THREE_RIGHT", "Right") == 21975
    assert DF.setup_channel_count(_SUMMARY["sensing_channels"], "ZERO_TWO_RIGHT", "Right") == 0


def test_c5_no_sensing_channel_block_means_no_d15_key_never_a_pass(monkeypatch):
    S = {k: v for k, v in _SUMMARY.items() if k != "sensing_channels"}
    monkeypatch.setattr(DF, "_load_summary",
                        lambda uid: (S, {"source": "current", "sentence": "s", "launch": None}))
    f, _ = DF.session_report_facts_for("2e3c75c00d7f4f37b53a048d195f11da",
                                       channel="ZERO_THREE_LEFT", hemisphere="Left")
    assert "channel_is_brainsense_setup_channel" not in f
    # and the stated block no longer carries it, so nothing can pass on the old statement
    assert "channel_is_brainsense_setup_channel" not in DF.PI_STATED_FACTS["2e3c75c00d7f4f37b53a048d195f11da"]


# ------------------------------------------------------------------------------------------------
# C3 -- one 55 Hz
# ------------------------------------------------------------------------------------------------
def test_c3_d31_is_told_the_brainsense_minimum_and_it_is_stim_optimizers_own_number():
    try:
        from modules.StimOptimizer.routines.percept_adaptive import MIN_ADAPTIVE_RATE_HZ
    except ImportError:                                          # pragma: no cover
        from StimOptimizer.routines.percept_adaptive import MIN_ADAPTIVE_RATE_HZ
    stated = DF.PI_STATED_FACTS["2e3c75c00d7f4f37b53a048d195f11da"]
    assert stated["brainsense_min_rate_hz"] == MIN_ADAPTIVE_RATE_HZ == 55.0
    f = DF.facts_for_participant("2e3c75c00d7f4f37b53a048d195f11da", [], hemisphere="Left")
    assert f["brainsense_min_rate_hz"] == 55.0
    assert "MIN_ADAPTIVE_RATE_HZ" in f["_provenance"]["brainsense_min_rate_hz"]
    # it reaches the participant dict D31 reads
    part = PL._participant_facts("2e3c75c00d7f4f37b53a048d195f11da", f, CO)
    assert part["brainsense_min_rate_hz"] == 55.0
    # 40 Hz on the left: never demonstrated in a BrainSense group, and below the minimum -> False
    assert CO._p_d31({"rate_hz": 40.0, "pulse_width_us": 60.0, "sensing_hemisphere": "Left"},
                     part) is False
    # 55 Hz at 100 us on the left: demonstrated 280 times -> True through the pair table
    assert CO._p_d31({"rate_hz": 55.0, "pulse_width_us": 100.0, "sensing_hemisphere": "Left"},
                     part) is True
    # without the minimum (the state before this change) 40 Hz was "not determinable", not False
    assert CO._p_d31({"rate_hz": 40.0, "pulse_width_us": 60.0, "sensing_hemisphere": "Left"},
                     dict(part, brainsense_min_rate_hz=None)) is None


# ------------------------------------------------------------------------------------------------
# C2 -- the D26 row is fed from the plan
# ------------------------------------------------------------------------------------------------
def _pooled(slope, se, p):
    return {"pooled_direction": "band power falls as current rises", "pooled_slope_per_mA": slope,
            "pooled_slope_stderr": se, "pooled_slope_p": p, "n": 13, "n_visits": 4,
            "verdict": "ok", "curves": False, "peaks_inside": False, "peak_mA": float("nan"),
            "p_curvature": 0.41, "r2_linear": 0.6, "r2_quadratic": 0.61}


def _rows(rep):
    el = rep.eligibility
    out = {}
    for bucket in ("failures", "unknowns", "advisories", "deferred"):
        for r in getattr(el, bucket, []) or []:
            out[r["rule_id"]] = (bucket, r)
    return out


def test_c2_the_d26_row_reads_the_alert_the_same_run_predicted(monkeypatch):
    cand = {"channel": "ZERO_TWO_LEFT", "center_hz": 24.5, "sensing_hemisphere": "Left",
            "actuated_hemisphere": "Left"}
    # an established, right-signed pooled slope: no alert, so D26 passes and (not being a
    # recorded-on-pass rule) leaves no row
    rep = _run(monkeypatch, cand, pooled_e1=_pooled(-3.6, 1.2, 0.01), with_rules=True)
    assert rep.threshold is not None and rep.threshold.predicted_recapture_alert is False
    assert "D26" not in _rows(rep)
    # a slope whose interval spans zero, sign right: since 2026-09-13 (PI rule, "established
    # means mean only") the alert follows the SIGN, so none is predicted and D26 passes; the
    # unestablished interval travels as a caveat in the plan's warnings, not in the D26 row
    rep = _run(monkeypatch, cand, pooled_e1=_pooled(-3.6, 9.9, 0.72), with_rules=True)
    assert rep.threshold.predicted_recapture_alert is False
    assert "D26" not in _rows(rep)
    assert any("CAVEAT: the interval spans zero" in w for w in rep.warnings)
    # an INVERTED slope (wrong sign on the point estimate): the alert is predicted, the row says
    # so, and the reason carries the plan's own sentence
    rep = _run(monkeypatch, cand, pooled_e1=_pooled(+3.6, 1.2, 0.01), with_rules=True)
    assert rep.threshold.predicted_recapture_alert is True
    bucket, row = _rows(rep)["D26"]
    assert (bucket, row["kind"]) == ("advisories", "advisory_failed")
    assert "a RECAPTURE THRESHOLDS alert IS predicted" in row["observed"]
    assert "inverted capture: INDICATED" in row["observed"]
    # and, before this change, the same run read "could not be determined"
    f = PL._facts_for(cand, None, None, "power_linear", threshold=None)
    assert "predicted_recapture_alert" not in f


def test_c2_a_plan_with_no_pooled_slope_leaves_d26_not_determinable_and_says_why(monkeypatch):
    """RCS08's committed band today: a plan is placed, no pooled titration slope is stored, so
    authority predicts nothing (decision 139) and the row must say that, not "no plan"."""
    cand = {"channel": "ZERO_TWO_LEFT", "center_hz": 24.5, "sensing_hemisphere": "Left",
            "actuated_hemisphere": "Left"}
    rep = _run(monkeypatch, cand, pooled_e1=None, with_rules=True)
    assert rep.threshold is not None and rep.threshold.predicted_recapture_alert is None
    bucket, row = _rows(rep)["D26"]
    assert (bucket, row["kind"]) == ("advisories", "advisory_not_determinable")
    assert row["observed"].startswith("a threshold plan was placed, but the alert could not be predicted")
    assert "no pooled titration slope is stored" in row["observed"]


def test_c2_no_plan_leaves_d26_not_determinable_rather_than_passing(monkeypatch):
    """A cell with no therapeutic current places no plan; D26 must not read that as no alert."""
    T = _two_sided_table("ZERO_TWO_LEFT")
    T["amp_mA_Left"] = 0.0
    cand = {"channel": "ZERO_TWO_LEFT", "center_hz": 24.5, "sensing_hemisphere": "Left",
            "actuated_hemisphere": "Left"}
    rep = _run(monkeypatch, cand, table=T, with_rules=True)
    assert rep.threshold is None
    bucket, row = _rows(rep)["D26"]
    assert (bucket, row["kind"]) == ("advisories", "advisory_not_determinable")
    assert row["observed"].startswith("no threshold plan was placed")


# ------------------------------------------------------------------------------------------------
# C12 -- one therapeutic current
# ------------------------------------------------------------------------------------------------
def test_c12_a_single_therapeutic_current_appends_a_blocker_and_places_no_plan(monkeypatch):
    T = _two_sided_table("ZERO_TWO_LEFT")
    T["amp_mA_Left"] = np.where(T["setting_epoch"] % 2 == 0, 0.0, 2.5)   # off, or 2.5 mA
    cand = {"channel": "ZERO_TWO_LEFT", "center_hz": 24.5, "sensing_hemisphere": "Left",
            "actuated_hemisphere": "Left"}
    rep = _run(monkeypatch, cand, table=T, pooled_e1=_pooled(-3.6, 1.2, 0.01))
    assert rep.threshold is None
    assert any("only one therapeutic Left amplitude on record" in b and "2.5 mA" in b
               for b in rep.blockers), rep.blockers
    assert rep.is_licensed() is False


# ------------------------------------------------------------------------------------------------
# C9 -- the open-ended last epoch, and one epoch assignment for the report and the simulation
# ------------------------------------------------------------------------------------------------
def _epochs(open_ended):
    t0 = pd.Timestamp("2026-09-01T00:00:00Z")
    ep = pd.DataFrame({"t_start": [t0, t0 + pd.Timedelta(hours=1)],
                       "t_end": [t0 + pd.Timedelta(hours=1), t0 + pd.Timedelta(hours=2)],
                       "amp_mA_Left": [1.0, 2.5], "epoch": [1.0, 2.0]})
    if open_ended is not None:
        ep["open_ended"] = [False, open_ended]
    return ep


def test_c9_a_sample_after_the_last_export_belongs_to_the_open_ended_epoch():
    t0 = pd.Timestamp("2026-09-01T00:00:00Z").timestamp()
    t = np.array([t0 + 1800, t0 + 3600, t0 + 5400, t0 + 7200, t0 + 7200 + 86400])
    # open-ended: the last epoch extends past its recorded t_end
    assert AD._assign_epoch(t, _epochs(True)).tolist() == [0, 1, 1, 1, 1]
    # not open-ended (or no column): the last epoch's t_end is a wall, as before
    assert AD._assign_epoch(t, _epochs(False)).tolist() == [0, 1, 1, -1, -1]
    assert AD._assign_epoch(t, _epochs(None)).tolist() == [0, 1, 1, -1, -1]
    # a sample exactly on a settings change belongs to the NEW epoch (unchanged rule)
    assert AD._assign_epoch(np.array([t0 + 3600]), _epochs(True)).tolist() == [1]


def test_c9_the_simulation_uses_the_one_epoch_assignment_not_a_private_copy():
    import ast, inspect
    src = inspect.getsource(AD.simulation_inputs_for_participant)
    tree = ast.parse(src)
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)}
    assert "_assign_epoch" in calls
    assert "searchsorted(es" not in src, "the private epoch lookup is back"


# ------------------------------------------------------------------------------------------------
# C10 -- one "which files are session reports" rule and one "newest" rule
# ------------------------------------------------------------------------------------------------
def test_c10_the_active_group_reader_uses_the_summarys_own_file_rules():
    import ast, inspect
    src = inspect.getsource(DF.active_sensing_group_facts)
    assert "_srf.session_report_files(" in src and "_srf.newest_by_stamp(" in src
    # code, not comments: no `"Session" in ...` comparison and no by-date `max(...)` remain
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Constant) and n.left.value == "Session":
            raise AssertionError("the inline session-report predicate is back")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "max":
            raise AssertionError("the by-date newest rule is back")


# ------------------------------------------------------------------------------------------------
# C8 -- the recordings the three-source build decoded reach the simulation
# ------------------------------------------------------------------------------------------------
def test_c8_the_simulation_is_handed_the_recordings_the_same_request_decoded(monkeypatch):
    """With ``loaded`` carrying the four objects, no recording is decoded again. Measured on
    RCS08: 98,719 input fields, 0 differing; 2.3 s decoded twice against 0.01 s handed over."""
    import inspect, types
    src = inspect.getsource(AD.report_for_participant)
    assert "loaded_sink=_3loaded" in src and "loaded=_3loaded" in src
    # behaviour: the real Biomarkers service, with its loaders replaced by ones that record
    # every call; handed the four objects, the simulation must call none of them
    import sys
    calls = []
    mods = [m for name, m in sys.modules.items()
            if name in ("Biomarkers.bravo_service", "modules.Biomarkers.bravo_service")]
    if not mods:
        # The Biomarkers service needs a configured Django (it raises ImproperlyConfigured, not
        # ImportError, without one); on such a runner the source assertions above and the live
        # proof in the implementation report stand, and this half is skipped.
        try:
            import importlib
            mods = [importlib.import_module("Biomarkers.bravo_service")]
        except Exception as exc:                                 # noqa: BLE001
            pytest.skip(f"the Biomarkers service needs a configured Django here: {type(exc).__name__}")
    for m in mods:
        monkeypatch.setattr(m, "_load_recordings", lambda uid, kinds: calls.append(("load", kinds)) or [])
        monkeypatch.setattr(m, "_raw_lsb_cache_cached", lambda *a, **k: calls.append(("cache",)) or {})
    loaded = {"power": [], "td": [], "psd": [], "cache": {"ZERO_TWO_LEFT": {"td": {}}}}
    out = AD.simulation_inputs_for_participant("u", contact="ZERO_TWO_LEFT", centre_hz=24.5,
                                               hemisphere="Left", epochs=None, loaded=loaded)
    assert calls == [], f"the simulation decoded recordings it was already handed: {calls}"
    assert out["n_pieces"] == 0
    # and without the hand-over it loads all three families and builds the cache, as before
    AD.simulation_inputs_for_participant("u", contact="ZERO_TWO_LEFT", centre_hz=24.5,
                                         hemisphere="Left", epochs=None, loaded=None)
    assert [c[0] for c in calls] == ["load", "load", "load", "cache"], calls
