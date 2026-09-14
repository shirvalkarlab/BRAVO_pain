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

RCS08 = "2e3c75c00d7f4f37b53a048d195f11da"


# --- the one home ------------------------------------------------------------------------------
def test_the_documented_ranges_are_the_fda_and_tip_card_values_and_cite_them():
    assert PA.ONSET_RANGE_DUAL_MS == (0.0, 360_000.0)
    assert PA.ONSET_RANGE_SINGLE_MS == (0.0, 30_000.0)
    assert PA.TRANSITION_RANGE_MS == (250.0, 1_800_000.0)
    assert PA.AVERAGING_RANGE_MS == (0.0, 30_000.0)
    assert PA.LFP_THRESHOLD_RANGE_UVRMS == (0.55, 400.0)
    assert PA.ADAPTIVE_AMP_LIMIT_RANGE_MA == (0.0, 25.5)
    assert "P960009/S478" in PA.RANGE_SOURCE_FDA and "Table 2" in PA.RANGE_SOURCE_FDA
    assert "Tip Cards" in PA.RANGE_SOURCE_TIP_CARD
    for name in ("onset duration (dual)", "transition up duration", "adaptive amplitude limit"):
        assert PA.DOCUMENTED_RANGES[name]["source"].startswith("FDA SSED")
    assert PA.DOCUMENTED_RANGES["averaging duration"]["source"].startswith("Medtronic BrainSense Tip Cards")
    # the trial's settings are kept, labelled as the trial's, and sit inside the device's range
    assert PA.ADAPT_PD_ONSET_RANGE_MS[PA.DUAL] == (1200.0, 2000.0)
    assert PA.ADAPT_PD_ONSET_RANGE_MS[PA.SINGLE] == (200.0, 500.0)
    # the only two parameters with no documented range anywhere found
    assert set(PA.UNPUBLISHED_RANGES) == {"adaptive startup delay", "detection blanking duration"}
    assert PA.documented_range_ms("onset", PA.SINGLE) == PA.ONSET_RANGE_SINGLE_MS
    assert PA.documented_range_ms("detection_blanking") is None


def test_the_closed_loop_module_reads_the_ranges_from_the_one_home_not_a_copy():
    assert CON.ONSET_DURATION_RANGE_MS["dual"] is PA.ONSET_RANGE_DUAL_MS
    assert CON.ONSET_DURATION_RANGE_MS["single"] is PA.ONSET_RANGE_SINGLE_MS
    assert CON.TIMING_RANGE_BY_KEY["averaging_ms_adaptive"] is PA.AVERAGING_RANGE_MS
    assert CON.TIMING_RANGE_BY_KEY["transition_up_s"] == (0.25, 1800.0)
    assert CON.TIMING_RANGE_BY_KEY["detection_blanking_ms_adaptive"] is None
    assert PR.ONSET_RANGE_SINGLE_MS is PA.ONSET_RANGE_SINGLE_MS


# --- D21: the onset inside the documented range -----------------------------------------------
def test_d21_passes_the_30_s_onset_rcs08_runs_and_fails_one_past_six_minutes():
    """Under the old rule RCS08's own programmed 30 s onset read as out of range (1.2-2 s)."""
    base = {"threshold_mode": "dual", "onset_duration_ms": 30_000.0}
    assert CON._p_d21(base, {}) is True
    assert CON._p_d21(dict(base, onset_duration_ms=1200.0), {}) is True      # the trial's value
    assert CON._p_d21(dict(base, onset_duration_ms=7.0 * 60_000.0), {}) is False
    assert CON._p_d21(dict(base, threshold_mode="single", onset_duration_ms=30_000.0), {}) is True
    assert CON._p_d21(dict(base, threshold_mode="single", onset_duration_ms=31_000.0), {}) is False
    assert CON._p_d21({"threshold_mode": "dual"}, {}) is None
    rule = next(r for r in CON.RULES if r.rule_id == "D21")
    assert "0-6 min" in rule.title and "FDA" in rule.source
    assert "P960009/S478" in rule.page


# --- D20: declared timing judged against the envelope, not the default ------------------------
def test_d20_judges_a_declared_timing_against_the_documented_range_not_the_default():
    """RCS08's running configuration (30 s onset, 4 s transitions, 30 s averaging) differs from
    every default and is inside every documented range: it must pass, where the old rule failed
    it for being adjusted."""
    running = {"threshold_mode": "dual",
               "declared_mode_timing": {"onset_ms_adaptive": 30_000.0, "transition_up_s": 4.0,
                                        "transition_down_s": 4.0, "averaging_ms_adaptive": 30_000.0,
                                        "detection_blanking_ms_adaptive": 30_000.0}}
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
    assert CON._p_d20(blank_only, {}) is None
    rule = next(r for r in CON.RULES if r.rule_id == "D20")
    assert "documented range" in rule.title and "FDA" in rule.source


# --- the device's running values, read from the session report ---------------------------------
def _group_d_channels():
    return [{"HemisphereLocation": "HemisphereLocationDef.Left",
             "AdaptiveTherapyStatus": "ADBSStatusDef.RUNNING",
             "UpperLfpThreshold": 167.0, "LowerLfpThreshold": 166.0,
             "UpperLimitInMilliAmps": 3.0, "LowerLimitInMilliAmps": 2.0,
             "SuspendAmplitudeInMilliAmps": 2.5,
             "TransitionUpInMilliSeconds": 4000, "TransitionDownInMilliSeconds": 4000,
             "RateInHertz": 55, "PulseWidthInMicroSecond": 100,
             "SensingSetup": {"FrequencyInHertz": 23.44, "AveragingDurationInMilliSeconds": 30000},
             "AdaptiveTherapy": {"UpperThresholdOnsetInMilliSeconds": 30000,
                                 "LowerThresholdOnsetInMilliSeconds": 30000,
                                 "DetectionBlankingDurationInMilliSeconds": 30000,
                                 "AdaptiveStartupDelayInMilliSeconds": 0}},
            {"HemisphereLocation": "HemisphereLocationDef.Right",
             "AdaptiveTherapyStatus": "ADBSStatusDef.RUNNING",
             "UpperLfpThreshold": 167.0, "LowerLfpThreshold": 166.0,
             "UpperLimitInMilliAmps": 2.5, "LowerLimitInMilliAmps": 1.5,
             "TransitionUpInMilliSeconds": 4000, "TransitionDownInMilliSeconds": 4000,
             "RateInHertz": 55, "PulseWidthInMicroSecond": 150,
             "SensingSetup": {"FrequencyInHertz": 23.44, "AveragingDurationInMilliSeconds": 30000},
             "AdaptiveTherapy": {"UpperThresholdOnsetInMilliSeconds": 30000,
                                 "LowerThresholdOnsetInMilliSeconds": 30000,
                                 "DetectionBlankingDurationInMilliSeconds": 30000,
                                 "AdaptiveStartupDelayInMilliSeconds": 0}}]


def test_programmed_timing_is_read_per_side_from_the_group_with_the_exports_own_field_names():
    t = DF.programmed_closed_loop_timing(_group_d_channels())
    assert set(t) == {"Left", "Right"}
    L = t["Left"]
    assert L["onset_upper_ms"] == 30000.0 and L["onset_lower_ms"] == 30000.0
    assert L["transition_up_ms"] == 4000.0 and L["transition_down_ms"] == 4000.0
    assert L["averaging_ms"] == 30000.0 and L["detection_blanking_ms"] == 30000.0
    assert L["adaptive_startup_delay_ms"] == 0.0
    assert L["upper_threshold"] == 167.0 and L["lower_threshold"] == 166.0
    assert L["upper_limit_mA"] == 3.0 and L["lower_limit_mA"] == 2.0
    assert L["suspend_amplitude_mA"] == 2.5 and L["adaptive_status"] == "RUNNING"
    assert t["Right"]["upper_limit_mA"] == 2.5 and t["Right"]["suspend_amplitude_mA"] is None
    assert DF.programmed_closed_loop_timing([]) == {}
    # a channel without the AdaptiveTherapy block gives None, never an invented number
    bare = [{"HemisphereLocation": "HemisphereLocationDef.Left"}]
    assert DF.programmed_closed_loop_timing(bare)["Left"]["onset_upper_ms"] is None


def test_the_active_group_reader_carries_the_timing_alongside_the_rate():
    d = {"SessionDate": "2026-09-11T15:30:00Z",
         "Groups": {"Final": [{"GroupId": "GroupIdDef.GROUP_D", "ActiveGroup": True,
                               "ProgramSettings": {"RateInHertz": 55,
                                                   "SensingChannel": _group_d_channels()}}]}}
    ag = DF.active_sensing_group_from_report(d)
    assert ag["active_sensing_group"] == "GROUP_D" and ag["active_sensing_group_rate_hz"] == 55.0
    assert ag["active_sensing_group_timing"]["Left"]["onset_upper_ms"] == 30000.0


# --- the record-derived table --------------------------------------------------------------
def test_rcs08s_record_derived_timing_is_the_decision_148_table_and_sits_inside_every_range():
    r = TR.for_participant(RCS08)
    assert {k: v["value_ms"] for k, v in r.items()} == {
        "onset_upper_ms": 30000.0, "onset_lower_ms": 30000.0, "averaging_ms": 30000.0,
        "transition_up_ms": 30000.0, "transition_down_ms": 30000.0,
        "detection_blanking_ms": 30000.0, "adaptive_startup_delay_ms": 15000.0}
    assert r["onset_upper_ms"]["confidence"] == "High"
    assert r["transition_up_ms"]["confidence"] == "Medium"
    assert r["detection_blanking_ms"]["confidence"] == "Low"
    assert all("decision 148" in v["provenance"] for v in r.values())
    lo, hi = PA.ONSET_RANGE_DUAL_MS
    assert lo <= r["onset_upper_ms"]["value_ms"] <= hi
    assert PA.TRANSITION_RANGE_MS[0] <= r["transition_up_ms"]["value_ms"] <= PA.TRANSITION_RANGE_MS[1]
    assert PA.AVERAGING_RANGE_MS[0] <= r["averaging_ms"]["value_ms"] <= PA.AVERAGING_RANGE_MS[1]
    assert TR.for_participant("nobody") == {}
    assert TR.for_participant(None) == {}


# --- the parameter card ------------------------------------------------------------------------
def _rows(**kw):
    p = PR.prescribe(mode=PA.DUAL, timing=PA.timing_plan(mode=PA.DUAL),
                     candidate={"channel": "ONE_THREE_LEFT", "center_hz": 24.5,
                                "band_width_hz": 5.0, "threshold_mode": "dual"}, **kw)
    return {r["parameter"]: r for r in p.as_rows()}, p


def test_the_card_carries_the_record_derived_values_with_their_confidence_and_the_programmed_values():
    rows, p = _rows(record_timing=TR.for_participant(RCS08),
                    programmed_timing=DF.programmed_closed_loop_timing(_group_d_channels())["Left"])
    assert rows["Upper onset duration"]["value"] == 30000.0
    assert rows["Upper onset duration"]["status"] == "derived"
    assert rows["Upper onset duration"]["confidence"] == "High"
    assert rows["Upper onset duration"]["range"] == PA.ONSET_RANGE_DUAL_MS
    assert "P960009/S478" in rows["Upper onset duration"]["range_source"]
    assert rows["Upper onset duration"]["programmed"] == 30000.0
    assert rows["Upper onset duration"]["confirm"] == "enterable"
    assert rows["Transition up duration"]["value"] == 30000.0
    assert rows["Transition up duration"]["programmed"] == 4000.0
    assert rows["Transition up duration"]["range"] == PA.TRANSITION_RANGE_MS
    assert rows["Transition up duration"]["confirm"] == "enterable"
    assert rows["Averaging duration"]["value"] == 30000.0
    assert rows["Averaging duration"]["range"] == PA.AVERAGING_RANGE_MS
    assert rows["Averaging duration"]["confirm"] == "enterable"
    assert rows["Adaptive startup delay"]["value"] == 15000.0
    assert rows["Adaptive startup delay"]["programmed"] == 0.0
    assert rows["Adaptive startup delay"]["confirm"] == "check_on_device"     # no documented range
    assert rows["Detection blanking duration"]["value"] == 30000.0
    assert rows["Detection blanking duration"]["confirm"] == "check_on_device"
    assert rows["Adaptive amplitude limit, upper"]["range"] == PA.ADAPTIVE_AMP_LIMIT_RANGE_MA
    assert rows["Adaptive amplitude limit, upper"]["programmed"] == 3.0
    assert rows["Upper LFP threshold"]["programmed"] == 167.0
    assert "uVrms" in rows["Upper LFP threshold"]["range_source"]
    assert rows["Upper LFP threshold"]["range"] is None                       # units differ: not applied
    assert len(p.unknowns) == 1 and "Startup Delay" in p.unknowns[0]
    assert "Detection Blanking" in p.unknowns[0]
    assert not any("Transition" in u for u in p.unknowns)


def test_without_a_measured_record_the_card_falls_back_to_the_window_and_the_defaults_unclamped():
    rows, p = _rows()
    # two windows of 4096 ms sit inside 0-6 min, so the onset is operative and not clamped to the
    # trial's 2 s (under which it was one window at every enterable value)
    assert rows["Upper onset duration"]["value"] == pytest.approx(2 * 4096.0)
    assert PR.onset_windows(rows["Upper onset duration"]["value"], rows["Averaging duration"]["value"])["windows"] == 2
    assert p.couplings == []
    assert "outside" not in rows["Upper onset duration"]["why"]
    assert rows["Upper onset duration"]["confidence"] is None
    assert rows["Upper onset duration"]["programmed"] is None
    assert rows["Transition up duration"]["value"] == 150_000.0
    assert rows["Transition up duration"]["status"] == "device_default"
    assert rows["Averaging duration"]["value"] == pytest.approx(4096.0)
    single = PR.prescribe(mode=PA.SINGLE, timing=PA.timing_plan(mode=PA.SINGLE),
                          candidate={"threshold_mode": "single"})
    srow = {r["parameter"]: r for r in single.as_rows()}["Onset duration"]
    assert srow["value"] == pytest.approx(2 * 4096.0) and srow["range"] == PA.ONSET_RANGE_SINGLE_MS


def test_the_onset_averaging_coupling_names_the_documented_ceiling_not_the_trials():
    rows, p = _rows(record_timing=TR.for_participant(RCS08))
    # 30 s onset against 30 s averaging is one controller step under the module's reading
    assert p.couplings and p.couplings[0]["fields"][0] == "Upper onset duration"
    assert "6 min" in p.couplings[0]["resolution"]
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
