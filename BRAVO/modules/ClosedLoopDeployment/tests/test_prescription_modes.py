"""The mode toggle's backend contract: every mode, two provenance axes, couplings, the gloss.

These exist because the PI asked for a toggle so a clinician can explore modes, and a toggle is only
honest if the alternative it offers is real. Each test below pins a property that, if it broke,
would make the toggle misleading rather than merely wrong.
"""
import math

import pytest

from ClosedLoopDeployment import prescription as PR, types as TY

PA = pytest.importorskip("StimOptimizer.routines.percept_adaptive")


def _plan():
    """RCS08's real threshold placement, so the numbers under test are the shipping ones."""
    return TY.ThresholdPlan(upper=0.3956, lower=0.182, capture_amp_low=1.4, capture_amp_high=4.8)


def _cand():
    return {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}


# --- the two provenance axes --------------------------------------------------------------------
def test_origin_and_confirm_are_independent_axes_not_a_relabelled_status():
    """The averaging duration is the case that PROVES the axes must be separate, and it is the
    reason a single `status` enum was not enough.

    That field is `derived` — this module computed it from the biomarker's own integration window —
    AND its adjustable range is unpublished, so nobody can promise the A610 will accept the value.
    Rendering it as merely "derived" would tell a clinician the number is trustworthy while
    withholding that the device may silently clamp it. So origin must say `participant` while
    confirm says `check_on_device`, and no single-axis encoding can express that.
    """
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=_plan(), candidate=_cand(),
                      timing=PA.timing_plan(mode=PA.DUAL))
    rows = {r["parameter"]: r for r in pr.as_rows()}

    avg = rows["Averaging duration"]
    assert avg["origin"] == "participant", "the module computed this from the integration window"
    assert avg["confirm"] == "check_on_device", "its adjustable range is unpublished (WP p. 14)"

    # and the two axes are genuinely non-redundant across the table: at least one field pairs a
    # participant origin with a non-enterable confirm, which a single enum could not encode.
    assert any(r["origin"] == "participant" and r["confirm"] != "enterable"
               for r in rows.values()), "if this fails the axes have collapsed into one"

    # every row carries both axes with values from the declared vocabularies
    for r in rows.values():
        assert r["origin"] in {"participant", "manufacturer", "clinician", "none"}, r
        assert r["confirm"] in {"enterable", "check_on_device", "must_choose",
                                "not_applicable"}, r


def test_the_required_safety_parameter_offers_no_value_and_says_the_clinician_must_choose():
    """D34's paused amplitude is deliberately null. Any number printed in a value column during a
    programming visit gets typed, so a suggestion here would be actively dangerous — the interface
    must render a blank field, and it can only know to do that from `confirm`.
    """
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=_plan(), candidate=_cand(),
                      timing=PA.timing_plan(mode=PA.DUAL))
    paused = next(r for r in pr.as_rows() if r["parameter"] == "Paused amplitude")
    assert paused["value"] is None, "a suggested value here would be transcribed"
    assert paused["confirm"] == "must_choose"
    assert paused["origin"] == "clinician"


# --- the transcription gloss --------------------------------------------------------------------
def test_long_millisecond_values_carry_the_minutes_and_seconds_the_programmer_displays():
    """The largest transcription hazard in the table. The transition durations leave this module as
    150000 and 300000 ms while the A610 displays and accepts minutes and seconds, so entering
    150000 where the device wants 2 min 30 s is a two-order-of-magnitude error rather than a near
    miss. The gloss is computed here rather than in JavaScript so both cannot disagree.
    """
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=_plan(), candidate=_cand(),
                      timing=PA.timing_plan(mode=PA.DUAL))
    rows = {r["parameter"]: r for r in pr.as_rows()}
    assert rows["Transition up duration"]["enter_as"] == "2 min 30 s"
    assert rows["Transition down duration"]["enter_as"] == "5 min 00 s"

    # short values must NOT be glossed: below ten seconds the programmer shows milliseconds and the
    # raw number is exactly what gets typed, so a gloss would add a second thing to read for no gain
    assert rows["Upper onset duration"]["enter_as"] is None
    assert rows["Averaging duration"]["enter_as"] is None
    # and a non-duration is never glossed however large
    assert rows["Upper LFP threshold"]["enter_as"] is None


def test_the_gloss_helper_boundary_and_non_numeric_inputs():
    assert PR._enter_as(9999.0, "ms") is None, "below ten seconds, no gloss"
    assert PR._enter_as(10000.0, "ms") == "0 min 10 s", "at ten seconds, glossed"
    assert PR._enter_as(1.4, "mA") is None, "wrong units"
    assert PR._enter_as("dual", "ms") is None, "non-numeric"
    assert PR._enter_as(True, "ms") is None, "a bool is not a duration"


# --- couplings ----------------------------------------------------------------------------------
def test_the_inoperative_onset_is_reported_as_a_field_PAIR_not_as_a_row_property():
    """The most consequential fact about this configuration is not a property of any single field:
    at the derived averaging duration the onset duration does nothing. A sixteen-row table renders
    each field as though its value could be judged alone, so this has to travel as a coupling
    between two named fields with both their values.
    """
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=_plan(), candidate=_cand(),
                      timing=PA.timing_plan(mode=PA.DUAL))
    assert len(pr.couplings) == 1, "expected exactly the onset/averaging coupling"
    c = pr.couplings[0]
    assert len(c["fields"]) == 2 and len(c["values"]) == 2, "a coupling names BOTH fields"
    assert "nset duration" in c["fields"][0] and c["fields"][1] == "Averaging duration"
    assert c["severity"] == "consequential"

    # the arithmetic in the prose must match the arithmetic in the code, or the banner lies
    onset, avg = float(c["values"][0]), float(c["values"][1])
    assert math.ceil(onset / avg) == 1, "the claim is that this is ONE controller step"
    ow = PR.onset_windows(onset, avg)
    assert ow["windows"] == 1 and ow["inoperative"] is True

    # honesty about what is NOT established must survive into the payload, because no supplied
    # document says whether the device counts onset in averaging windows or in FFT updates
    assert "FFT" in c["not_established"] or "fft" in c["not_established"]
    # and the resolution must not pretend this is a setting to fix
    assert "clinical trade" in c["resolution"] or "different feature" in c["resolution"]


@pytest.mark.parametrize("integration_s, expect_windows, expect_coupling", [
    # Measured from the shipping timing plan, so this table also documents WHERE the onset stops
    # working. The onset is operative while the averaging duration is short relative to it, and
    # becomes inoperative at an integration window of about two seconds — which is the regime the
    # validated biomarker actually needs, at 4.096 s.
    (0.25, 5, False),
    (0.5, 3, False),
    (1.0, 2, False),
    (2.0, 1, True),
    (4.096, 1, True),
])
def test_the_coupling_is_measured_from_the_chosen_pair_not_a_constant_warning(
        integration_s, expect_windows, expect_coupling):
    """The coupling must appear only when the two chosen values actually conflict, or the banner
    becomes a permanent decoration that a reader learns to ignore.

    Written as a ladder rather than as one case with a conditional assertion, because a test whose
    assertion depends on a branch can pass without ever reaching the interesting comparison. This
    version fails if the timing plan changes such that the onset never works, or always does.

    Note that Medtronic's own defaults pair a 1200 ms onset with 1200 ms averaging, which is itself
    exactly one window, so the averaging duration has to be made short relative to the onset before
    the coupling disappears at all.
    """
    pr = PR.prescribe(mode=PA.DUAL, threshold_plan=_plan(), candidate=_cand(),
                      timing=PA.timing_plan(mode=PA.DUAL, biomarker_integration_s=integration_s))
    rows = {r["parameter"]: r["value"] for r in pr.as_rows()}
    onset = float(rows["Upper onset duration"])
    avg = float(rows["Averaging duration"])

    assert math.ceil(onset / avg) == expect_windows, (
        f"onset {onset:.0f} ms against averaging {avg:.0f} ms")
    assert PR.onset_windows(onset, avg)["inoperative"] is expect_coupling
    assert bool(pr.couplings) is expect_coupling, (
        "the banner must track the measured conflict, not appear unconditionally")


def test_the_onset_cannot_be_rescued_within_the_published_range_at_the_validated_window():
    """The finding that makes the coupling a clinical trade rather than a setting to fix.

    At the averaging duration the validated biomarker requires, NO onset value a clinician can
    enter makes the onset operative, because the published dual-mode range has a ceiling. If a
    future device document widens that range this test should fail and be revisited, which is the
    point of pinning it.
    """
    avg_ms = 4096.0
    lo, hi = PA.ONSET_RANGE_DUAL_MS
    for onset in (lo, (lo + hi) / 2.0, hi):
        assert PR.onset_windows(onset, avg_ms)["windows"] == 1, (
            f"onset {onset} ms unexpectedly spans more than one {avg_ms} ms window")
        assert PR.onset_windows(onset, avg_ms)["inoperative"] is True

    # it is the CEILING that binds, not the arithmetic: an onset above the published range would
    # work, which is why this is a range limitation rather than a property of the control law
    assert PR.onset_windows(hi * 3.0, avg_ms)["inoperative"] is False


# --- every mode, and the field sets genuinely differing -----------------------------------------
def test_all_three_modes_are_returned_so_the_toggle_has_something_real_to_offer():
    """A module that returned only its own preference would make the clinician's choice
    unauditable: to see what Single Threshold requires they would have to take the module's word
    that it is worse.
    """
    A = PR.prescribe_all_modes(threshold_plan=_plan(), candidate=_cand())
    assert set(A["modes"]) == set(PA.MODES), "every mode the device offers must appear"
    assert A["recommended"] in PA.MODES
    assert A["recommendation"].get("recommended_because"), "advice without a reason is not advice"


def test_the_field_SETS_differ_between_modes_rather_than_only_the_numbers():
    """This is the property that makes the toggle worth having. Dual Threshold has two thresholds
    set by hand and two independently adjustable onsets; Single Threshold has one threshold the
    DEVICE computes (D20) and one onset. If both modes returned the same field names with different
    values, a clinician would reasonably conclude the mode only rescales things.
    """
    A = PR.prescribe_all_modes(threshold_plan=_plan(), candidate=_cand())
    dual = {r["parameter"] for r in A["modes"][PA.DUAL].as_rows()}
    single = {r["parameter"] for r in A["modes"][PA.SINGLE].as_rows()}

    assert {"Upper LFP threshold", "Lower LFP threshold"} <= dual
    assert not {"Upper LFP threshold", "Lower LFP threshold"} & single, \
        "Single Threshold does not take two hand-set thresholds"
    assert len([n for n in dual if "nset duration" in n]) == 2, "dual has upper AND lower onset"
    assert len([n for n in single if "nset duration" in n]) == 1, "single has one onset"
    assert dual != single


def test_the_sensing_only_mode_offers_no_prescription_and_explains_itself():
    """Single Threshold Inverse cannot drive therapy, so presenting any programmable field for it
    would imply a closed loop that cannot exist. An empty table with no explanation would read as a
    loading failure, so the reason has to be carried.
    """
    A = PR.prescribe_all_modes(threshold_plan=_plan(), candidate=_cand())
    inv = A["modes"][PA.SINGLE_INVERSE]
    assert inv.fields == [], "a mode that cannot actuate has nothing to program"
    assert inv.note, "an empty table without a reason looks like a bug"
    assert not PA.MODES[PA.SINGLE_INVERSE].can_drive_therapy


def test_each_mode_names_the_other_modes_exclusive_fields_instead_of_omitting_them():
    """Omitting them makes two modes look like one table with different numbers, which is exactly
    the misreading the toggle has to prevent. A named-but-struck-through row tells a clinician the
    field exists elsewhere and why it does not exist here.
    """
    A = PR.prescribe_all_modes(threshold_plan=_plan(), candidate=_cand())
    for m in (PA.DUAL, PA.SINGLE):
        na = A["modes"][m].not_applicable
        assert na, f"{m} should name the other mode's exclusive fields"
        present = {f.name for f in A["modes"][m].fields}
        for f in na:
            assert f.status == "not_applicable"
            assert f.confirm == "not_applicable" and f.origin == "none"
            assert f.why and len(f.why) > 40, "a struck-through row must say WHY it is absent"
            assert f.name not in present, "a field cannot be both present and not applicable"

    # the single mode must name the two hand-set thresholds it does not have, since that is the
    # difference a clinician most needs to understand before switching
    single_na = {f.name for f in A["modes"][PA.SINGLE].not_applicable}
    assert {"Upper LFP threshold", "Lower LFP threshold"} <= single_na


def test_one_mode_failing_does_not_lose_the_others():
    """The toggle must still work if one mode's prescription cannot be built, because a page with
    no table at all is a worse failure than a page with one mode unavailable.
    """
    A = PR.prescribe_all_modes(threshold_plan=None, candidate=None)
    assert set(A["modes"]) == set(PA.MODES)
    for pr in A["modes"].values():
        assert isinstance(pr, PR.Prescription)


# --- the longest continuous excursion at a limit (2026-09-05) -----------------------------------
def test_duty_reads_the_amplitude_trajectory_not_the_control_state():
    """Regression. `duty_cycle` read `replay_result.state` where it meant `amplitude_mA`.
    ReplayResult documents and populates `state` as the CONTROL STATE — a list of the strings
    "below", "between", "above" — so `np.asarray(state, float)` raised
    `ValueError: could not convert string to float: 'below'` and took down the whole prescription
    for any configuration whose replay returned a full trajectory.

    It went unnoticed because RCS08's record is fragmented enough to take the segment-aggregating
    path, which returns `state=None`; that skipped the block silently and left mean_amplitude_mA,
    amplitude_duty and both stim_frac fields null on every live payload instead of raising.
    """
    import numpy as np
    from ClosedLoopDeployment import replay as RP, prescription as PRx, types as TY
    p = np.concatenate([np.full(40, .05), np.full(120, .9), np.full(40, .05)])
    plan = TY.ThresholdPlan(upper=.5, lower=.2, capture_amp_low=1.0, capture_amp_high=3.0)
    r = RP.dual_threshold(p, plan=plan, params={"dt_s": 1.2})
    assert isinstance(r.state[0], str), "state is no longer strings; revisit this regression"
    d = PRx.duty_cycle(p, upper=.5, lower=.2, dt_s=1.2, replay_result=r)
    assert d.mean_amplitude_mA is not None and np.isfinite(d.mean_amplitude_mA)
    assert 1.0 - 1e-9 <= d.mean_amplitude_mA <= 3.0 + 1e-9, d.mean_amplitude_mA


def test_longest_excursion_is_a_duration_not_a_total_and_zero_is_not_none():
    """The number a clinician needs before consenting: 10% of a day at the upper limit is one long
    block or a hundred blips, and the fractions cannot tell them apart. `None` (no trajectory) and
    `0.0` (never reached the limit) are different answers and must not be collapsed."""
    import numpy as np
    from ClosedLoopDeployment import replay as RP, types as TY
    plan = TY.ThresholdPlan(upper=.5, lower=.2, capture_amp_low=1.0, capture_amp_high=3.0)

    # one long excursion, then a short one: the LONGEST is reported, not their sum
    p = np.concatenate([np.full(20, .05), np.full(200, .9), np.full(60, .05), np.full(40, .9)])
    r = RP.dual_threshold(p, plan=plan, params={"dt_s": 1.0})
    assert r.longest_run_at_upper_s is not None and r.longest_run_at_upper_s > 0

    # never reaches the upper limit -> 0.0, a real answer
    r0 = RP.dual_threshold(np.full(200, .05), plan=plan, params={"dt_s": 1.0})
    assert r0.longest_run_at_upper_s == 0.0
    assert r0.longest_run_at_lower_s is not None and r0.longest_run_at_lower_s > 0


def test_longest_run_helper_uses_a_declared_tolerance_rather_than_equality():
    """Exact equality would report zero time at the limit whenever the ramp arithmetic lands a
    fraction of a programmable step short. The tolerance is one A610 amplitude step."""
    import numpy as np
    from ClosedLoopDeployment import replay as RP
    assert RP.AT_LIMIT_TOL_MA == 0.05
    amp = np.array([1.0, 3.0 - 0.01, 3.0 - 0.01, 3.0 - 0.01, 1.0])   # a step short of the limit
    assert RP._longest_run_at_level_s(amp, 2.0, 3.0) == pytest.approx(6.0)
    assert RP._longest_run_at_level_s(amp, 2.0, 3.0, tol=0.0) == 0.0
    assert RP._longest_run_at_level_s(None, 2.0, 3.0) is None
    assert RP._longest_run_at_level_s(amp, 2.0, None) is None
