"""The documented selection ranges of the closed-loop parameters, wired in on 2026-09-13.

Until that day the platform carried the ADAPT-PD trial's onset setting (1.2-2 s) as the device's
range and said every other range was unpublished. The FDA approval summary for BrainSense Adaptive
(P960009/S478, Table 2, p. 8) documents onset 0-6 min (Dual) / 0-30 s (Single), transitions
250 ms-30 min, thresholds 0.55-400 uVrms, amplitude limits 0-25.5 mA; the 2020 tip card documents
averaging 0-30 s. These tests pin the numbers to those sources, the two device rules that read
them, the parameter card's rows, and the per-participant record-derived values (decision 148).
"""
import pytest

from ClosedLoopDeployment import constraints as CON
from ClosedLoopDeployment import device_facts as DF
from ClosedLoopDeployment import prescription as PR
from ClosedLoopDeployment import timing_recommendation as TR
from StimOptimizer.routines import percept_adaptive as PA

SYNTHETIC_UID = "synthetic-test-participant"

# Independently authored timings exercise the private configuration contract.
SYNTHETIC_TIMINGS = {
    "onset_upper_ms": 12000.0, "onset_lower_ms": 12000.0, "averaging_ms": 3000.0,
    "transition_up_ms": 6000.0, "transition_down_ms": 9000.0,
    "detection_blanking_ms": 12000.0, "adaptive_startup_delay_ms": 5000.0}

@pytest.fixture(autouse=True)
def synthetic_configuration(tmp_path, monkeypatch):
    import json
    from modules.DecodeCommon.private_clinical_config import ENVIRONMENT_VARIABLE
    fields = {key: {"value_ms": value, "why": "Independent synthetic timing example",
                    "confidence": "Medium"} for key, value in SYNTHETIC_TIMINGS.items()}
    doc = {"schema_version": 1, "participants": {"synthetic-test-participant": {
        "safety_ceiling": {"values_mA": {"Left": 3.0, "Right": 3.0},
                           "provenance": "Independent synthetic ceiling", "source_commit": "a" * 40,
                           "evidence_ref": "synthetic/ceiling"},
        "timing": {"fields": fields, "provenance": "Independent synthetic example",
                   "source_commit": "a" * 40, "evidence_ref": "synthetic/timing"}}}}
    path = tmp_path / "timing.json"
    path.write_text(json.dumps(doc)); path.chmod(0o600)
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, str(path))




# --- the one home ------------------------------------------------------------------------------
def test_the_documented_ranges_are_the_fda_and_tip_card_values_and_cite_them():
    assert PA.ONSET_RANGE_DUAL_MS == (0.0, 30_000.0)   # the tablet, 2026-09-15; the FDA's 0-6 min is kept as ONSET_RANGE_DUAL_MS_FDA
    assert PA.ONSET_RANGE_DUAL_MS_FDA == (0.0, 360_000.0)
    assert PA.ONSET_RANGE_SINGLE_MS == (0.0, 30_000.0)
    assert PA.TRANSITION_RANGE_MS == (2_000.0, 1_800_000.0)   # WP p. 16 slider, confirmed on the tablet
    assert PA.AVERAGING_RANGE_MS == (0.0, 30_000.0)
    assert PA.LFP_THRESHOLD_RANGE_UVRMS == (0.55, 400.0)
    assert PA.ADAPTIVE_AMP_LIMIT_RANGE_MA == (0.0, 25.5)
    assert "P960009/S478" in PA.RANGE_SOURCE_FDA and "Table 2" in PA.RANGE_SOURCE_FDA
    assert "Tip Cards" in PA.RANGE_SOURCE_TIP_CARD
    assert PA.DOCUMENTED_RANGES["adaptive amplitude limit"]["source"].startswith("FDA SSED")
    assert "tablet" in PA.DOCUMENTED_RANGES["onset duration (dual)"]["source"].lower()
    assert "tablet" in PA.DOCUMENTED_RANGES["detection blanking duration"]["source"].lower()
    assert PA.DOCUMENTED_RANGES["averaging duration"]["source"].startswith("Medtronic BrainSense Tip Cards")
    # the trial's settings are kept, labelled as the trial's, and sit inside the device's range
    assert PA.ADAPT_PD_ONSET_RANGE_MS[PA.DUAL] == (1200.0, 2000.0)
    assert PA.ADAPT_PD_ONSET_RANGE_MS[PA.SINGLE] == (200.0, 500.0)
    # the one parameter with no range anywhere, the tablet included
    assert set(PA.UNPUBLISHED_RANGES) == {"adaptive startup delay"}
    assert PA.documented_range_ms("onset", PA.SINGLE) == PA.ONSET_RANGE_SINGLE_MS
    assert PA.documented_range_ms("detection_blanking") == (0.0, 30_000.0)


def test_the_closed_loop_module_reads_the_ranges_from_the_one_home_not_a_copy():
    assert CON.ONSET_DURATION_RANGE_MS["dual"] is PA.ONSET_RANGE_DUAL_MS
    assert CON.ONSET_DURATION_RANGE_MS["single"] is PA.ONSET_RANGE_SINGLE_MS
    assert CON.TIMING_RANGE_BY_KEY["averaging_ms_adaptive"] is PA.AVERAGING_RANGE_MS
    assert CON.TIMING_RANGE_BY_KEY["transition_up_s"] == (2.0, 1800.0)
    assert CON.TIMING_RANGE_BY_KEY["detection_blanking_ms_adaptive"] is PA.DETECTION_BLANKING_RANGE_MS
    assert PR.ONSET_RANGE_SINGLE_MS is PA.ONSET_RANGE_SINGLE_MS


# --- D21: the onset inside the documented range -----------------------------------------------
def test_d21_passes_the_documented_maximum_and_fails_one_past_it():
    """The documented endpoint passes; values above it fail."""
    base = {"threshold_mode": "dual", "onset_duration_ms": 30_000.0}
    assert CON._p_d21(base, {}) is True
    assert CON._p_d21(dict(base, onset_duration_ms=1200.0), {}) is True      # the trial's value
    assert CON._p_d21(dict(base, onset_duration_ms=7.0 * 60_000.0), {}) is False
    assert CON._p_d21(dict(base, onset_duration_ms=31_000.0), {}) is False
    assert CON._p_d21(dict(base, threshold_mode="single", onset_duration_ms=30_000.0), {}) is True
    assert CON._p_d21(dict(base, threshold_mode="single", onset_duration_ms=31_000.0), {}) is False
    assert CON._p_d21({"threshold_mode": "dual"}, {}) is None
    rule = next(r for r in CON.RULES if r.rule_id == "D21")
    assert "0-30 s" in rule.title and "tablet" in rule.source.lower() and "6 min" in rule.human_text
    assert "P960009/S478" in rule.page


# --- D20: declared timing judged against the envelope, not the default ------------------------
def test_d20_judges_a_declared_timing_against_the_documented_range_not_the_default():
    """Independent declared values inside the documented envelope pass."""
    running = {"threshold_mode": "dual",
               "declared_mode_timing": {"onset_ms_adaptive": 12_000.0, "transition_up_s": 6.0,
                                        "transition_down_s": 6.0, "averaging_ms_adaptive": 12_000.0,
                                        "detection_blanking_ms_adaptive": 12_000.0}}
    assert CON._p_d20(running, {}) is True
    defaults = {"threshold_mode": "dual",
                "declared_mode_timing": {"onset_ms_adaptive": 1200.0, "transition_up_s": 150.0}}
    assert CON._p_d20(defaults, {}) is True
    outside = {"threshold_mode": "dual",
               "declared_mode_timing": {"onset_ms_adaptive": 30_000.0, "transition_up_s": 0.1}}
    assert CON._p_d20(outside, {}) is False                                   # 100 ms < 250 ms
    over = {"threshold_mode": "single",
            "declared_mode_timing": {"onset_ms_adaptive": 31_000.0}}
    assert CON._p_d20(over, {}) is False                                      # single: 0-30 s
    # a declaration carrying only a key with no documented range gives no verdict
    blank_only = {"threshold_mode": "dual",
                  "declared_mode_timing": {"detection_blanking_ms_adaptive": 30_000.0}}
    # 2026-09-15: detection blanking has a range now (0-30 s, the tablet), so it IS judged; only a
    # key with no range anywhere (the startup delay) still leaves D20 undetermined.
    assert CON._p_d20(blank_only, {}) is True
    blank_over = {"threshold_mode": "dual",
                  "declared_mode_timing": {"detection_blanking_ms_adaptive": 31_000.0}}
    assert CON._p_d20(blank_over, {}) is False
    rule = next(r for r in CON.RULES if r.rule_id == "D20")
    assert "documented range" in rule.title and "FDA" in rule.source


# --- the device's running values, read from the session report ---------------------------------
def _group_d_channels():
    return [{"HemisphereLocation": "HemisphereLocationDef.Left",
             "AdaptiveTherapyStatus": "ADBSStatusDef.RUNNING",
             "UpperLfpThreshold": 120.0, "LowerLfpThreshold": 90.0,
             "UpperLimitInMilliAmps": 3.0, "LowerLimitInMilliAmps": 2.0,
             "SuspendAmplitudeInMilliAmps": 2.5,
             "TransitionUpInMilliSeconds": 6000, "TransitionDownInMilliSeconds": 6000,
             "RateInHertz": 100, "PulseWidthInMicroSecond": 100,
             "SensingSetup": {"FrequencyInHertz": 18.0, "AveragingDurationInMilliSeconds": 12000},
             "AdaptiveTherapy": {"UpperThresholdOnsetInMilliSeconds": 12000,
                                 "LowerThresholdOnsetInMilliSeconds": 12000,
                                 "DetectionBlankingDurationInMilliSeconds": 12000,
                                 "AdaptiveStartupDelayInMilliSeconds": 0}},
            {"HemisphereLocation": "HemisphereLocationDef.Right",
             "AdaptiveTherapyStatus": "ADBSStatusDef.RUNNING",
             "UpperLfpThreshold": 120.0, "LowerLfpThreshold": 90.0,
             "UpperLimitInMilliAmps": 2.5, "LowerLimitInMilliAmps": 1.5,
             "TransitionUpInMilliSeconds": 6000, "TransitionDownInMilliSeconds": 6000,
             "RateInHertz": 100, "PulseWidthInMicroSecond": 150,
             "SensingSetup": {"FrequencyInHertz": 18.0, "AveragingDurationInMilliSeconds": 12000},
             "AdaptiveTherapy": {"UpperThresholdOnsetInMilliSeconds": 12000,
                                 "LowerThresholdOnsetInMilliSeconds": 12000,
                                 "DetectionBlankingDurationInMilliSeconds": 12000,
                                 "AdaptiveStartupDelayInMilliSeconds": 0}}]


def test_programmed_timing_is_read_per_side_from_the_group_with_the_exports_own_field_names():
    t = DF.programmed_closed_loop_timing(_group_d_channels())
    assert set(t) == {"Left", "Right"}
    L = t["Left"]
    assert L["onset_upper_ms"] == 12000.0 and L["onset_lower_ms"] == 12000.0
    assert L["transition_up_ms"] == 6000.0 and L["transition_down_ms"] == 6000.0
    assert L["averaging_ms"] == 12000.0 and L["detection_blanking_ms"] == 12000.0
    assert L["adaptive_startup_delay_ms"] == 0.0
    assert L["upper_threshold"] == 120.0 and L["lower_threshold"] == 90.0
    assert L["upper_limit_mA"] == 3.0 and L["lower_limit_mA"] == 2.0
    assert L["suspend_amplitude_mA"] == 2.5 and L["adaptive_status"] == "RUNNING"
    assert t["Right"]["upper_limit_mA"] == 2.5 and t["Right"]["suspend_amplitude_mA"] is None
    assert DF.programmed_closed_loop_timing([]) == {}
    # a channel without the AdaptiveTherapy block gives None, never an invented number
    bare = [{"HemisphereLocation": "HemisphereLocationDef.Left"}]
    assert DF.programmed_closed_loop_timing(bare)["Left"]["onset_upper_ms"] is None


def test_the_active_group_reader_carries_the_timing_alongside_the_rate():
    d = {"SessionDate": "2025-01-01T00:00:00Z",
         "Groups": {"Final": [{"GroupId": "GroupIdDef.GROUP_D", "ActiveGroup": True,
                               "ProgramSettings": {"RateInHertz": 100,
                                                   "SensingChannel": _group_d_channels()}}]}}
    ag = DF.active_sensing_group_from_report(d)
    assert ag["active_sensing_group"] == "GROUP_D" and ag["active_sensing_group_rate_hz"] == 100.0
    assert ag["active_sensing_group_timing"]["Left"]["onset_upper_ms"] == 12000.0


# --- the record-derived table --------------------------------------------------------------
def test_private_timing_is_bound_to_the_synthetic_participant():
    from modules.DecodeCommon.private_clinical_config import ClinicalConfigurationUnavailable
    r = TR.for_participant(SYNTHETIC_UID)
    assert {k: v["value_ms"] for k, v in r.items()} == SYNTHETIC_TIMINGS
    assert all(v["confidence"] == "Medium" for v in r.values())
    assert all(v["provenance"] == "Independent synthetic example" for v in r.values())
    for uid in ("nobody", None):
        with pytest.raises(ClinicalConfigurationUnavailable):
            TR.for_participant(uid)


# --- the parameter card ------------------------------------------------------------------------
def _rows(**kw):
    from ClosedLoopDeployment.types import ThresholdPlan
    kw.update(threshold_plan=ThresholdPlan(upper=120, lower=90, capture_amp_low=1, capture_amp_high=2),
              participant_uid=SYNTHETIC_UID, hemisphere="Left")
    p = PR.prescribe(mode=PA.DUAL, timing=PA.timing_plan(mode=PA.DUAL),
                     candidate={"channel": "ONE_THREE_LEFT", "center_hz": 24.5,
                                "band_width_hz": 5.0, "threshold_mode": "dual"}, **kw)
    return {r["parameter"]: r for r in p.as_rows()}, p


def test_the_card_carries_the_record_derived_values_with_their_confidence_and_the_programmed_values():
    rows, p = _rows(record_timing=TR.for_participant(SYNTHETIC_UID),
                    programmed_timing=DF.programmed_closed_loop_timing(_group_d_channels())["Left"])
    assert rows["Upper onset duration"]["value"] == 12000.0
    assert rows["Upper onset duration"]["status"] == "derived"
    assert rows["Upper onset duration"]["confidence"] == "Medium"
    assert rows["Upper onset duration"]["range"] == PA.ONSET_RANGE_DUAL_MS
    assert "P960009/S478" in rows["Upper onset duration"]["range_source"]
    assert rows["Upper onset duration"]["programmed"] == 12000.0
    assert rows["Upper onset duration"]["confirm"] == "enterable"
    assert rows["Transition up duration"]["value"] == 6000.0
    assert rows["Transition up duration"]["programmed"] == 6000.0
    assert rows["Transition up duration"]["range"] == PA.TRANSITION_RANGE_MS
    assert rows["Transition up duration"]["confirm"] == "enterable"
    assert rows["Averaging duration"]["value"] == 3000.0
    assert rows["Averaging duration"]["programmed"] == 12000.0
    assert rows["Averaging duration"]["range"] == PA.AVERAGING_RANGE_MS
    assert rows["Averaging duration"]["confirm"] == "enterable"
    assert rows["Adaptive startup delay"]["value"] == 5000.0
    assert rows["Adaptive startup delay"]["programmed"] == 0.0
    assert rows["Adaptive startup delay"]["confirm"] == "check_on_device"     # no documented range
    assert rows["Detection blanking duration"]["value"] == 12000.0
    assert rows["Detection blanking duration"]["confirm"] == "enterable"     # 0-30 s on the tablet, 2026-09-15
    assert rows["Adaptive amplitude limit, upper"]["range"] == PA.ADAPTIVE_AMP_LIMIT_RANGE_MA
    assert rows["Adaptive amplitude limit, upper"]["programmed"] == 3.0
    assert rows["Upper LFP threshold"]["programmed"] == 120.0
    assert "uVrms" in rows["Upper LFP threshold"]["range_source"]
    assert rows["Upper LFP threshold"]["range"] is None                       # units differ: not applied
    assert len(p.unknowns) == 1 and "Startup Delay" in p.unknowns[0]
    assert "Detection Blanking" in p.unknowns[0]
    assert not any("Transition" in u for u in p.unknowns)


def test_without_complete_timing_evidence_the_card_refuses_to_invent_defaults():
    from modules.DecodeCommon.private_clinical_config import ClinicalConfigurationUnavailable
    with pytest.raises(ClinicalConfigurationUnavailable):
        _rows(record_timing={})


def _thirty_thirty():
    """An independently constructed boundary pair: onset equals averaging."""
    rows = TR.for_participant(SYNTHETIC_UID)
    for key in ("onset_upper_ms", "onset_lower_ms", "averaging_ms"):
        rows[key]["value_ms"] = 30000.0
    return rows


def test_synthetic_table_gives_four_confirmations_without_coupling():
    """The constructed 12 s onset over 3 s averaging gives four steps."""
    rows, p = _rows(record_timing=TR.for_participant(SYNTHETIC_UID))
    ow = PR.onset_windows(rows["Upper onset duration"]["value"], rows["Averaging duration"]["value"])
    assert ow["windows"] == 4 and ow["inoperative"] is False
    assert p.couplings == []


def test_the_onset_averaging_coupling_names_the_documented_ceiling_not_the_trials():
    rows, p = _rows(record_timing=_thirty_thirty())
    # 30 s onset against 30 s averaging is one controller step under the module's reading
    assert p.couplings and p.couplings[0]["fields"][0] == "Upper onset duration"
    assert "30 s" in p.couplings[0]["resolution"] and "6 min" not in p.couplings[0]["resolution"]
    assert "60000 ms" in p.couplings[0]["resolution"]
    assert "2000 ms" not in p.couplings[0]["resolution"]


# --- the Stim Optimizer's policy check ----------------------------------------------------------
def test_validate_policy_refuses_a_timing_or_limit_outside_the_documented_range():
    base = {"mode": PA.DUAL, "center_hz": 24.5, "band_width_hz": 5.0, "amp_min_mA": 1.4,
            "amp_max_mA": 4.8, "rate_hz": 55.0, "lfp_responds_to_stimulation": True}
    assert PA.validate_policy(base) == []
    assert PA.validate_policy(dict(base, onset_ms=30_000.0, transition_up_ms=30_000.0,
                                   transition_down_ms=4_000.0, averaging_ms=30_000.0)) == []
    bad = PA.validate_policy(dict(base, onset_ms=7.0 * 60_000.0, transition_up_ms=100.0,
                                  averaging_ms=31_000.0, amp_max_mA=26.0))
    assert len(bad) == 4
    assert any("onset duration 420000 ms is outside" in b for b in bad)
    assert any("transition up duration 100 ms is outside" in b for b in bad)
    assert any("averaging duration 31000 ms is outside" in b for b in bad)
    assert any("amp_max_mA 26 mA is outside" in b for b in bad)
    assert PA.validate_policy(dict(base, mode=PA.SINGLE, onset_ms=31_000.0))[0].startswith(
        "onset duration 31000 ms is outside the documented range 0-30000 ms")


# --- 2026-09-15 evening: the tablet's ranges on the card ---------------------------------------
def test_the_detection_blanking_row_carries_the_tablets_range_instead_of_not_published():
    rows, _ = _rows(record_timing=_thirty_thirty())
    r = rows["Detection blanking duration"]
    assert r["range"] == PA.DETECTION_BLANKING_RANGE_MS
    assert "NOT published" not in (r["range_source"] or "")
    assert "tablet" in r["range_source"].lower()
    assert "NOT published" in rows["Adaptive startup delay"]["range_source"]
