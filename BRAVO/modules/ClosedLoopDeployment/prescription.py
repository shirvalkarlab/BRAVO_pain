"""What to type into the programmer, and what fraction of the day the patient will spend where.

WHY THIS FILE EXISTS. Everything else in this module decides whether a configuration is ALLOWED.
None of it says what to program. A clinician standing at the A610 with a supported candidate still
has to choose two LFP thresholds, two onset durations, an averaging duration, a detection blanking
duration, two transition durations, an adaptive startup delay, two amplitude limits and a paused
amplitude — and the module previously supplied recommendations for three of those and echoed the
device default for the rest. This file assembles the whole set into one prescription, each field
carrying where its value came from, and adds the outcome metric a clinician actually asks for: what
percentage of the day the stimulation will sit high, low, or in between.

THE PARAMETER SET DEPENDS ON THE NUMBER OF THRESHOLDS. This is the single most important thing to
understand before reading further, and it is why this file is organised by mode rather than by
parameter. The white paper's parameter table (WP p. 14, Table 1; reproduced as D20) has one column
per mode, and the modes do not merely differ in the VALUE of a shared parameter — they differ in
which parameters exist at all and in how many copies.

Dual Threshold has TWO thresholds and therefore three control states, and the amplitude is HELD
CONSTANT while the power sits between them (WP p. 13). Both thresholds are set MANUALLY. Because
there are two distinct qualifying crossings — upward past the upper threshold and downward past the
lower one — there are TWO onset durations, and the manufacturer's own troubleshooting table names
them separately: for stimulation that is transiently too low it directs the clinician to "decrease
Upper Onset and increase Lower Onset" (A610 pp. 73-74, recorded as D51). They are independently
adjustable and this file treats them as two fields.

Single Threshold has ONE threshold and therefore two control states, and the amplitude ramps fully
between the two limits, giving the trapezoidal pattern Stanslaski et al. (2024) describe. The
threshold is NOT typed in: the device computes it as 0.75 x (Upper - Lower) + Lower from the
captured pair (D20 table, threshold-setting row). So a clinician in Single mode has a threshold they
cannot directly set, and one onset duration rather than two.

The timing values differ by more than a little between the modes, and the difference is not a matter
of taste. Dual: averaging 1200 ms, onset 1200 ms, blanking 2000 ms, transitions 2.5 and 5 minutes,
FFT updating at 5 Hz. Single: averaging 100 ms, onset 200 ms, blanking 550 ms, transitions 250 ms
each, FFT at 20 Hz. Single Threshold is built for a signal that changes within a second, which is
what a tremor burst does; Dual is built for one that drifts over minutes. That is a substantive
argument for Dual on a pain biomarker whose validated integration window is about four seconds, and
it is made in ``percept_adaptive.recommend_threshold_mode`` rather than here.

WHAT REMAINS GENUINELY UNKNOWN, and is reported as such rather than filled in. The adjustable RANGES
of Transition Up, Transition Down, Adaptive Startup Delay, Sensing Blanking Duration and Averaging
Duration are not printed in any supplied Medtronic document — only the defaults are (WP p. 14). The
onset ranges come from the ADAPT-PD methodology paper rather than the device labelling: 1.2-2 s in
dual mode and 200-500 ms in single mode (Stanslaski et al. 2024). Every field below says which of
those three situations it is in, because a recommendation that cannot be entered is worse than no
recommendation: it wastes a programming visit.

There is NO published resolution or step grid for these fields. An earlier reading of the parameter
table mistook its Single Threshold column for a step size, which would have meant quantising every
recommendation onto a grid; the table's four columns are Parameter, Dual, Single and Single Inverse,
so no such grid exists in the supplied documents and nothing here rounds to one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

try:                                                    # pragma: no cover - import shim
    from StimOptimizer.routines import percept_adaptive as PA
except Exception:                                       # pragma: no cover
    PA = None


#: Onset duration range in SINGLE threshold mode, from the ADAPT-PD methodology paper rather than
#: the device labelling (Stanslaski et al. 2024). Recorded here because the dual-mode range was
#: already encoded in percept_adaptive and its single-mode counterpart was not, which meant a
#: single-mode recommendation had nothing to be clamped against.
ONSET_RANGE_SINGLE_MS = (200.0, 500.0)

#: How many averaging windows an excursion must persist before this module will treat it as a real
#: state change when no measured latency is available. Declared by this module, not by Medtronic.
#: Two windows is the same settling convention percept_adaptive.timing_plan uses for blanking, and
#: the reason is the same: the device's averaging is non-overlapping (D14), so one window can be
#: half-contaminated by the previous state while two cannot.
ONSET_SETTLE_WINDOWS = 2.0

#: Fraction of the amplitude range within which the delivered amplitude counts as "at" a limit.
AT_LIMIT_FRAC = 0.05

#: Plausible bounds on the interval between band-power samples, used to refuse a degenerate time
#: base rather than divide by it. A Percept band-power series arrives no faster than the FFT update
#: rate and chronic snapshots are minutes apart, so anything outside these bounds is a unit error
#: in the caller rather than an unusual recording.
MIN_PLAUSIBLE_DT_S = 0.02
MAX_PLAUSIBLE_DT_S = 3600.0

#: Coverage at or above this fraction of the elapsed span is treated as continuous enough that the
#: state fractions may be read as fractions of time. Declared by this module. Set deliberately high
#: because the failure it guards against — reporting "half the day" when the truth is "half of four
#: hours of streaming spread over fourteen months" — overstates the result by orders of magnitude.
COVERAGE_IS_CONTINUOUS = 0.5


def onset_windows(onset_ms, averaging_ms):
    """How many controller steps an excursion must persist for, and whether that filters anything.

    THIS IS THE PARAMETER INTERACTION MOST LIKELY TO BE MISSED, and it silently removes a safety
    feature. The device's averaging is non-overlapping (D14), so the controller sees one averaged
    value per averaging duration and cannot resolve anything shorter. The onset duration therefore
    expresses itself as a whole number of averaging windows: ceil(onset / averaging). When that
    number is one, the onset is INOPERATIVE — the very first averaged sample past a threshold
    satisfies it, so the onset provides no protection at all against acting on a single noisy
    window, and whatever protection the configuration has must come from the threshold separation
    instead.

    That is not a hypothetical. The published onset range in dual mode is 1.2 to 2 s, so at any
    averaging duration of 2 s or more the onset is inoperative at EVERY value the clinician can
    choose. Matching the averaging duration to a biomarker validated on a 4096 ms window therefore
    costs the onset filter entirely, and that trade is worth stating rather than discovering later:
    the manufacturer's own defaults pair a 1200 ms onset with a 1200 ms averaging duration, which
    is exactly one window, and only an onset at the top of its range with averaging left at the
    1200 ms default gives two.

    WHAT IS NOT ESTABLISHED, and why this returns a caveat rather than a verdict. No supplied
    Medtronic document states whether the device counts the onset duration in averaging windows or
    in FFT updates, which arrive far more often (5 Hz in dual mode, so every 200 ms). If it counts
    FFT updates then a 2 s onset spans ten of them and does filter, even under a long averaging
    window. The reading used here — that the controller steps once per averaging window — is the
    one the defaults support, since the default onset and the default averaging duration are the
    same 1200 ms, which would be a strange coincidence otherwise. It is a reading, not a citation.
    """
    a = float(averaging_ms) / 1000.0
    if not (a > 0):
        raise ValueError(f"averaging duration must be positive, got {averaging_ms!r}")
    n = max(1, int(math.ceil(float(onset_ms) / 1000.0 / a)))
    inoperative = n <= 1
    return {
        "windows": n,
        "inoperative": inoperative,
        "why": (
            f"An onset of {float(onset_ms):.0f} ms against an averaging duration of "
            f"{float(averaging_ms):.0f} ms is {n} controller step(s)."
            + ("" if not inoperative else
               " That means the onset duration does NOTHING: the first averaged sample past a "
               "threshold already satisfies it, so the configuration has no protection against "
               "acting on one noisy window and must rely on the threshold separation instead. "
               "Shortening the averaging duration is the only way to make the onset operative, "
               "and it would deploy a different feature from the validated one."))}


@dataclass
class Field_:
    """One programmable field, with enough provenance that a clinician can audit it.

    ``status`` is the honest part and takes one of four values. ``derived`` means this module
    computed the value from the participant's own data or from the biomarker's integration window.
    ``device_default`` means the value is the manufacturer's default and nothing here improves on
    it. ``read_off_programmer`` means the field must be set by hand because its adjustable range is
    not published, so no recommendation can be guaranteed enterable. ``not_applicable`` means the
    field does not exist in the selected threshold mode, which is different from being unset.
    """

    name: str
    value: float | str | None
    units: str
    status: str
    default: float | str | None = None
    range_: tuple | None = None
    range_source: str | None = None
    why: str = ""

    #: WHY `status` ALONE IS NOT ENOUGH, and why two axes are derived from it below.
    #:
    #: `status` conflates two independent questions that a clinician standing at the programmer
    #: needs answered separately: where did this number come from, and can I actually enter it?
    #: The averaging duration is the case that proves they are independent — it is `derived`,
    #: because this module computed 4096 ms from the biomarker's own integration window, AND its
    #: adjustable range is unpublished, so nobody can promise the A610 will accept that value. One
    #: enum cannot say both, and rendering it as merely "derived" would tell a reader the number is
    #: trustworthy while withholding that it may be silently clamped.
    #:
    #: So the axes are separated. `origin` says where the value came from and takes
    #: `participant` / `manufacturer` / `clinician` / `none`. `confirm` says what must happen
    #: before it is trusted and takes `enterable` (a published range contains it) /
    #: `check_on_device` (no published range, so read the field's own limits first) /
    #: `must_choose` (no value is offered because the choice is clinical) / `not_applicable`.
    #:
    #: Derived from the existing fields rather than stored, so every existing call site keeps
    #: working and the two axes cannot drift out of step with `status`.

    @property
    def origin(self):
        if self.status == "not_applicable":
            return "none"
        if self.status == "device_default":
            return "manufacturer"
        if self.status == "read_off_programmer":
            return "clinician"
        if self.status == "device_computed":
            # Neither "participant" nor "manufacturer" is right here. The number is produced by the
            # DEVICE, applying a published formula to this participant's captured pair, and what a
            # clinician needs to know is that it appears on the programmer without being typed.
            return "device"
        return "participant"

    @property
    def confirm(self):
        if self.status == "not_applicable":
            return "not_applicable"
        if self.status == "device_computed":
            # The whole point of the new state: this value is CHECKED against the programmer, never
            # entered into it. Any confirm value that reads as an instruction to type would be
            # actively dangerous on this row.
            return "verify_only"
        if self.status == "read_off_programmer" and self.value is None:
            return "must_choose"
        # An unpublished range is the deciding fact regardless of where the value came from: it is
        # exactly the case the single `status` enum could not express.
        if self.range_source and "NOT published" in self.range_source:
            return "check_on_device"
        if self.status == "read_off_programmer":
            return "check_on_device"
        return "enterable"


@dataclass
class DutyCycle:
    """Where the patient's day is predicted to be spent.

    Two different quantities live here and conflating them is a real error, so they are named
    separately. The ``lfp_*`` fractions are time spent in each LFP CONTROL STATE, which is what the
    device's own Timeline reports as percentage of time above, between and below the thresholds
    (A610 p. 39, p. 56) — that is the observable a clinician compares this prediction against. The
    ``stim_*`` fractions are time spent at each end of the AMPLITUDE range, which is what the
    patient experiences. They differ because the amplitude ramps slowly: in Dual mode a brief
    excursion above the upper threshold moves the amplitude a little way up and then stops, so time
    above threshold is not time at the upper limit.
    """

    lfp_frac_above: float | None = None
    lfp_frac_between: float | None = None
    lfp_frac_below: float | None = None
    stim_frac_at_upper: float | None = None
    stim_frac_at_lower: float | None = None
    stim_frac_mid: float | None = None
    mean_amplitude_mA: float | None = None
    #: 0 means the amplitude sat at the lower limit throughout, 1 at the upper limit throughout.
    #: This is the single number closest to what is usually meant by "percentage of time on", and
    #: it is a fraction of the AMPLITUDE RANGE rather than a fraction of time, which is why it is
    #: named separately from the fractions above.
    amplitude_duty: float | None = None
    transitions_per_hour: float | None = None
    qualified_transitions: int | None = None
    unqualified_excursions: int | None = None
    hours_observed: float | None = None
    #: Hours of actual SIGNAL in the record, which is the sample count times the averaging
    #: duration, and the fraction of the elapsed span that represents.
    hours_of_signal: float | None = None
    coverage_frac: float | None = None
    #: True when the state fractions above are fractions of the OBSERVED SAMPLES rather than of
    #: elapsed time. This is the single most misreadable number the module produces, so it carries
    #: its own flag rather than relying on a caveat being read: a chronic Percept record is sampled
    #: in short bursts minutes apart, so "half the samples were above the upper threshold" is not
    #: "half the day was spent above the upper threshold", and on this participant the two differ
    #: by a factor of about two thousand. Any interface that prints a percentage of the day must
    #: refuse to do so when this is True.
    fractions_are_of_observed_samples: bool | None = None
    predicted_failure_mode: str | None = None
    #: How many controller steps an excursion must persist for, per direction, and whether the
    #: onset duration filters anything at all at the chosen averaging duration. See onset_windows.
    onset_windows_upper: int | None = None
    onset_windows_lower: int | None = None
    onset_inoperative: bool | None = None
    caveats: list = field(default_factory=list)


@dataclass
class Prescription:
    mode: str
    fields: list = field(default_factory=list)
    duty: DutyCycle | None = None
    unknowns: list = field(default_factory=list)
    #: Conflicts between PAIRS of fields, which a table of independent rows cannot express.
    #:
    #: A sixteen-row table renders each field as though its value could be judged on its own, and
    #: the most consequential finding about this configuration is not a property of any single row:
    #: at the derived averaging duration the onset duration is inoperative, and that is a fact
    #: about the two fields together. Putting the warning in the onset row's ``why`` text was tried
    #: and is not enough, because a reader scanning a column of values does not read sixteen
    #: paragraphs of justification, and the conflict belongs to neither row alone.
    #:
    #: Each entry carries the two field names, their values, the plain-English consequence and a
    #: severity, so an interface can render the pair rather than assert a conclusion.
    couplings: list = field(default_factory=list)
    #: Fields that do NOT exist in the selected mode, kept rather than omitted so a reader can see
    #: that the other mode has them. Omitting them makes two modes look like the same table with
    #: different numbers, which is exactly the misreading the mode toggle has to prevent.
    not_applicable: list = field(default_factory=list)
    note: str = ""

    def as_rows(self):
        return [{"parameter": f.name, "value": f.value, "units": f.units, "status": f.status,
                 "device_default": f.default, "range": f.range_, "range_source": f.range_source,
                 "why": f.why,
                 # The two provenance axes, so the interface never has to re-derive them from the
                 # status string and cannot disagree with this module about what a status means.
                 "origin": f.origin, "confirm": f.confirm,
                 # The minutes-and-seconds gloss, computed HERE rather than in JavaScript. The two
                 # transition durations come out of this module as 150000 and 300000 ms while the
                 # A610 displays and accepts minutes and seconds, which is the largest transcription
                 # hazard in the table: entering 150000 where the device wants 2 min 30 s is not a
                 # near miss. Anything at or above ten seconds gets the gloss.
                 "enter_as": _enter_as(f.value, f.units)} for f in self.fields]


def _enter_as(value, units):
    """How the A610 displays a millisecond value, for values long enough that it matters.

    Returns None when no gloss is needed. The threshold is ten seconds: below that the programmer
    shows milliseconds and the raw number is what gets typed, at or above it the programmer shows
    minutes and seconds. The two transition durations are 150000 and 300000 ms, and typing those
    digits into a field expecting 2 min 30 s is a two-order-of-magnitude error rather than a
    near miss, so the gloss is part of the data rather than a presentation flourish.
    """
    if units != "ms" or not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    total = float(value) / 1000.0
    if total < 10.0:
        return None
    m, sec = int(total // 60), total - 60 * int(total // 60)
    return f"{m} min {sec:04.1f} s".replace(".0 s", " s")


def _clamp(x, lo, hi):
    return min(max(float(x), float(lo)), float(hi))


def _qualified_states(power, upper, lower, n_up, n_dn):
    """Walk an averaged power series and assign a control state to every window.

    An excursion past a threshold only changes the state once it has persisted for the onset
    duration, which is what the onset duration is FOR: it stops the controller chasing single
    noisy windows. Counting the states without it would overstate how much of the day is spent
    calling for a change, and it is the reason a shorter Upper Onset makes stimulation rise more
    readily while a longer Lower Onset makes it fall less readily — the asymmetry the
    manufacturer's troubleshooting table exploits.

    Returns the per-window state array, the number of state changes that qualified, and the number
    of excursions that touched a threshold but did not persist long enough to count.
    """
    p = np.asarray(power, float)
    state = np.zeros(p.size, dtype=np.int8)          # -1 below, 0 between, +1 above
    cur = 0
    run_val, run_len = 0, 0
    qualified, unqualified = 0, 0
    for i, v in enumerate(p):
        inst = 1 if v > upper else (-1 if v < lower else 0)
        if inst == run_val:
            run_len += 1
        else:
            # a run that ended without qualifying, and that was not merely a return to `between`
            if run_val != 0 and run_val != cur and run_len > 0:
                unqualified += 1
            run_val, run_len = inst, 1
        need = 1 if inst == 0 else (n_up if inst > 0 else n_dn)
        if inst != cur and run_len >= need:
            cur = inst
            qualified += 1
            run_len = 0
            run_val = inst
        state[i] = cur
    return state, qualified, unqualified


def _failure_mode(lfp_above, lfp_below, at_upper, at_lower):
    """Name the device's own predicted adaptive failure state, or say the prediction is benign.

    D51 records that the A610 troubleshooting table enumerates four adaptive failure states and
    that the Timeline's percentage of time above, between and below the thresholds is the
    observable that discriminates them. Predicting which one a configuration will land in before
    it is programmed is more useful than a generic warning, because each state has a different
    remedy and two of the remedies move parameters in opposite directions.
    """
    if at_upper is not None and at_upper > 0.8:
        return ("stimulation chronically too high: predicted to sit at the upper amplitude limit "
                "more than 80% of the time. D51 remedy: lower the maximum amplitude limit if the "
                "Timeline confirms it, otherwise raise the upper LFP threshold, then the lower, "
                "then lower the maximum amplitude limit.")
    if at_lower is not None and at_lower > 0.8:
        return ("stimulation chronically too low: predicted to sit at the lower amplitude limit "
                "more than 80% of the time. D51 remedy: raise the maximum amplitude limit if the "
                "Timeline shows it stuck there, otherwise lower the upper LFP threshold, then the "
                "lower LFP threshold, then raise the minimum amplitude limit.")
    if lfp_above is not None and lfp_above > 0.45 and lfp_below is not None and lfp_below > 0.45:
        return ("stimulation transiently unstable: the power is predicted to spend most of the day "
                "outside the thresholds in both directions with little time held between them, so "
                "the amplitude will chase it. D51 remedy: widen the threshold separation, or "
                "lengthen Transition Down and shorten Transition Up.")
    return None


def prescribe_all_modes(**kw):
    """Every threshold mode's prescription in one call, plus the mode this module recommends.

    WHY ALL THREE RATHER THAN THE RECOMMENDED ONE. The clinician is the person choosing the mode,
    and a module that returns only its own preference makes that choice unauditable: to see what
    Single Threshold would require, the clinician would have to take the module's word that it is
    worse. Returning all three lets the interface offer a toggle and lets the reader compare the
    field sets side by side, which is the honest shape for a recommendation — it says what this
    module would do and shows the alternative it declined.

    The recommendation itself is not made here. It comes from
    ``percept_adaptive.recommend_threshold_mode``, which derives it from the biomarker's timescale
    rather than hardcoding it, so a demonstrated fast biomarker would change the answer.

    Returns ``{"recommended": <mode>, "recommendation": {...}, "modes": {<mode>: Prescription}}``.
    A mode that cannot drive therapy still appears, carrying an empty field list and the reason,
    because "this mode exists and is useless for closed loop" is information a clinician exploring
    the toggle needs.
    """
    if PA is None:                                       # pragma: no cover
        raise RuntimeError("percept_adaptive is required for the device parameter table")
    kw.pop("mode", None)
    rec = PA.recommend_threshold_mode(
        biomarker_timescale_s=kw.pop("biomarker_timescale_s", None),
        validated_hemispheres=kw.pop("validated_hemispheres", ()),
        configuring_both_hemispheres=kw.pop("configuring_both_hemispheres", False))
    out = {}
    for m in PA.MODES:
        try:
            out[m] = prescribe(mode=m, timing=PA.timing_plan(mode=m), **kw)
        except Exception as ex:                          # one mode failing must not lose the rest
            out[m] = Prescription(mode=m, fields=[],
                                  note=f"this mode's prescription could not be built: {ex}")
    return {"recommended": rec.get("mode"), "recommendation": rec, "modes": out}


def prescribe(*, mode, threshold_plan=None, candidate=None, timing=None, power_series=None,
              t_s=None, dt_s=None, replay_result=None, measured_latency_s=None):
    """Assemble the full programmable prescription for one candidate, in one threshold mode.

    ``mode`` decides which fields exist; see the module docstring. ``threshold_plan`` supplies the
    captured thresholds and amplitudes. ``timing`` is the dict from
    ``percept_adaptive.timing_plan``. ``power_series`` is the observed band power used for the duty
    cycle, on the same scale as the thresholds.
    """
    if PA is None:                                       # pragma: no cover
        raise RuntimeError("percept_adaptive is required for the device parameter table")
    if mode not in PA.MODES:
        raise ValueError(f"unknown threshold mode {mode!r}; expected one of {sorted(PA.MODES)}")
    spec = PA.MODES[mode]
    if not spec.can_drive_therapy:
        return Prescription(
            mode=mode, fields=[], unknowns=[],
            note=(f"{mode} is a Sensing Only configuration and cannot drive therapy (D18), so "
                  f"there is no closed-loop prescription to write. Nothing below would be "
                  f"programmable and the field list is deliberately empty rather than filled with "
                  f"values that cannot be entered."))

    is_dual = (mode == PA.DUAL)
    T = timing or {}
    cand = candidate or {}
    F, unknowns = [], []

    # --- sensing ---------------------------------------------------------------------------------
    F.append(Field_("Sensing channel", cand.get("channel"), "contacts", "derived",
                    why="Chosen by the biomarker screen. Changing it destroys the captured "
                        "thresholds and requires recapture (D29)."))
    F.append(Field_("Centre frequency", cand.get("center_hz"), "Hz", "derived",
                    range_=PA.ADAPTIVE_LFP_BAND_HZ, range_source="A610, adaptive band",
                    why="The validated band centre. Must lie inside the adaptive sensing band."))
    F.append(Field_("Band width", cand.get("band_width_hz"), "Hz", "derived",
                    why="The width the band was validated at; changing it changes the feature."))
    F.append(Field_("Threshold mode", mode, "", "derived",
                    default=PA.DUAL,
                    why="Recommended from the biomarker's own timescale, not hardcoded; see "
                        "percept_adaptive.recommend_threshold_mode."))

    # --- thresholds: the field set differs by mode -----------------------------------------------
    tp = threshold_plan
    up = getattr(tp, "upper", None)
    lo = getattr(tp, "lower", None)
    if is_dual:
        F.append(Field_("Upper LFP threshold", up, "LFP power", "derived",
                        why="Placed at the capture mean measured at the LOWER amplitude. The "
                            "naming is crossed on purpose (D24). Set manually in Dual mode."))
        F.append(Field_("Lower LFP threshold", lo, "LFP power", "derived",
                        why="Placed at the capture mean measured at the UPPER amplitude (D24)."))
    else:
        single = None
        if up is not None and lo is not None:
            single = 0.75 * (float(up) - float(lo)) + float(lo)
        # STATUS `device_computed`, NOT `derived`, and the distinction is a safety one.
        #
        # Under `derived` this row came out with confirm "enterable", while its own justification
        # text said the opposite: the value is NOT typed in, because the device computes it as
        # 0.75 x (Upper - Lower) + Lower from the captured pair (D20). The interface consumes the
        # `confirm` axis, not the prose, so the one field in the table where the error runs toward
        # entering a number that must not be entered was the field labelled enterable. The
        # front-end had to detect this row by matching its `why` text, which is a fragile stopgap
        # its author flagged for replacement — this is that replacement.
        F.append(Field_("Single LFP threshold", single, "LFP power", "device_computed",
                        why="NOT typed in. The device computes it as 0.75 x (Upper - Lower) + "
                            "Lower from the captured pair (D20), so it is shown here for the "
                            "clinician to verify against the device rather than to enter."))

    # --- onset durations: TWO in dual, ONE in single ---------------------------------------------
    rng = PA.ONSET_RANGE_DUAL_MS if is_dual else ONSET_RANGE_SINGLE_MS
    src = ("ADAPT-PD methodology paper (Stanslaski et al. 2024), not the device labelling; "
           "the labelling prints only the default")
    # The principled starting point is the biomarker's own integration window, clamped into the
    # published range. A band averaged over about four seconds cannot meaningfully confirm a state
    # change faster than one averaging window, and the range's upper end is well below that, so in
    # dual mode this clamps to the top of the range rather than landing inside it — which is itself
    # worth seeing, and is stated in `why` rather than hidden by the clamp.
    ideal_ms = 1000.0 * float(T.get("biomarker_averaging_window_s") or 0) or None
    onset_ms = _clamp(ideal_ms, *rng) if ideal_ms else spec.onset_duration_ms
    clamped = ideal_ms is not None and not (rng[0] <= ideal_ms <= rng[1])
    tail = ("" if not clamped else
            f" The biomarker's own integration window is {ideal_ms:.0f} ms, which is outside the "
            f"published range, so this is clamped to the range end rather than to the window. A "
            f"state change therefore cannot be confirmed within one averaging window, and brief "
            f"excursions will be acted on sooner than the biomarker can resolve them.")
    if is_dual:
        F.append(Field_("Upper onset duration", onset_ms, "ms", "derived",
                        default=spec.onset_duration_ms, range_=rng, range_source=src,
                        why="How long the power must stay ABOVE the upper threshold before the "
                            "amplitude starts to rise. Separately adjustable from the lower onset; "
                            "the manufacturer's troubleshooting table directs the clinician to "
                            "decrease this one while increasing the other when stimulation is "
                            "transiently too low (D51)." + tail))
        F.append(Field_("Lower onset duration", onset_ms, "ms", "derived",
                        default=spec.onset_duration_ms, range_=rng, range_source=src,
                        why="How long the power must stay BELOW the lower threshold before the "
                            "amplitude starts to fall. Started symmetric with the upper onset "
                            "because nothing in this participant's data argues for an asymmetry "
                            "yet; asymmetry is the first lever to reach for if the delivered "
                            "amplitude turns out transiently too low or too high (D51)." + tail))
    else:
        F.append(Field_("Onset duration", onset_ms, "ms", "derived",
                        default=spec.onset_duration_ms, range_=rng, range_source=src,
                        why="Single Threshold has one threshold and so one onset duration. Its "
                            "range is 200-500 ms, an order of magnitude shorter than dual mode's, "
                            "because the mode is built for a signal that changes within a second."
                            + tail))

    # --- averaging, blanking -----------------------------------------------------------------
    avg = T.get("recommended_device_averaging_ms") or spec.averaging_duration_ms
    F.append(Field_("Averaging duration", avg, "ms",
                    "derived" if T.get("recommended_device_averaging_ms") else "device_default",
                    default=spec.averaging_duration_ms, range_=None,
                    range_source="range NOT published; only the default is (WP p. 14)",
                    why="Matched to the window the biomarker was validated on, because the device "
                        "averaging duration IS the feature definition: deploying the default "
                        f"({spec.averaging_duration_ms:.0f} ms) deploys a different feature from "
                        "the validated one. Whether the device reaches this value must be checked "
                        "on the Advanced Settings screen, since the range is unpublished."))
    F.append(Field_("Detection blanking duration", spec.detection_blanking_ms, "ms",
                    "device_default", default=spec.detection_blanking_ms,
                    range_source="range NOT published (WP p. 14)",
                    why="Left at the default. D51 uses it as the remedy for repeated ramping to "
                        "the upper limit straight after reaching the lower one, so it is a "
                        "reactive lever rather than something to preset."))

    # --- transitions ----------------------------------------------------------------------------
    for nm, dflt, direction in (("Transition up duration", spec.transition_up_ms, "rise"),
                                ("Transition down duration", spec.transition_down_ms, "fall")):
        F.append(Field_(nm, dflt, "ms", "device_default", default=dflt,
                        range_source="range NOT published (WP p. 14); read off Advanced Settings",
                        why=f"How long the amplitude takes to {direction} across the full limit "
                            f"range. Left at the device default because the range is unpublished "
                            f"and no measurement in this participant's record constrains it. In "
                            f"Dual mode the adjustment is incremental rather than a full ramp "
                            f"between the limits (D22), so this sets a RATE, not a dwell time."))
    unknowns.append("Transition Up and Transition Down adjustable ranges (WP p. 14 prints only "
                    "the defaults) — read off the Advanced Settings screen")

    # --- adaptive startup delay -----------------------------------------------------------------
    # Derived rather than defaulted, because the document gives a mechanism even though it gives no
    # range: a transient jump to the upper limit immediately after resuming is fixed by increasing
    # this delay (D51). The principled floor is therefore the time the band needs to settle before
    # its value means anything, which is exactly the blanking floor timing_plan already computes
    # from the ramp and the averaging window.
    settle_s = T.get("blank_after_step_s")
    startup_ms = float(settle_s) * 1000.0 if settle_s else None
    F.append(Field_("Adaptive startup delay", startup_ms, "ms",
                    "derived" if startup_ms else "read_off_programmer",
                    range_source="range NOT published (WP p. 14); read off Advanced Settings",
                    why="Set to the same settling time used to blank the ramp transient, which is "
                        "the ramp duration plus two averaging windows. The reasoning is the "
                        "device's own: D51 fixes a transient jump to the upper limit immediately "
                        "after resuming by increasing this delay, and the jump happens because the "
                        "controller acts on a band value measured before the signal has settled. "
                        "Whether the device accepts this value is unverified, because the range is "
                        "not published."))
    unknowns.append("Adaptive Startup Delay adjustable range — read off the Advanced Settings "
                    "screen; the recommendation above is derived, not confirmed enterable")

    # --- amplitude limits -----------------------------------------------------------------------
    a_lo = getattr(tp, "capture_amp_low", None)
    a_hi = getattr(tp, "capture_amp_high", None)
    F.append(Field_("Adaptive amplitude limit, lower", a_lo, "mA", "derived",
                    why="Inherits the lower capture amplitude (D28), which makes the choice of "
                        "capture amplitudes a therapeutic decision and not only a measurement "
                        "one. Must be above zero (D07)."))
    F.append(Field_("Adaptive amplitude limit, upper", a_hi, "mA", "derived",
                    why="Inherits the upper capture amplitude (D28)."))
    F.append(Field_("Paused amplitude", cand.get("paused_amplitude_mA"), "mA",
                    "derived" if cand.get("paused_amplitude_mA") else "read_off_programmer",
                    why="The amplitude delivered when the patient pauses Adaptive (D34). Not "
                        "derivable from the record; a clinical choice."))

    # --- duty cycle ------------------------------------------------------------------------------
    duty = None
    if power_series is not None and up is not None and lo is not None:
        duty = duty_cycle(power_series, upper=float(up), lower=float(lo), t_s=t_s, dt_s=dt_s,
                          averaging_ms=float(avg), upper_onset_ms=float(onset_ms),
                          lower_onset_ms=float(onset_ms), is_dual=is_dual,
                          replay_result=replay_result)

    # --- field-pair couplings ------------------------------------------------------------------
    couplings = []
    _avg = next((f for f in F if f.name == "Averaging duration"), None)
    _ons = [f for f in F if "nset duration" in f.name]
    if _avg is not None and _ons:
        _ow = onset_windows(_ons[0].value, _avg.value)
        if _ow["inoperative"]:
            couplings.append({
                "fields": [_ons[0].name, _avg.name],
                "values": [_ons[0].value, _avg.value],
                "units": ["ms", "ms"],
                "severity": "consequential",
                "consequence": (
                    f"The onset duration does nothing at this averaging duration. Averaging is "
                    f"non-overlapping (D14), so the controller sees one averaged value per "
                    f"averaging duration and an onset of {float(_ons[0].value):.0f} ms against "
                    f"{float(_avg.value):.0f} ms is ceil({float(_ons[0].value):.0f}/"
                    f"{float(_avg.value):.0f}) = 1 controller step. At one step the first averaged "
                    f"sample past a threshold already satisfies the onset, so there is no "
                    f"persistence requirement at all and the configuration's only protection "
                    f"against acting on one noisy window is the separation between the two "
                    f"thresholds."),
                "resolution": (
                    "The published onset range tops out at 2000 ms, so no value a clinician can "
                    "enter makes the onset operative at an averaging duration of 2 s or more. "
                    "Shortening the averaging duration would restore it, but the averaging "
                    "duration is the feature definition: 4096 ms is the window every validated "
                    "band was computed on, and changing it deploys a different feature from the "
                    "validated one. This is a clinical trade rather than a setting to fix."),
                "not_established": (
                    "No supplied Medtronic document states whether the device counts the onset "
                    "duration in averaging windows or in FFT updates, which arrive far more often "
                    "(5 Hz in Dual Threshold). If it counts FFT updates then a 2000 ms onset spans "
                    "ten of them and does filter. The reading used here is the one the defaults "
                    "support, since the default onset and the default averaging duration are both "
                    "1200 ms, which would otherwise be a strange coincidence. It is a reading, not "
                    "a citation."),
            })

    # --- fields the OTHER mode has and this one does not ---------------------------------------
    _names = {f.name for f in F}
    na = []
    if is_dual:
        na = [Field_(name="Single LFP threshold", value=None, units="LSB", status="not_applicable",
                     why=("Dual Threshold has two thresholds, both set by hand. The single "
                          "threshold does not exist here, and in Single Threshold it is not typed "
                          "in at all — the device computes it as 0.75 x (Upper - Lower) + Lower "
                          "from the captured pair (D20).")),
              Field_(name="Onset duration (single)", value=None, units="ms",
                     status="not_applicable",
                     why=("Dual Threshold has TWO onset durations, an upper and a lower, listed "
                          "above and independently adjustable. That asymmetry is the first lever "
                          "the manufacturer's troubleshooting table reaches for (D51), so "
                          "collapsing them into one would remove a control rather than simplify "
                          "the table."))]
    elif mode == PA.SINGLE:
        na = [Field_(name="Upper LFP threshold", value=None, units="LSB", status="not_applicable",
                     why=("Single Threshold has one threshold and the device computes it from the "
                          "captured amplitudes (D20); there is no upper threshold to enter.")),
              Field_(name="Lower LFP threshold", value=None, units="LSB", status="not_applicable",
                     why="Same as the upper threshold: not a field in this mode."),
              Field_(name="Upper onset duration", value=None, units="ms", status="not_applicable",
                     why=("Single Threshold has ONE onset duration, listed above. The upper and "
                          "lower onsets are a Dual Threshold feature.")),
              Field_(name="Lower onset duration", value=None, units="ms", status="not_applicable",
                     why="Same as the upper onset: not a field in this mode.")]
    na = [f for f in na if f.name not in _names]

    return Prescription(
        mode=mode, fields=F, duty=duty, unknowns=unknowns,
        couplings=couplings, not_applicable=na,
        note=("Every field carries its status: derived from this participant's data, left at the "
              "manufacturer's default, or flagged as needing to be read off the programmer because "
              "its adjustable range is unpublished. No field is silently defaulted. There is no "
              "published resolution grid for these values, so nothing here is rounded to one."))


def duty_cycle(power_series, *, upper, lower, t_s=None, dt_s=None, averaging_ms=1200.0,
               upper_onset_ms=1200.0, lower_onset_ms=1200.0, is_dual=True,
               replay_result=None):
    """Predict where the day is spent, with the onset durations actually applied.

    THE CAVEAT THAT TRAVELS WITH EVERY NUMBER THIS RETURNS, and it is not a formality. The power
    series available here was recorded while the amplitude followed the participant's actual
    programming, not while the controller was driving it. Using it to predict time-in-state assumes
    the same power would have occurred under closed-loop control, and that assumption is false
    exactly when the band responds to amplitude — which is the whole reason for deploying the band.
    So these fractions describe what the control law would have done to THIS input. They are a
    screening quantity for choosing between configurations, not a forecast of the Timeline.
    """
    p = np.asarray(getattr(power_series, "values", power_series), float).ravel()
    p = p[np.isfinite(p)]
    d = DutyCycle(caveats=[
        "Computed on band power recorded under the participant's ACTUAL programming, not under "
        "closed-loop control. It assumes the same power would occur once the loop is closed, which "
        "is false precisely when the band responds to amplitude. Treat as a way of comparing "
        "configurations, not as a prediction of the device Timeline."])
    if p.size < 3:
        d.caveats.append(f"only {p.size} finite samples; no duty cycle computed")
        return d

    # THE SAMPLE INTERVAL IS VALIDATED RATHER THAN TRUSTED. A degenerate interval produced a
    # transitions-per-hour figure of 3.4 billion in testing, against an observed span that rounded
    # to zero hours, because the caller had converted epoch SECONDS as though they were nanoseconds
    # and put fourteen months of recording inside one second of 1970. A rate computed against a
    # near-zero denominator is not a large rate, it is a broken one, so an implausible interval now
    # suppresses the per-hour figures and says so instead of publishing a number.
    # THE TIME BASE IS DERIVED AND VALIDATED, NEVER TRUSTED. Passing an interval alone is not
    # enough on a chronic record, for two independent reasons that both produced wrong numbers in
    # testing.
    #
    # The first is a unit error the caller cannot be relied on to avoid. A degenerate interval
    # produced a transitions-per-hour figure of 3.4 billion against an observed span that rounded
    # to zero hours, because fourteen months of epoch SECONDS had been converted as though they
    # were epoch nanoseconds, compressing the whole record into one second of 1970. A rate computed
    # against a near-zero denominator is not a large rate, it is a broken one.
    #
    # The second is structural. Elapsed time is the SPAN of the recording, not the sample count
    # multiplied by the interval, and those agree only when the series has no gaps. A chronic
    # Percept record is mostly gaps: the two figures here differ by orders of magnitude, so using
    # the count would understate the elapsed time and inflate every per-hour figure by the same
    # factor. The span therefore comes from the time base itself when one is supplied.
    span_s, dt = None, (float(dt_s) if dt_s else None)
    if t_s is not None:
        t = np.asarray(getattr(t_s, "values", t_s), float).ravel()
        t = t[np.isfinite(t)]
        if t.size >= 2:
            u = np.unique(t)                      # duplicated timestamps are collapsed, not summed
            span_s = float(u[-1] - u[0])
            gaps = np.diff(u)
            gaps = gaps[gaps > 0]
            if gaps.size:
                dt = float(np.median(gaps))
            if u.size < t.size:
                d.caveats.append(
                    f"{t.size - u.size} of {t.size} samples share a timestamp with another sample; "
                    f"the interval was measured between DISTINCT timestamps so that duplicates do "
                    f"not collapse it toward zero")
    if dt is not None and not (MIN_PLAUSIBLE_DT_S <= dt <= MAX_PLAUSIBLE_DT_S):
        d.caveats.append(
            f"the sample interval of {dt:.6g} s is outside the plausible range "
            f"{MIN_PLAUSIBLE_DT_S}-{MAX_PLAUSIBLE_DT_S} s for a band-power series, so it was "
            f"REFUSED and every per-hour figure is omitted. The usual cause is a time column in "
            f"epoch seconds converted as though it were epoch nanoseconds.")
        dt, span_s = None, None
    avg_s = float(averaging_ms) / 1000.0
    if dt and dt > 0:
        n_per = max(1, int(math.floor(avg_s / dt + 1e-9)))
        n_win = p.size // n_per
        if n_win >= 3 and n_per > 1:
            p = p[:n_win * n_per].reshape(n_win, n_per).mean(axis=1)
        elif n_per > 1:
            d.caveats.append(
                f"the series supports only {n_win} averaging windows of {avg_s:.3g} s, so the "
                f"power was NOT re-averaged onto the device grid and each sample is treated as "
                f"one controller step")
        else:
            d.caveats.append(
                f"the samples arrive every {dt:.3g} s, which is LONGER than the {avg_s:.3g} s "
                f"averaging duration, so each sample already represents at least one controller "
                f"step and no re-averaging was applied. The state fractions below are therefore "
                f"fractions of the SAMPLES on record rather than of continuous time, and because "
                f"a chronic record is sampled in bursts they are not a fraction of the day.")
        if span_s:
            d.hours_observed = float(span_s) / 3600.0
        # Coverage: how much of the elapsed span the record actually observed. Each retained sample
        # stands for one averaging window of signal, so the signal time is the sample count times
        # the window. When coverage is low the state fractions are fractions of the samples on
        # record and not of the day, and saying so is the difference between a useful number and a
        # misleading one.
        d.hours_of_signal = float(p.size) * avg_s / 3600.0
        if d.hours_observed and d.hours_observed > 0:
            d.coverage_frac = float(d.hours_of_signal / d.hours_observed)
            d.fractions_are_of_observed_samples = bool(d.coverage_frac < COVERAGE_IS_CONTINUOUS)
            if d.fractions_are_of_observed_samples:
                d.caveats.append(
                    f"COVERAGE {100 * d.coverage_frac:.3g}%. The record contains "
                    f"{d.hours_of_signal:.1f} hours of signal spread across "
                    f"{d.hours_observed:.0f} hours of elapsed time, so the state fractions below "
                    f"are fractions of the SAMPLES ON RECORD and must not be reported as "
                    f"percentages of the day — the two differ here by a factor of about "
                    f"{1 / max(d.coverage_frac, 1e-12):.0f}. A chronic Percept record is sampled "
                    f"in short bursts minutes apart, and the bursts are not a random sample of "
                    f"the day either, since streaming happens when the participant or the clinic "
                    f"initiates it.")
    else:
        d.caveats.append("no usable sample interval, so each sample is treated as one controller "
                         "step and the per-hour figures are omitted")

    ow_up = onset_windows(upper_onset_ms, averaging_ms)
    ow_dn = onset_windows(lower_onset_ms, averaging_ms)
    n_up, n_dn = ow_up["windows"], ow_dn["windows"]
    d.onset_windows_upper = n_up
    d.onset_windows_lower = n_dn
    d.onset_inoperative = bool(ow_up["inoperative"] or ow_dn["inoperative"])
    if d.onset_inoperative:
        d.caveats.append("ONSET DURATION INOPERATIVE. " + ow_up["why"])
    if not is_dual:
        # One threshold and two states: the device computes the single threshold from the pair, so
        # the state boundary is that computed value rather than either captured threshold.
        thr = 0.75 * (upper - lower) + lower
        upper = lower = thr

    state, qualified, unqualified = _qualified_states(p, upper, lower, n_up, n_dn)
    n = float(state.size)
    d.lfp_frac_above = float((state > 0).sum() / n)
    d.lfp_frac_below = float((state < 0).sum() / n)
    d.lfp_frac_between = float((state == 0).sum() / n) if is_dual else None
    d.qualified_transitions = int(qualified)
    d.unqualified_excursions = int(unqualified)
    if d.hours_observed:
        d.transitions_per_hour = float(qualified / d.hours_observed)

    if not is_dual:
        d.caveats.append(
            "Single Threshold mode has one threshold and two states, so there is no 'between' "
            "fraction and the amplitude ramps fully between the limits rather than holding (D22).")

    # The amplitude side comes from the controller replay when one was run, because that is where
    # the transition durations turn a state sequence into a trajectory.
    r = replay_result
    if r is not None:
        d.stim_frac_at_upper = getattr(r, "frac_time_at_upper", None)
        d.stim_frac_at_lower = getattr(r, "frac_time_at_lower", None)
        if None not in (d.stim_frac_at_upper, d.stim_frac_at_lower):
            d.stim_frac_mid = float(max(0.0, 1.0 - d.stim_frac_at_upper - d.stim_frac_at_lower))
        amp = getattr(r, "state", None)
        if amp is not None:
            a = np.asarray(amp, float).ravel()
            a = a[np.isfinite(a)]
            if a.size:
                d.mean_amplitude_mA = float(a.mean())
                span = float(a.max() - a.min())
                params = getattr(r, "params", None) or {}
                a_lo, a_hi = params.get("amp_low_mA"), params.get("amp_high_mA")
                if a_lo is not None and a_hi is not None and float(a_hi) > float(a_lo):
                    d.amplitude_duty = float((d.mean_amplitude_mA - float(a_lo))
                                             / (float(a_hi) - float(a_lo)))
                elif span > 0:
                    d.amplitude_duty = float((d.mean_amplitude_mA - a.min()) / span)
    else:
        d.caveats.append(
            "No controller replay was supplied, so the amplitude-side fractions are absent. Time "
            "spent past a threshold is NOT the same as time at an amplitude limit, because the "
            "amplitude ramps slowly and a brief excursion moves it only part of the way.")

    d.predicted_failure_mode = _failure_mode(
        d.lfp_frac_above, d.lfp_frac_below, d.stim_frac_at_upper, d.stim_frac_at_lower)
    return d
