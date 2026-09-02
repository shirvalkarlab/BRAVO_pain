"""The gate between the open-loop and closed-loop stages.

WHAT THIS MODULE IS FOR
-----------------------
Stage 1 searches rate, pulse width and amplitude and freezes a configuration. Stage 2 configures
closed-loop therapy on top of that frozen configuration. Between them sits a decision that is not a
modelling step at all: is Stage 1's result good enough to justify configuring BrainSense, given that
configuring it makes rate and pulse width unchangeable until it is torn down again?

The whole reason this gate is a separate module with its own tests is that it MUST BE ABLE TO SAY
NO, and it must say no in a way that names the specific condition that failed. A single boolean
"ready" flag would be useless to a clinician: "not ready" prompts the question "not ready why", and
if the answer is "the sensed band never passed the response test" that is a data-collection problem,
whereas if it is "the chosen rate is 40 Hz" that is a programming problem, and the two have nothing
to do with each other. So every condition is evaluated and reported individually, and evaluation
never short-circuits on the first failure.

THREE-VALUED CONDITIONS, AND WHY "NOT ASSESSED" IS NOT A PASS
-------------------------------------------------------------
Each condition returns ``True`` (passed), ``False`` (failed) or ``None`` (NOT ASSESSED — the
question could not be put to the available data). ``None`` is emphatically not a pass. Treating an
unasked question as satisfied is the exact failure mode this project has spent its effort avoiding:
it would license closed-loop configuration on the strength of evidence nobody collected. It is also
not the same as a failure, because a failure says the data answered and the answer was no, while
``None`` says go and measure it. Both block the gate; they differ in what the clinician should do
next, which is why they are distinguished.

THE FOUR CONDITIONS
-------------------
``rate_at_or_above_adaptive_minimum``
    A group configured for Adaptive Therapy has a HIGHER minimum stimulation rate than an open-loop
    group (A610 manual p. 35). ``percept_adaptive.MIN_ADAPTIVE_RATE_HZ`` holds the value, 55 Hz,
    which is PI-supplied rather than quoted from the labelling — the labelling states the constraint
    and its direction but does not print the number on the pages reviewed. A frozen rate below it
    cannot be programmed with Adaptive Therapy at all, so this condition is checked first and it is
    the cheapest one to fail. Note that such a rate may be perfectly usable OPEN loop; the floor
    belongs to the adaptive configuration, not to therapy in general.

``openloop_choice_resolved``
    The frozen rate and pulse width must be resolved against their own uncertainty, or a clinician
    must have recorded an explicit override with a reason. This is the condition that carries the
    argument. Freezing rate and pulse width forecloses the open-loop search, so freezing values the
    surface cannot distinguish from the ones already in force spends the option for nothing. An
    override is available because a clinician may have reasons this module cannot see — a tolerated
    setting, a charge-density limit, a scheduling constraint — but the override has to be recorded
    with its reason, and it is reported as an override and never as a pass.

``adaptive_band_passes_lfp_response``
    A sensed band must exist that lies entirely inside 8-30 Hz AND responds to stimulation
    amplitude. Both halves are necessary and they are independent. The range is the device's:
    Adaptive Therapy can only be driven by a band inside 8-30 Hz, and the wider 1-96 Hz range is
    Sensing Only, meaning the signal can be recorded but a change in it will not change stimulation.
    The response requirement is also the device's (manual p. 35: "Adaptive Therapy relies on LFP
    signals that respond to stimulation amplitude changes"), and it is a DIFFERENT question from
    whether the band tracks pain. A band can correlate with reported pain perfectly and still be
    useless as a control signal, because the controller does not act on pain — it acts on the band,
    and its only actuator is amplitude. The test itself is ``routines/lfp_response.assess_response``,
    called as it stands; this module supplies candidates and interprets verdicts, and computes no
    statistics of its own.

``amplitude_limits_inside_envelope_and_under_ceiling``
    The adaptive amplitude limits are the range the device will move within, and they become the
    patient limits if the group is later switched from Adaptive to Sensing Only. They must sit under
    the declared 4.9 mA ceiling and inside the amplitude envelope actually delivered on that
    hemisphere. The envelope requirement is doing real work rather than being a formality: this
    record establishes that amplitude does NOT predict side-effect severity (Spearman rho = -0.013,
    p = 0.79, n = 417 non-procedural steps with stimulation on), and only 5 of those rows sit above
    4 mA. So above 4 mA is UNKNOWN rather than safe, and an adaptive limit above the delivered
    maximum would hand the device authority to go somewhere no one has ever been.

Typical use::

    from StimOptimizer.routines import stage_gate as GATE
    g = GATE.evaluate_gate(stage1_result.frozen)
    print(g.describe())
    if not g.passed:
        for name, detail in g.refusals():
            print(name, detail)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import lfp_response as LFP
from . import percept_adaptive as PA

#: Amplitude ceiling the plan may propose, in mA. PI-declared (2026-08-30).
AMP_CEILING_MA = 4.9

#: Default sensed-band width, in Hz. This is OUR default and not a device figure: the labelling
#: specifies the permitted band RANGE (8-30 Hz) but the width is a configuration choice. 5 Hz is
#: chosen because it is wide enough to contain several FFT bins at the device's 256-point size and
#: narrow enough that a band centred anywhere from 10.5 to 27.5 Hz stays inside the adaptive range.
DEFAULT_BAND_WIDTH_HZ = 5.0

#: Candidate band centres swept when the caller does not supply their own. The endpoints are set by
#: the adaptive range and the default width: with a 5 Hz band, 10.5 Hz reaches down to exactly 8 Hz
#: and 27.5 Hz reaches up to exactly 30 Hz.
DEFAULT_BAND_CENTERS_HZ = tuple(np.round(np.arange(10.5, 27.51, 0.5), 2))

#: Mode-required direction for the capture contrast. Dual and Single Threshold both need the band
#: SUPPRESSED at higher amplitude; only Single Inverse wants the opposite, and Single Inverse is
#: Sensing Only and cannot drive therapy at all.
DEFAULT_MODE_REQUIRES = "suppression"

#: Threshold on a SELECTION-CORRECTED permutation p-value for a selected band to count as
#: statistically supported. 0.05 is the conventional level and is fixed here rather than tuned. It
#: must never be raised to make a gate pass: the gate exists to be able to refuse, and a threshold
#: adjusted until the answer changes is not a threshold.
SELECTION_ALPHA = 0.05

#: Threshold on the FDR-adjusted q-value. A band is required to survive multiplicity correction as
#: well as its own permutation test, because the band was chosen from a family of candidates and the
#: uncorrected p-value of a selected maximum is not a valid test of it.
SELECTION_FDR_Q = 0.05


@dataclass(frozen=True)
class SelectedBand:
    """A biomarker band chosen by the upstream biomarker pipeline, carrying its own statistics.

    This is an INPUT to the gate and is never computed here. The distinction matters because the
    selection correction is the hard part of the statistic: a band picked as the best of a family
    cannot be tested with the uncorrected p-value of that maximum, and reconciling the permutation
    family with the family the band was actually selected from is what the biomarker track does.
    The gate's job is to read the reconciled numbers and say whether they clear a stated threshold.

    ``perm_p`` is the SELECTION-CORRECTED permutation p-value. ``fdr_q`` is its multiplicity-adjusted
    counterpart. ``exceeds_null_95th`` records whether the observed correlation exceeded its own
    permutation null's 95th percentile, which is a statement about the same evidence from a
    different angle and is reported alongside rather than folded in.
    """

    outcome: str
    center_hz: float
    band_width_hz: float
    r: float = float("nan")
    perm_p: float | None = None
    fdr_q: float | None = None
    exceeds_null_95th: bool | None = None
    provenance: str = ""

    @property
    def band_hz(self) -> tuple:
        return (float(self.center_hz) - float(self.band_width_hz) / 2.0,
                float(self.center_hz) + float(self.band_width_hz) / 2.0)

    def adaptive_capable(self) -> tuple:
        """``(ok, reason)`` from the device's own range check. A DEVICE fact, not a statistical one."""
        return PA.band_is_adaptive_capable(self.center_hz, self.band_width_hz)

    def statistically_supported(self, *, alpha=SELECTION_ALPHA, fdr_q=SELECTION_FDR_Q) -> bool | None:
        """``None`` when no selection-corrected p-value was supplied — not assessed, not a pass."""
        if self.perm_p is None:
            return None
        if float(self.perm_p) >= float(alpha):
            return False
        if self.fdr_q is not None and float(self.fdr_q) >= float(fdr_q):
            return False
        return True


@dataclass(frozen=True)
class ResponseSummary:
    """An LFP-response result established ELSEWHERE and supplied to the gate.

    ``routines/lfp_response.assess_response`` tests one band against one amplitude contrast from
    row-level data. A verdict drawn over the whole historical record — every sensing channel crossed
    with every stimulation rate — is a different and larger computation, and when another track has
    already run it there is no honest way for this module to reproduce it from a summary. So the
    summary is accepted as an input and reported WITH ITS SOURCE, never presented as something the
    gate computed.

    ``responds`` is the supplied verdict. ``None`` means the supplier did not reach one.
    """

    responds: bool | None
    n_cells_suppressing: int | None = None
    n_cells_total: int | None = None
    one_sided_p: float | None = None
    replication_note: str = ""
    source: str = ""

    def describe(self) -> str:
        bits = []
        if self.n_cells_suppressing is not None and self.n_cells_total is not None:
            bits.append(f"{self.n_cells_suppressing} of {self.n_cells_total} channel-by-rate cells "
                        "show suppression")
        if self.one_sided_p is not None:
            bits.append(f"one-sided binomial p = {float(self.one_sided_p):.4g}")
        if self.replication_note:
            bits.append(self.replication_note)
        body = "; ".join(bits) if bits else "no summary statistics supplied"
        src = f" [supplied by {self.source}]" if self.source else " [supplied by the caller]"
        return body + src


#: The reconciled RCS08 biomarker plate, as handed over by the biomarker track on 2026-09-02 (audit
#: item F8 part 2, commit 6001e00). Recorded here so this module, its tests and TWO_STAGE_DESIGN.md
#: all cite ONE set of numbers instead of three drifting copies.
#:
#: PROVISIONAL. Three successive corrections have now moved this statistic, and these are the
#: current best estimates rather than a settled result. They are the selection-corrected values:
#: the permutation family was reconciled with the family the band was actually selected from, which
#: moved ``nrs`` from 0.0500 to 0.0809 and ``left_leg_vas`` from 0.6074 to 0.4166. Neither observed
#: correlation exceeds its own null 95th percentile.
#:
#: The two bands fail for INDEPENDENT reasons and conflating them would overstate the case. The
#: 3.92 Hz band is excluded by a DEVICE constraint — at 5 Hz width it spans roughly 1.4-6.4 Hz,
#: entirely outside the 8-30 Hz adaptive window — and that exclusion holds whatever its p-value had
#: turned out to be. The 14.8 Hz band IS adaptive-capable and is excluded on its statistics alone.
RCS08_SELECTED_BANDS = (
    SelectedBand(outcome="nrs", center_hz=3.9215, band_width_hz=DEFAULT_BAND_WIDTH_HZ,
                 r=-0.5303, perm_p=0.0809, fdr_q=None, exceeds_null_95th=False,
                 provenance="biomarker track 2026-09-02, audit F8 part 2, commit 6001e00; "
                            "selection-corrected from perm_p 0.0500"),
    SelectedBand(outcome="left_leg_vas", center_hz=14.817, band_width_hz=DEFAULT_BAND_WIDTH_HZ,
                 r=-0.6343, perm_p=0.4166, fdr_q=0.5055, exceeds_null_95th=False,
                 provenance="biomarker track 2026-09-02, audit F8 part 2, commit 6001e00; "
                            "selection-corrected from perm_p 0.6074"),
)

#: The LFP-response verdict already established on the real RCS08 record, supplied by the same
#: hand-over. Reported by the gate with attribution; this module did not compute it.
RCS08_RESPONSE_SUMMARY = ResponseSummary(
    responds=False, n_cells_suppressing=3, n_cells_total=15, one_sided_p=0.996,
    replication_note="the sole bilateral replication is at 165 Hz",
    source="the LFP-response run on the real RCS08 record, 2026-09-02")


@dataclass
class LfpEvidence:
    """The measurements the LFP-response condition needs, in one place.

    Two accepted forms, because the two arise in different places in this project.

    ``magnitude`` + ``freqs``
        A spectrogram-like matrix of LFP MAGNITUDE (not power), one row per recording window, with
        its frequency axis. Band power is then computed per candidate band by
        ``lfp_response.device_band_power``, which uses the DEVICE's definition — the linear sum of
        squared magnitude over the band, not a log and not a mean (manual p. 39). Using the device's
        definition is not pedantry: the threshold has to be expressed in the units the device
        thresholds, and a mean rather than a sum differs by the bin count.

    ``band_power``
        Power already reduced per band, as ``{(center_hz, width_hz): array}``. Use this when the
        power came from somewhere that already applied the device definition.

    ``amplitude_mA`` is required in both forms and must align row-for-row. ``era`` blocks the time
    confound, which is not optional in this record because stimulation amplitude rose over the
    programme, so an unadjusted amplitude effect is partly a time effect. ``cluster`` is the repeat
    unit for cluster-robust standard errors.
    """

    amplitude_mA: object
    magnitude: object = None
    freqs: object = None
    band_power: dict = field(default_factory=dict)
    era: object = None
    cluster: object = None
    mode_requires: str = DEFAULT_MODE_REQUIRES
    hemisphere: str | None = None

    def power_for(self, center_hz, width_hz):
        """Band power for one candidate band, or ``None`` if this evidence cannot supply it."""
        key = (round(float(center_hz), 6), round(float(width_hz), 6))
        for k, v in self.band_power.items():
            if (round(float(k[0]), 6), round(float(k[1]), 6)) == key:
                return np.asarray(v, float)
        if self.magnitude is None or self.freqs is None:
            return None
        return LFP.device_band_power(self.magnitude, self.freqs, center_hz, width_hz)


@dataclass
class GateCondition:
    """One named condition, its verdict, and the sentence explaining the verdict."""

    name: str
    passed: bool | None
    detail: str
    overridden: bool = False
    evidence: dict = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        """True when this condition prevents Stage 2 from starting. ``None`` blocks."""
        return self.passed is not True

    @property
    def verdict(self) -> str:
        if self.passed is True:
            return "OVERRIDDEN" if self.overridden else "PASS"
        return "FAIL" if self.passed is False else "NOT ASSESSED"


@dataclass
class GateResult:
    """The gate's decision, with every condition reported whether it passed or not."""

    conditions: list
    frozen: object = None

    @property
    def passed(self) -> bool:
        """Stage 2 may start only if every condition is strictly ``True``."""
        return bool(self.conditions) and all(c.passed is True for c in self.conditions)

    def condition(self, name: str) -> GateCondition:
        for c in self.conditions:
            if c.name == name:
                return c
        raise KeyError(f"no gate condition named {name!r}; have "
                       f"{[c.name for c in self.conditions]}")

    def refusals(self) -> list:
        """``(name, detail)`` for every condition that blocks, in evaluation order."""
        return [(c.name, c.detail) for c in self.conditions if c.blocking]

    def failed_names(self) -> list:
        return [c.name for c in self.conditions if c.passed is False]

    def not_assessed_names(self) -> list:
        return [c.name for c in self.conditions if c.passed is None]

    def describe(self) -> str:
        head = ("GATE: Stage 2 MAY START — every condition passed" if self.passed
                else f"GATE: Stage 2 MUST NOT START — {len(self.refusals())} of "
                     f"{len(self.conditions)} conditions block")
        lines = [head]
        for c in self.conditions:
            lines.append(f"  [{c.verdict:12s}] {c.name}: {c.detail}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# The individual conditions
# ---------------------------------------------------------------------------------------------
def check_rate_floor(frozen, *, min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ) -> GateCondition:
    """Every hemisphere's frozen rate must be at or above the adaptive minimum."""
    rates = {s.hemisphere: float(s.rate_hz) for s in frozen.settings}
    if not rates:
        return GateCondition("rate_at_or_above_adaptive_minimum", None,
                             "no frozen setting to check: Stage 1 produced no hemisphere result",
                             evidence=dict(rates=rates))
    below = {h: r for h, r in rates.items() if r < float(min_rate_hz)}
    if below:
        return GateCondition(
            "rate_at_or_above_adaptive_minimum", False,
            f"frozen rate below the {float(min_rate_hz):g} Hz adaptive minimum on "
            + ", ".join(f"{h} ({r:g} Hz)" for h, r in sorted(below.items()))
            + ". Adaptive Therapy cannot be programmed at this rate (A610 manual p. 35: minimum "
              "rate is higher with Adaptive Therapy configured). The rate may still be usable open "
              "loop — the floor belongs to the adaptive configuration.",
            evidence=dict(rates=rates, below=below, min_rate_hz=float(min_rate_hz)))
    return GateCondition(
        "rate_at_or_above_adaptive_minimum", True,
        "every frozen rate is at or above the adaptive minimum of "
        f"{float(min_rate_hz):g} Hz ("
        + ", ".join(f"{h} {r:g} Hz" for h, r in sorted(rates.items())) + ")",
        evidence=dict(rates=rates, min_rate_hz=float(min_rate_hz)))


def check_openloop_resolved(frozen) -> GateCondition:
    """The frozen rate and pulse width must be resolved, or explicitly overridden with a reason."""
    per_hemi = {s.hemisphere: dict(rate_resolved=s.rate_resolved, pw_resolved=s.pw_resolved,
                                   reasons=list(s.reasons)) for s in frozen.settings}
    if frozen.resolved:
        return GateCondition(
            "openloop_choice_resolved", True,
            "the frozen rate and pulse width are resolved against their own uncertainty on every "
            "hemisphere", evidence=dict(per_hemisphere=per_hemi))
    unresolved = [f"{s.hemisphere} (rate resolved: {s.rate_resolved}, pulse width resolved: "
                  f"{s.pw_resolved})" for s in frozen.settings if not s.resolved]
    if frozen.overridden:
        return GateCondition(
            "openloop_choice_resolved", True,
            "NOT resolved on " + "; ".join(unresolved)
            + f" — proceeding under a recorded clinician override: "
              f"{frozen.override.get('reason')!r}"
            + (f" (by {frozen.override.get('by')})" if frozen.override.get("by") else "")
            + ". This is an override, not a pass: the open-loop choice remains undistinguished "
              "from the setting already in force.",
            overridden=True, evidence=dict(per_hemisphere=per_hemi, override=dict(frozen.override)))
    # Distinguish "asked and answered no" from "never asked" so the clinician knows what to do.
    any_not_assessed = any(s.rate_resolved is None or s.pw_resolved is None
                           for s in frozen.settings)
    detail = ("the frozen rate and/or pulse width are NOT resolved against their uncertainty on "
              + "; ".join(unresolved)
              + ". Freezing them forecloses the open-loop search, so freezing values the surface "
                "cannot distinguish from the ones already in force spends that option for nothing. "
                "Either collect the evidence that separates them, or record a clinician override "
                "with a reason via stage1_openloop.clinician_override.")
    if any_not_assessed:
        detail += (" At least one component is NOT ASSESSED rather than refused, which means the "
                   "question was never put to the data — see the per-hemisphere reasons.")
    return GateCondition("openloop_choice_resolved", False, detail,
                         evidence=dict(per_hemisphere=per_hemi))


def check_selected_band_in_adaptive_window(selected_bands) -> GateCondition:
    """Does any SELECTED biomarker band lie entirely inside the 8-30 Hz adaptive window?

    This is a pure DEVICE check and it is kept as its own condition precisely so that it cannot be
    confused with the statistical one. A band outside the window is excluded whatever its p-value
    turns out to be, and a band inside the window is admitted here whatever its p-value turns out to
    be. Conflating the two reasons would overstate the case against a band that fails only one of
    them, and on the current RCS08 plate the two bands fail for exactly these two different reasons.
    """
    if not selected_bands:
        return GateCondition("selected_band_inside_adaptive_window", None,
                             "no selected biomarker band was supplied, so whether any candidate is "
                             "adaptive-capable is NOT ASSESSED")
    inside, outside = [], []
    for b in selected_bands:
        ok, why = b.adaptive_capable()
        lo, hi = b.band_hz
        rec = dict(outcome=b.outcome, center_hz=float(b.center_hz),
                   band_width_hz=float(b.band_width_hz), band_hz=(lo, hi), reason=why)
        (inside if ok else outside).append(rec)
    ev = dict(inside=inside, outside=outside,
              adaptive_range_hz=list(PA.ADAPTIVE_LFP_BAND_HZ))
    outside_txt = "; ".join(
        f"{r['outcome']} at {r['center_hz']:.4g} Hz spans {r['band_hz'][0]:.4g}-"
        f"{r['band_hz'][1]:.4g} Hz" for r in outside)
    if not inside:
        return GateCondition(
            "selected_band_inside_adaptive_window", False,
            f"no selected band lies entirely inside the adaptive window "
            f"{PA.ADAPTIVE_LFP_BAND_HZ[0]:g}-{PA.ADAPTIVE_LFP_BAND_HZ[1]:g} Hz: {outside_txt}. "
            "Such a band can be SENSED (Sensing Only spans "
            f"{PA.SENSING_ONLY_LFP_BAND_HZ[0]:g}-{PA.SENSING_ONLY_LFP_BAND_HZ[1]:g} Hz) but a "
            "change in it cannot drive stimulation on this device. This exclusion is a DEVICE "
            "constraint and is INDEPENDENT of the band's statistics.", evidence=ev)
    inside_txt = ", ".join(f"{r['outcome']} at {r['center_hz']:.4g} Hz "
                           f"({r['band_hz'][0]:.4g}-{r['band_hz'][1]:.4g} Hz)" for r in inside)
    detail = (f"{len(inside)} of {len(selected_bands)} selected bands lie inside the adaptive "
              f"window {PA.ADAPTIVE_LFP_BAND_HZ[0]:g}-{PA.ADAPTIVE_LFP_BAND_HZ[1]:g} Hz: "
              f"{inside_txt}")
    if outside:
        detail += (f". Excluded by the DEVICE window regardless of their statistics: "
                   f"{outside_txt}")
    return GateCondition("selected_band_inside_adaptive_window", True, detail, evidence=ev)


def check_selected_band_statistical_support(selected_bands, *, alpha=SELECTION_ALPHA,
                                            fdr_q=SELECTION_FDR_Q) -> GateCondition:
    """Is an ADAPTIVE-CAPABLE selected band statistically supported after selection correction?

    Only adaptive-capable bands are considered, because a band the device cannot use is already
    refused by the window condition and its p-value is beside the point. Support requires the
    selection-corrected permutation p-value to clear ``alpha`` and, when a q-value is supplied, to
    survive multiplicity correction as well — a band chosen as the best of a family cannot be
    tested with the uncorrected p-value of that maximum.

    The thresholds are fixed and must not be raised to make the gate pass.
    """
    if not selected_bands:
        return GateCondition("selected_band_statistically_supported", None,
                             "no selected biomarker band was supplied, so statistical support is "
                             "NOT ASSESSED")
    rows, supported, not_assessed = [], [], []
    for b in selected_bands:
        ok, _ = b.adaptive_capable()
        if not ok:
            continue
        verdict = b.statistically_supported(alpha=alpha, fdr_q=fdr_q)
        rows.append(dict(outcome=b.outcome, center_hz=float(b.center_hz), r=float(b.r),
                         perm_p=b.perm_p, fdr_q=b.fdr_q,
                         exceeds_null_95th=b.exceeds_null_95th, supported=verdict,
                         provenance=b.provenance))
        if verdict is True:
            supported.append(b)
        elif verdict is None:
            not_assessed.append(b)
    ev = dict(candidates=rows, alpha=float(alpha), fdr_q_threshold=float(fdr_q))

    def _num(b):
        bits = [f"{b.outcome} at {float(b.center_hz):.4g} Hz, r = {float(b.r):+.4f}"]
        if b.perm_p is not None:
            bits.append(f"selection-corrected perm_p = {float(b.perm_p):.4f}")
        if b.fdr_q is not None:
            bits.append(f"FDR q = {float(b.fdr_q):.4f}")
        if b.exceeds_null_95th is False:
            bits.append("does not exceed its own null 95th percentile")
        return "; ".join(bits)

    if not rows:
        return GateCondition(
            "selected_band_statistically_supported", False,
            "no selected band is adaptive-capable, so there is no candidate whose statistics could "
            "support closed-loop use. See selected_band_inside_adaptive_window for the device "
            "reason, which is independent of any p-value.", evidence=ev)
    if supported:
        return GateCondition(
            "selected_band_statistically_supported", True,
            f"{len(supported)} of {len(rows)} adaptive-capable selected bands are statistically "
            f"supported at alpha = {float(alpha):g} after selection correction: "
            + "; ".join(_num(b) for b in supported), evidence=ev)
    if len(not_assessed) == len(rows):
        return GateCondition(
            "selected_band_statistically_supported", None,
            f"all {len(rows)} adaptive-capable selected bands lack a selection-corrected "
            "permutation p-value, so their support is NOT ASSESSED: "
            + "; ".join(_num(b) for b in not_assessed), evidence=ev)
    failing = [b for b in selected_bands
               if b.adaptive_capable()[0]
               and b.statistically_supported(alpha=alpha, fdr_q=fdr_q) is False]
    return GateCondition(
        "selected_band_statistically_supported", False,
        f"no adaptive-capable selected band is statistically supported at alpha = "
        f"{float(alpha):g} with FDR q < {float(fdr_q):g} after selection correction: "
        + "; ".join(_num(b) for b in failing)
        + ". The band the device could actually use is therefore not supported by the data, which "
          "is a separate refusal from the window exclusion applying to any other candidate.",
        evidence=ev)


def check_adaptive_band(frozen, *, lfp=None, band_centers=DEFAULT_BAND_CENTERS_HZ,
                        band_width_hz=DEFAULT_BAND_WIDTH_HZ,
                        min_sep_d=LFP.MIN_CAPTURE_SEPARATION_D,
                        response_summary=None) -> GateCondition:
    """Does a sensed band exist inside 8-30 Hz that responds to stimulation amplitude?

    Two independent requirements, checked in order. The device range comes first because it is a
    hard fact about the hardware and costs nothing to check: ``percept_adaptive.
    band_is_adaptive_capable`` requires the WHOLE band inside 8-30 Hz, not just its centre, so a
    band centred at 9 Hz with 5 Hz width reaches down to 6.5 Hz and is excluded. The response test
    comes second and needs measurements. With no LFP evidence the condition is NOT ASSESSED, which
    is the state this project's design matrix is actually in: it carries stimulation settings and
    pain ratings and no spectral data at all.

    ``response_summary`` supplies a verdict established ELSEWHERE and takes precedence over any
    row-level test run here. It exists because a verdict computed over the whole historical record —
    every sensing channel crossed with every stimulation rate — is a larger computation than
    ``assess_response`` performs on one band, and when another track has already run it the honest
    thing is to report their number with attribution rather than to recompute something smaller and
    present it as the same claim. The detail string always names the source.
    """
    if response_summary is not None:
        ev = dict(source="supplied", n_cells_suppressing=response_summary.n_cells_suppressing,
                  n_cells_total=response_summary.n_cells_total,
                  one_sided_p=response_summary.one_sided_p)
        if response_summary.responds is True:
            return GateCondition("adaptive_band_passes_lfp_response", True,
                                 "the LFP-response requirement is met according to a verdict "
                                 f"established outside this module: {response_summary.describe()}",
                                 evidence=ev)
        if response_summary.responds is False:
            return GateCondition(
                "adaptive_band_passes_lfp_response", False,
                "the LFP-response requirement FAILS on the historical record, according to a "
                f"verdict established outside this module: {response_summary.describe()}. Adaptive "
                "Therapy relies on a control signal that moves with stimulation amplitude (A610 "
                "manual p. 35); without that response the loop has no authority, however well the "
                "band tracks pain.", evidence=ev)
        return GateCondition("adaptive_band_passes_lfp_response", None,
                             "the supplied LFP-response summary reaches no verdict, so the "
                             f"requirement is NOT ASSESSED: {response_summary.describe()}",
                             evidence=ev)

    capable, rejected = [], []
    for c in band_centers:
        ok, why = PA.band_is_adaptive_capable(c, band_width_hz)
        (capable if ok else rejected).append((float(c), why))
    ev = dict(n_candidates=len(tuple(band_centers)), n_inside_adaptive_range=len(capable),
              band_width_hz=float(band_width_hz),
              adaptive_range_hz=list(PA.ADAPTIVE_LFP_BAND_HZ))
    if not capable:
        return GateCondition(
            "adaptive_band_passes_lfp_response", False,
            f"none of the {len(tuple(band_centers))} candidate band centres yields a band that "
            f"lies entirely inside the adaptive range "
            f"{PA.ADAPTIVE_LFP_BAND_HZ[0]:g}-{PA.ADAPTIVE_LFP_BAND_HZ[1]:g} Hz at a width of "
            f"{float(band_width_hz):g} Hz. Such a band can be SENSED (Sensing Only spans "
            f"{PA.SENSING_ONLY_LFP_BAND_HZ[0]:g}-{PA.SENSING_ONLY_LFP_BAND_HZ[1]:g} Hz) but a "
            "change in it cannot drive stimulation on this device.", evidence=ev)

    if lfp is None:
        return GateCondition(
            "adaptive_band_passes_lfp_response", None,
            f"{len(capable)} candidate bands lie inside the adaptive range, but NO LFP EVIDENCE "
            "was supplied, so whether any of them responds to stimulation amplitude is NOT "
            "ASSESSED. Adaptive Therapy relies on that response (A610 manual p. 35), and it is a "
            "different question from whether the band tracks pain: a band can correlate with pain "
            "perfectly and still be useless as a control signal, because the controller acts on "
            "the band and its only actuator is amplitude. Supply an LfpEvidence carrying LFP "
            "magnitude or band power against the amplitude it was recorded at.", evidence=ev)

    results, passing, not_assessed = {}, [], []
    for c, _ in capable:
        power = lfp.power_for(c, band_width_hz)
        if power is None:
            not_assessed.append(c)
            continue
        r = LFP.assess_response(power, lfp.amplitude_mA, era=lfp.era, cluster=lfp.cluster,
                                mode_requires=lfp.mode_requires, min_sep_d=min_sep_d)
        results[float(c)] = r
        if r.responds is True:
            passing.append(float(c))
    ev.update(n_tested=len(results), n_passing=len(passing), passing_centers=sorted(passing),
              n_power_unavailable=len(not_assessed),
              verdicts={k: v.describe() for k, v in results.items()})

    if passing:
        best = min(passing, key=lambda c: -results[c].separation_d)
        r = results[best]
        return GateCondition(
            "adaptive_band_passes_lfp_response", True,
            f"{len(passing)} of {len(results)} tested bands inside the adaptive range respond to "
            f"stimulation amplitude. Best separated: centre {best:g} Hz, width "
            f"{float(band_width_hz):g} Hz — {r.describe()}", evidence=ev)
    if not results:
        return GateCondition(
            "adaptive_band_passes_lfp_response", None,
            f"{len(capable)} candidate bands lie inside the adaptive range but band power could be "
            f"computed for none of them from the supplied evidence, so the response requirement is "
            "NOT ASSESSED.", evidence=ev)
    if all(r.responds is None for r in results.values()):
        one = next(iter(results.values()))
        return GateCondition(
            "adaptive_band_passes_lfp_response", None,
            f"all {len(results)} tested bands returned NOT ASSESSED rather than a verdict: the "
            f"data cannot answer the question. First reason given: {one.reason}", evidence=ev)
    worst = min(results.values(), key=lambda r: (r.responds is not False, -r.separation_d
                                                 if np.isfinite(r.separation_d) else 0.0))
    return GateCondition(
        "adaptive_band_passes_lfp_response", False,
        f"none of the {len(results)} tested bands inside the adaptive range passes the "
        f"stimulation-response requirement. Representative verdict: {worst.describe()}. A band "
        "that does not move with amplitude gives the loop no authority, however well it tracks "
        "pain.", evidence=ev)


def check_amplitude_limits(frozen, *, amp_limits=None, ceiling_mA=AMP_CEILING_MA) -> GateCondition:
    """Adaptive amplitude limits must sit under the ceiling and inside the delivered envelope.

    ``amp_limits`` maps hemisphere to ``(min_mA, max_mA)``. When it is omitted the DELIVERED
    ENVELOPE is used, which passes the envelope test by construction; the detail string says so, so
    a reader is never left thinking a proposal was checked when a default was.
    """
    problems, checked = [], {}
    if not frozen.settings:
        return GateCondition("amplitude_limits_inside_envelope_and_under_ceiling", None,
                             "no frozen setting to check: Stage 1 produced no hemisphere result")
    defaulted = []
    for s in frozen.settings:
        lo_env, hi_env = float(s.amp_delivered_min_mA), float(s.amp_delivered_max_mA)
        if amp_limits is not None and s.hemisphere in amp_limits:
            lo, hi = (float(v) for v in amp_limits[s.hemisphere])
        else:
            lo, hi = lo_env, hi_env
            defaulted.append(s.hemisphere)
        checked[s.hemisphere] = dict(amp_min_mA=lo, amp_max_mA=hi,
                                     envelope=(lo_env, hi_env))
        if not np.isfinite(lo) or not np.isfinite(hi):
            problems.append(f"{s.hemisphere}: limits are not finite ({lo}, {hi}); the delivered "
                            "envelope is empty, so there is nothing to bound the device with")
            continue
        if not hi > lo:
            problems.append(f"{s.hemisphere}: limits must satisfy max > min (got {lo:g}, {hi:g}); "
                            "the device needs a range to move within")
        if hi > float(ceiling_mA) + 1e-9:
            problems.append(f"{s.hemisphere}: upper limit {hi:g} mA exceeds the declared ceiling "
                            f"of {float(ceiling_mA):g} mA")
        if np.isfinite(hi_env) and hi > hi_env + 1e-9:
            problems.append(
                f"{s.hemisphere}: upper limit {hi:g} mA is above the highest amplitude ever "
                f"delivered on this hemisphere ({hi_env:g} mA). This record establishes that "
                "amplitude does NOT predict side-effect severity (Spearman rho = -0.013, p = 0.79 "
                "over 417 non-procedural steps with stimulation on), and only 5 of those rows sit "
                "above 4 mA, so amplitudes above the delivered maximum are UNKNOWN rather than "
                "safe. Handing the device authority to go there is not supported by the data")
        if np.isfinite(lo_env) and lo < lo_env - 1e-9:
            problems.append(
                f"{s.hemisphere}: lower limit {lo:g} mA is below the lowest amplitude delivered on "
                f"this hemisphere ({lo_env:g} mA), so the bottom of the adaptive range has never "
                "been observed as therapeutic")
    note = ("" if not defaulted else
            f" NOTE: limits were not supplied for {', '.join(sorted(defaulted))} and were "
            "DEFAULTED to the delivered envelope, so the envelope test on those hemispheres is "
            "satisfied by construction rather than by a check on a proposal.")
    if problems:
        return GateCondition("amplitude_limits_inside_envelope_and_under_ceiling", False,
                             "; ".join(problems) + note,
                             evidence=dict(checked=checked, ceiling_mA=float(ceiling_mA)))
    return GateCondition(
        "amplitude_limits_inside_envelope_and_under_ceiling", True,
        "adaptive amplitude limits sit inside the delivered envelope and under the "
        f"{float(ceiling_mA):g} mA ceiling on every hemisphere ("
        + "; ".join(f"{h} {v['amp_min_mA']:g}-{v['amp_max_mA']:g} mA"
                    for h, v in sorted(checked.items())) + ")." + note,
        evidence=dict(checked=checked, ceiling_mA=float(ceiling_mA)))


# ---------------------------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------------------------
def evaluate_gate(frozen, *, lfp=None, amp_limits=None, selected_bands=None,
                  response_summary=None,
                  band_centers=DEFAULT_BAND_CENTERS_HZ, band_width_hz=DEFAULT_BAND_WIDTH_HZ,
                  min_rate_hz=PA.MIN_ADAPTIVE_RATE_HZ, ceiling_mA=AMP_CEILING_MA,
                  min_sep_d=LFP.MIN_CAPTURE_SEPARATION_D, alpha=SELECTION_ALPHA,
                  fdr_q=SELECTION_FDR_Q) -> GateResult:
    """Evaluate every gate condition on a frozen configuration and return all four verdicts.

    Evaluation deliberately does NOT short-circuit. A clinician looking at a refusal needs the whole
    picture, because the conditions fail for unrelated reasons and fixing the first one does not
    predict what the second will say. Running all four costs nothing here — three are arithmetic on
    the frozen configuration and the fourth is skipped cheaply when there is no LFP evidence.

    Parameters
    ----------
    frozen
        A :class:`stage1_openloop.FrozenConfiguration`.
    lfp
        An :class:`LfpEvidence`, or ``None``. ``None`` makes the response condition NOT ASSESSED,
        which blocks the gate.
    amp_limits
        ``{hemisphere: (min_mA, max_mA)}`` proposed adaptive limits. Omitted means the delivered
        envelope is used; see :func:`check_amplitude_limits`.
    selected_bands
        A sequence of :class:`SelectedBand` from the upstream biomarker pipeline. When supplied,
        TWO EXTRA conditions are evaluated and reported separately — the device-window check and the
        statistical-support check — because a selected band can fail either one alone and the two
        reasons must not be conflated. When omitted, those conditions are not added at all and the
        window check on the SWEPT candidate set inside ``check_adaptive_band`` is the only band
        gate, which is the right behaviour for a caller doing its own sweep.
    response_summary
        A :class:`ResponseSummary` established outside this module. Takes precedence over any
        row-level response test and is always reported with its source.

    Returns
    -------
    GateResult
        ``.passed`` is ``True`` only when EVERY evaluated condition is strictly ``True``. The number
        of conditions is four, or six when ``selected_bands`` is supplied.
    """
    conditions = [
        check_rate_floor(frozen, min_rate_hz=min_rate_hz),
        check_openloop_resolved(frozen),
    ]
    if selected_bands is not None:
        conditions += [
            check_selected_band_in_adaptive_window(selected_bands),
            check_selected_band_statistical_support(selected_bands, alpha=alpha, fdr_q=fdr_q),
        ]
    conditions += [
        check_adaptive_band(frozen, lfp=lfp, band_centers=band_centers,
                            band_width_hz=band_width_hz, min_sep_d=min_sep_d,
                            response_summary=response_summary),
        check_amplitude_limits(frozen, amp_limits=amp_limits, ceiling_mA=ceiling_mA),
    ]
    return GateResult(conditions=conditions, frozen=frozen)
