"""Stage 1 of the two-stage architecture: the OPEN-LOOP search, whose product is a frozen
configuration for BOTH stimulators, fitted JOINTLY.

WHY THIS IS A SEPARATE STAGE AND NOT ONE DIMENSION OF A FLAT SEARCH
-------------------------------------------------------------------
The device decides the shape of this problem, not the statistics. ``routines/percept_adaptive.py``
records the constraint verbatim from the A610 Clinician Programming Guide (pp. 34-35): "Pulse width
and rate cannot be adjusted once BrainSense has been set up for either hemisphere." To change either
one afterwards, BrainSense has to be removed from the group, which discards the closed-loop
configuration. Closed-loop therapy therefore adapts AMPLITUDE ONLY, with rate and pulse width held
at whatever values were in force when sensing was configured.

That makes the open-loop search a PREREQUISITE rather than an alternative. A single flat optimizer
over rate and amplitude, which is what ``pipeline.run`` implements, models a decision the hardware
will not let a clinician make: it can propose moving the rate at a point in the programme where the
rate is already frozen. Stage 1 exists to finish that decision and hand on a configuration that
cannot be revisited, and to state plainly whether the configuration it hands on was chosen on
evidence or merely inherited.

WHY THE SEARCH IS NOW JOINT (2026-09-14), AND WHAT THAT REPLACES
------------------------------------------------------------------
Until 2026-09-14 this module fitted the Left and the Right hemisphere as two INDEPENDENT
two-dimensional (rate, amplitude) surfaces. The reason on record (``pipeline.py``'s own module
docstring, and this module's own, both since superseded) was that the two sides are usable on
different epoch subsets — a side at 0 mA was excluded from that side's own surface as "a different
therapeutic state", so the two arms ended up fitted on different row counts. That is true, and nothing
here changes it as an observation. But it was never a reason the two currents had to be modelled
INDEPENDENTLY of each other, and it is the wrong reason to have used, because the device only has ONE
frequency knob (the settings history carries a single ``freq_hz`` column, never a per-side rate), and
both currents are reprogrammed CONCURRENTLY every time the device is set — never one held fixed while
the other is probed. Fitting a pain response to one side's current while ignoring what the other
side's current was doing at the same moment is a real confound, not a simplification: it can credit a
change in pain to the wrong stimulator.

The PI's instruction, verbatim, given directly: "Get rid of the whole arm strip and chart display...
Only keep the newer two-stage plan... it should model the left and right sides together because
they're always on." Measured on RCS08 before deciding how to honour it: of 120 epochs with both
currents recorded, 25 have the Left at 0 mA while the Right is on, 10 the other way, 9 both off and
73 both on — so "always on" is not literally true of every epoch, but every epoch DOES carry a real,
non-missing value for both currents (no epoch has one side recorded and the other absent), which is
exactly what a joint fit needs and an independent per-side fit was throwing away by filtering a side's
own zero-current rows out of its own surface.

WHAT STAGE 1 NOW SEARCHES
--------------------------
Rate x amplitude-Left x amplitude-Right, in ONE three-dimensional surface
(``routines.surrogate.JointParameterGrid``), fitted once per (pulse-width-Left, pulse-width-Right)
PAIR that has enough epochs — a JOINT STRATUM, the direct generalisation of the old per-hemisphere
pulse-width stratum. Every epoch that survives the side-effect feasibility filter enters the fit,
including one where either current is 0 mA: the OLD "0 mA is a different therapeutic state" filter
existed to keep a hemisphere's own dose axis from being anchored by "off"; there is no reason to
apply it here, since 0 mA is simply the low end of that axis in a grid that already spans both
currents, and dropping those epochs would throw away most of the information the joint fit exists to
use. The safety model stays PER SIDE (below) because the reported side-effect anchors are inherently
per-hemisphere; only the pain-objective surface is joint.

Stratifying by pulse-width PAIR rather than fitting a single higher-dimensional kernel over pulse
width too is the same modelling choice this module always made for pulse width, generalised: no
information is borrowed BETWEEN pulse-width combinations, which is the conservative direction (a
shared length scale across pulse width would smooth strata towards each other and make a
pulse-width difference look better determined than the design supports).

WHY THE COMMON INCUMBENT MATTERS, AND WHY ``build_context`` IS NOT USED
-------------------------------------------------------------------------
``routines/objective.build_objective`` defines ``J_pain`` as the primary pain item minus its value
at the incumbent epoch, so ``J`` is only comparable between two fits that used the SAME incumbent.
This module calls ``build_objective`` ONCE on the whole matrix with the globally most recent epoch
as incumbent, and then fits the surrogate per joint stratum on that single shared ``J`` column.
``pipeline.run`` and the flat figure set continue to use ``build_context`` unchanged, and are no
longer called from the request path that serves the Stim Optimizer page (see
``bravo_service.run_for_participant``); see the module's own docstring in ``pipeline.py`` for the
one entry point that still uses the old per-arm fit and where it is (still) reachable from.

THE SAFETY MODEL STAYS PER SIDE
--------------------------------
``safety_ceiling.py``'s severity-3 seed is a PI-stated current per hemisphere, and the recorded
side-effect anchors (tolerated settings, programmed limits) are inherently per-hemisphere too —
there is no joint side-effect report to fit a single safety surface to. So each side keeps its own
two-dimensional ``SafetyGP`` exactly as before, fitted on ``(rate, amp_<side>)``, and the JOINT safe
set at a (rate, amp_Left, amp_Right) grid cell is "safe on the Left's own (rate, amp_Left) view of
this cell AND safe on the Right's own (rate, amp_Right) view of it" — a cell is unsafe if either
side's own model says its own current is unsafe at that rate, which is exactly the PI-stated
per-side ceiling (decision 145) combined with whatever the fitted side-effect surface adds.

THE ADAPTIVE ENVELOPE, APPLIED BEFORE SCORING (2026-09-12, unchanged in kind, now joint)
------------------------------------------------------------------------------------------
The rate axis is SHARED, so the adaptive-minimum-rate constraint
(``routines/adaptive_envelope.py``) is applied ONCE, to the one shared rate axis, rather than once
per hemisphere. Everything else about the envelope — a non-empty scientific or physiological reason
lifts it, an override asked for with no reason is reported as ignored, what was excluded and why is
never hidden — is unchanged.

THE TERMINAL OUTPUT
-------------------
:class:`FrozenConfiguration` keeps its PUBLIC SHAPE — a tuple of two :class:`HemisphereSetting`,
one per side, so ``routines/stage_gate.py`` and ``stage2_closedloop.py`` read it exactly as they
did before. What changed is how the two are produced: BOTH now come from the SAME joint decision,
so ``rate_hz``, ``rate_resolved``, ``gain`` and ``sd_of_difference`` are IDENTICAL on the Left and
the Right setting of one configuration — there is only one rate knob and one joint comparison
against the incumbent now, not two independent ones that could (and, on RCS08, sometimes did)
disagree about the rate. ``pw_us`` and ``amp_star_mA`` stay genuinely per-side, because pulse width
and current are independently programmable on each hemisphere.

Resolution uses the same criterion as before: a candidate counts as resolved only when it beats the
comparison cell by more than the standard deviation OF THE DIFFERENCE, with both posterior standard
deviations propagated (``routines.resolution``). ``None`` still means the question could not be put
to the data (typically a stratum that never delivered the incumbent's rate), which blocks the gate
but is not the same statement as a measured "no".
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .routines.resolution import RESOLUTION_K as _RES_K
from .routines import acquisition as ACQ
from .routines import adaptive_envelope as ENV
from .routines import objective as OBJ
from .routines import plots as PLT
from .routines import surrogate as SUR
from . import safety_ceiling as SC

#: Minimum epochs in a JOINT (pulse-width-Left, pulse-width-Right) stratum before a surface is
#: fitted for it. The same floor the module has always used for a pulse-width stratum, now applied
#: to a pulse-width PAIR: a stratum is not held to a laxer standard than before, and it is not made
#: harder to clear either, since the joint stratum pools what used to be split across two arms.
PW_STRATUM_MIN_EPOCHS = 8

#: Multiplier on the standard deviation of the difference in the resolution criterion. Unchanged;
#: re-exported from routines.resolution, the single definition, so existing importers of
#: ``stage1_openloop.RESOLUTION_K`` keep working.
RESOLUTION_K = _RES_K

#: Amplitude ceiling the search may propose, in mA. Alias only; see ``routines.objective`` for
#: provenance. Single source of truth is ``routines.objective.AMP_HARD_LIMIT_MA``.
AMP_CEILING_MA = OBJ.AMP_HARD_LIMIT_MA

#: Exposure duration, in hours, above which a delivered setting is treated as tolerated for the
#: purposes of seeding the safety model. Same default the flat pipeline uses.
MIN_TOLERATED_H = 72.0

#: The amplitude grid used for EACH side's axis of the joint 3-D surface. Coarser than the flat
#: pipeline's own 0.1 mA-step ``routines.plots.AMP_GRID`` (51 points): a joint grid has TWO
#: amplitude axes instead of one, so holding the same step would multiply the cell count roughly
#: 50-fold (600 cells -> about 30,000) for a resolution finer than a clinician actually programs.
#: 0.25 mA is well inside the device's own programming granularity, so no cell the search could
#: recommend is finer than what gets typed into the tablet. 21 points per side, 12 rates: 5,292
#: joint grid cells, against 600 for the old 2-D grid.
JOINT_AMP_STEP = 0.25
JOINT_AMP_GRID = np.round(np.arange(0.0, OBJ.AMP_HARD_LIMIT_MA + 0.01, JOINT_AMP_STEP), 2)

#: Minimum epochs at ONE rate, inside an already-fitted (pulse-width-Left, pulse-width-Right)
#: stratum, before a PER-RATE (amplitude-Left, amplitude-Right) surface is fitted for it. The
#: same floor as ``PW_STRATUM_MIN_EPOCHS`` -- a rate is not held to a laxer or a stricter standard
#: than a pulse-width pair was.
RATE_STRATUM_MIN_EPOCHS = PW_STRATUM_MIN_EPOCHS

#: The three checks a PER-RATE current recommendation must clear (2026-09-14, following the PI's
#: own measurement that the 3-input joint surface can recommend a current from a surface that is
#: flat almost everywhere, drawing its confidence at a thin rate from data collected at OTHER
#: rates through the shared, pinned rate axis). All three must pass for a rate's current
#: recommendation to be honest:
#:   (i)   the fitted surface is not flat -- its range over safe cells must exceed
#:         ``RESOLUTION_K`` times the median posterior standard deviation over those cells;
#:   (ii)  the usual gain-over-incumbent test (``RESOLUTION_K`` times the standard deviation of
#:         the difference), read from THIS rate's own surface, never a borrowed one;
#:   (iii) the design actually supports telling the two currents apart: at least
#:         ``CURRENT_COVERAGE_MIN_PAIRS`` distinct (left, right) current pairs, each with at least
#:         ``CURRENT_COVERAGE_MIN_REPORTS_PER_PAIR`` reports, spanning at least
#:         ``CURRENT_COVERAGE_MIN_SPAN_MA`` on EACH axis.
CURRENT_COVERAGE_MIN_PAIRS = 6
CURRENT_COVERAGE_MIN_REPORTS_PER_PAIR = 5
CURRENT_COVERAGE_MIN_SPAN_MA = 1.0

#: Per-axis length-scale pinning for the joint (rate, amp_Left, amp_Right) surrogate. Pins the
#: RATE axis only, at the same value ``routines.plots.FIXED_LENGTH_SCALE`` pins it to for the
#: pre-joint 2-D surrogate (the frequency length scale is not identifiable from this design; see
#: ``routines.surrogate._make_kernel``'s own docstring). Both amplitude axes are left ``None``
#: (fitted), since each current's own dose-response should be free to have its own smoothness
#: rather than sharing the other current's.
JOINT_FIXED_LENGTH_SCALE = (PLT.FIXED_LENGTH_SCALE[0], None, None)


# ---------------------------------------------------------------------------------------------
# The frozen configuration
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HemisphereSetting:
    """The rate and pulse width Stage 1 hands on for one hemisphere, and the evidence for them.

    Since 2026-09-14 this is a VIEW onto one JOINT decision, not an independent choice on its own
    side: ``rate_hz``, ``rate_resolved``, ``gain`` and ``sd_of_difference`` are IDENTICAL on the
    Left and the Right setting of one :class:`FrozenConfiguration`, because the device has one rate
    knob and the search fits both currents together. Only ``pw_us`` and ``amp_star_mA`` are
    genuinely per-side, because pulse width and current are independently programmable per
    hemisphere.

    ``rate_resolved`` and ``pw_resolved`` are three-valued. ``True`` means the choice beat its
    comparison by more than the standard deviation of the difference. ``False`` means it did not.
    ``None`` means NOT ASSESSED — the question could not be put to the data at all, which is a
    different statement from a negative answer and must not be collapsed into one.
    """

    hemisphere: str
    rate_hz: float
    pw_us: float | None
    amp_star_mA: float
    amp_delivered_min_mA: float
    amp_delivered_max_mA: float
    #: Epochs on the ONE joint stratum that produced this choice — not the hemisphere's total.
    n_epochs_fitted: int
    rate_resolved: bool | None
    pw_resolved: bool | None
    #: The joint resolution's own numbers (2026-09-14), carried here so a reader does not have to
    #: cross-reference the strata table to find the gain the verdict rests on. Identical on both
    #: sides of one configuration: it is one joint comparison against one incumbent, not two.
    gain: float = float("nan")
    sd_of_difference: float = float("nan")
    reasons: tuple = ()
    detail: dict = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        """Both the rate and the pulse width resolved. ``None`` on either counts as NOT resolved.

        A gate that treated "not assessed" as a pass would license closed-loop configuration on the
        strength of a question nobody asked, so the collapse is deliberately one-directional.
        """
        return self.rate_resolved is True and self.pw_resolved is True


@dataclass(frozen=True)
class FrozenConfiguration:
    """Stage 1's terminal product: what Stage 2 must treat as immovable.

    Frozen in two senses that happen to coincide. Clinically, rate and pulse width freeze in the
    device the moment BrainSense is configured. Programmatically, this is a frozen dataclass, so
    ``cfg.rate_hz = 130`` raises ``FrozenInstanceError`` instead of quietly changing the plan. The
    coincidence is the point: the type system is made to enforce the device constraint.

    ``settings`` keeps its PUBLIC SHAPE from before the joint redesign — a tuple of two
    :class:`HemisphereSetting`, one per side — so every existing reader (``routines/stage_gate.py``,
    ``stage2_closedloop.py``) works unchanged. What changed is that both entries now come from ONE
    joint fit rather than two independent ones; see :class:`HemisphereSetting`.

    ``override`` records a clinician's explicit decision to proceed on an unresolved configuration.
    It is a mapping and it must carry a non-empty ``reason``; see :func:`clinician_override`.

    ``adaptive_envelope`` records whether the search was constrained to the settings the device's
    closed-loop mode can use (``routines/adaptive_envelope.py``), what it excluded and why, and --
    when the constraint was lifted -- the stated reason and who gave it.
    """

    settings: tuple                        # tuple[HemisphereSetting, ...]
    primary_item: str
    incumbent_epoch: float
    incumbent_rate_hz: float
    #: The pulse width in force read from the LEFT column (``pw_us_Left``), kept under this name
    #: for the callers and stored responses that read it. Each side's own value is under
    #: ``incumbent_pw_us_by_side``.
    incumbent_pw_us: float | None
    data_horizon: str
    washin_min: float
    n_epochs_total: int
    override: dict | None = None
    audit: dict = field(default_factory=dict)
    adaptive_envelope: dict = field(default_factory=dict)
    #: ``{hemisphere: pulse width in force on THAT side}``, read from each side's own column
    #: (``pw_us_<side>``), or from the fallback column named in the audit when the side's own is
    #: absent. ``None`` for a side whose pulse width is not recorded on the incumbent epoch.
    incumbent_pw_us_by_side: dict = field(default_factory=dict)

    def setting(self, hemisphere: str) -> HemisphereSetting:
        for s in self.settings:
            if s.hemisphere == hemisphere:
                return s
        raise KeyError(f"no setting for hemisphere {hemisphere!r}; have "
                       f"{[s.hemisphere for s in self.settings]}")

    @property
    def hemispheres(self) -> tuple:
        return tuple(s.hemisphere for s in self.settings)

    @property
    def resolved(self) -> bool:
        """Every hemisphere's rate and pulse width resolved against its own uncertainty."""
        return bool(self.settings) and all(s.resolved for s in self.settings)

    @property
    def overridden(self) -> bool:
        return bool(self.override) and bool(str(self.override.get("reason", "")).strip())

    def describe(self) -> str:
        lines = [f"FROZEN CONFIGURATION (primary outcome: {self.primary_item}; "
                 f"data horizon {self.data_horizon}; wash-in {self.washin_min:g} min)"]
        env = dict(self.adaptive_envelope or {})
        if env.get("statement"):
            lines.append(f"  adaptive envelope: {env['statement']}")
        if env.get("override_ignored"):
            lines.append(f"  NOTE: {env['override_ignored']}")
        for s in self.settings:
            pw = "NOT OBSERVED" if s.pw_us is None else f"{s.pw_us:g} us"
            rate = ("NO ADAPTIVE-CAPABLE RATE" if not np.isfinite(float(s.rate_hz))
                    else f"{s.rate_hz:g} Hz")
            lines.append(
                f"  {s.hemisphere:5s}: rate {rate}, pulse width {pw}, "
                f"amplitude preferred {s.amp_star_mA:.2f} mA "
                f"(delivered {s.amp_delivered_min_mA:.2f}-{s.amp_delivered_max_mA:.2f} mA, "
                f"{s.n_epochs_fitted} epochs) | rate resolved: {s.rate_resolved}, "
                f"pulse width resolved: {s.pw_resolved}")
            for r in s.reasons:
                lines.append(f"         - {r}")
            for x in (env.get("exclusions") or {}).get(s.hemisphere, []):
                lines.append(f"         x EXCLUDED: {x.get('what')} -- {x.get('reason')}")
        lines.append(f"  overall resolved: {self.resolved}"
                     + (f" | CLINICIAN OVERRIDE: {self.override.get('reason')}"
                        if self.overridden else ""))
        return "\n".join(lines)


def clinician_override(cfg: FrozenConfiguration, *, reason: str, by: str | None = None,
                       at: str | None = None) -> FrozenConfiguration:
    """Return a copy of ``cfg`` carrying a recorded clinician override of the resolution
    requirement.

    This does NOT change any setting and it does not make anything resolved. It records that a named
    person decided, for a stated reason, to freeze a configuration whose advantage over the setting
    in force is smaller than the uncertainty in that advantage. The gate reads it as satisfying the
    resolution condition and reports it as an override rather than as a pass, so the distinction
    survives into the report.

    An empty or whitespace reason is refused. An override with no reason is indistinguishable from
    disabling the check, and the whole purpose of this module is that a refusal names its cause.
    """
    if not str(reason).strip():
        raise ValueError(
            "a clinician override requires a non-empty reason. Recording who decided and why is "
            "what separates an override from silently disabling the resolution requirement.")
    return replace(cfg, override=dict(reason=str(reason).strip(), by=by, at=at))


# ---------------------------------------------------------------------------------------------
# Design audit over pulse-width pairs
# ---------------------------------------------------------------------------------------------
def pulse_width_pair_design_audit(fit: pd.DataFrame, *, pwl_col="pw_us_Left",
                                  pwr_col="pw_us_Right",
                                  min_epochs=PW_STRATUM_MIN_EPOCHS) -> dict:
    """How much of the rate x pulse-width-Left x pulse-width-Right space was actually delivered?

    Pure counting, with no test statistic and no model. Generalises the module's old
    single-side ``pulse_width_design_audit`` to a PAIR of pulse widths, because the joint fit
    stratifies on both sides' pulse widths at once.
    """
    pairs = fit[[pwl_col, pwr_col]].apply(tuple, axis=1)
    counts = pairs.value_counts()
    fittable = [tuple(float(v) for v in k) for k, n in counts.items() if int(n) >= int(min_epochs)]
    return dict(
        pw_pairs=[tuple(float(v) for v in k) for k in counts.index],
        epochs_per_pair={f"{k[0]:g}_{k[1]:g}": int(v) for k, v in counts.items()},
        n_pairs_delivered=int(len(counts)),
        fittable_pw_pairs=fittable,
        n_pairs_fittable=int(len(fittable)),
        min_epochs=int(min_epochs),
    )


# ---------------------------------------------------------------------------------------------
# One joint (rate, amplitude-Left, amplitude-Right) stratum
# ---------------------------------------------------------------------------------------------
@dataclass
class JointStratum:
    """One three-dimensional (rate, amplitude-Left, amplitude-Right) surface, fitted at a single
    (pulse-width-Left, pulse-width-Right) PAIR. The joint generalisation of the old
    ``Stage1Slice``."""

    pw_us_left: float
    pw_us_right: float
    n_epochs: int
    grid: object
    gp: object
    mu: np.ndarray
    sd: np.ndarray
    safe: np.ndarray
    i_star: int
    x_star: tuple                       # (rate_hz, amp_mA_left, amp_mA_right)
    mu_star: float
    sd_star: float
    incumbent_mu: float
    incumbent_sd: float
    n_reports: np.ndarray
    queue: np.ndarray
    stopping: object
    incumbent_rate_supported: bool = True
    optimum_rate_supported: bool = True
    batch: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    #: The adaptive envelope on this stratum. ``allowed`` is ``safe`` AND in-envelope, the mask
    #: ``i_star`` was chosen under. ``i_star_unconstrained`` is what the same surface would have
    #: chosen under ``safe`` alone. ``envelope_empty`` means no safe cell lies inside the envelope.
    allowed: np.ndarray | None = None
    i_star_unconstrained: int | None = None
    x_star_unconstrained: tuple | None = None
    mu_star_unconstrained: float = float("nan")
    envelope_empty: bool = False
    envelope_constrained: bool = False
    #: One :class:`RateStratum` per rate this (pulse-width-Left, pulse-width-Right) stratum
    #: actually delivered, keyed on the rate in Hz (2026-09-14). Built by ``run_stage1`` right
    #: after this joint surface is fitted; see the module docstring's "WHY THE SEARCH IS NOW
    #: JOINT" section's sibling, the per-rate honesty check, for why this exists alongside the
    #: 3-input surface rather than instead of it.
    rate_strata: dict = field(default_factory=dict)

    @property
    def optimum_moved_by_envelope(self) -> bool:
        return (self.envelope_constrained and self.i_star_unconstrained is not None
                and int(self.i_star_unconstrained) != int(self.i_star))

    def gain_over_incumbent(self) -> float:
        """Positive means the stratum optimum is better (lower J) than the setting in force."""
        return float(self.incumbent_mu) - float(self.mu_star)

    def sd_of_difference(self) -> float:
        return float(np.sqrt(float(self.sd_star) ** 2 + float(self.incumbent_sd) ** 2))

    def resolves_its_optimum(self, k: float = RESOLUTION_K) -> bool | None:
        """Does this stratum's optimum beat the setting in force by more than the uncertainty in
        that difference? ``None`` means the question cannot be put to this stratum.

        Identical reasoning to the module's pre-joint criterion: ``J`` is zero at the incumbent by
        construction, so a stratum that never delivered the incumbent's RATE has no data anywhere
        near that cell and its posterior there is an extrapolation across the PINNED frequency
        length scale, not a measurement. Support is required on the rate axis specifically for
        that reason; the two amplitude length scales are fitted, so extrapolating across current is
        not treated the same way.
        """
        if not self.incumbent_rate_supported:
            return None
        sd_diff = self.sd_of_difference()
        if not np.isfinite(sd_diff) or sd_diff <= 0:
            return False
        return bool(self.gain_over_incumbent() > float(k) * sd_diff)


@dataclass
class RateStratum:
    """One (amplitude-Left, amplitude-Right) surface, fitted at a SINGLE stimulation rate inside
    one (pulse-width-Left, pulse-width-Right) stratum (2026-09-14).

    This is what actually decides a current recommendation now. The 3-input
    :class:`JointStratum` this sits inside is left untouched and is still reported (as
    ``pooled_across_rates`` in the summary table) because it is still the right tool for choosing
    the RATE and the PULSE WIDTH -- those choices need to pool across rates to have any data at
    all. But reading a CURRENT off that pooled surface at a rate it barely sampled draws its
    apparent precision from OTHER rates through the shared, pinned rate axis; measured on RCS08,
    the pooled surface's own range across every safe cell at 55 Hz was 0.965-0.969 (its kernel's
    signal amplitude sits at its lower bound), so its argmin is noise, not a finding. This class
    fits amplitude alone, at one rate, with no rate axis to borrow through.

    ``fitted`` is ``False`` when there were not enough epochs at this rate to fit anything; every
    other numeric field is then meaningless and ``reason`` says why.
    """

    pw_us_left: float
    pw_us_right: float
    rate_hz: float
    n_epochs: int
    fitted: bool
    reason: str = ""
    grid: object = None
    gp: object = None
    mu: np.ndarray = None                  # (n_amp_left, n_amp_right), this rate's own surface
    sd: np.ndarray = None
    safe: np.ndarray = None
    n_reports: np.ndarray = None
    x_star: tuple = None                   # (amp_mA_left, amp_mA_right)
    mu_star: float = float("nan")
    sd_star: float = float("nan")
    n_reports_total: float = 0.0
    coverage: dict = field(default_factory=dict)
    resolution: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def current_coverage(sub, *, min_pairs=CURRENT_COVERAGE_MIN_PAIRS,
                     min_reports_per_pair=CURRENT_COVERAGE_MIN_REPORTS_PER_PAIR,
                     min_span_mA=CURRENT_COVERAGE_MIN_SPAN_MA) -> dict:
    """Check (iii) of the honest-current rule: does the DESIGN actually let the two currents be
    told apart? ``sub`` needs ``amp_mA_Left``, ``amp_mA_Right`` and ``n`` (report count) columns;
    every row counts, fitted or not, so this can also be run on a PLANNED schedule
    (``current_map_schedule.py``) to check what it would buy before it is run.

    Counts distinct (left, right) current PAIRS carrying at least ``min_reports_per_pair`` reports
    between them, and the span those qualifying pairs cover on each axis separately -- a pair at
    (1.0, 1.0) and one at (1.0, 4.0) span the right axis but say nothing about the left one.
    """
    d = pd.DataFrame(sub)
    if d.empty or not {"amp_mA_Left", "amp_mA_Right", "n"}.issubset(d.columns):
        return dict(n_pairs=0, n_pairs_required=int(min_pairs),
                    reports_per_pair_required=float(min_reports_per_pair),
                    span_left_mA=0.0, span_right_mA=0.0,
                    span_required_mA=float(min_span_mA), passes=False)
    g = (d.assign(amp_mA_Left=pd.to_numeric(d["amp_mA_Left"], errors="coerce").round(3),
                 amp_mA_Right=pd.to_numeric(d["amp_mA_Right"], errors="coerce").round(3),
                 n=pd.to_numeric(d["n"], errors="coerce").fillna(0.0))
           .groupby(["amp_mA_Left", "amp_mA_Right"])["n"].sum().reset_index())
    qual = g.loc[g["n"] >= float(min_reports_per_pair)]
    n_pairs = int(len(qual))
    span_left = float(qual["amp_mA_Left"].max() - qual["amp_mA_Left"].min()) if n_pairs else 0.0
    span_right = float(qual["amp_mA_Right"].max() - qual["amp_mA_Right"].min()) if n_pairs else 0.0
    passes = bool(n_pairs >= int(min_pairs) and span_left >= float(min_span_mA)
                 and span_right >= float(min_span_mA))
    return dict(n_pairs=n_pairs, n_pairs_required=int(min_pairs),
               reports_per_pair_required=float(min_reports_per_pair),
               span_left_mA=span_left, span_right_mA=span_right,
               span_required_mA=float(min_span_mA), passes=passes)


def _rate_stratum_resolution(rs: "RateStratum", joint_stratum: JointStratum, *,
                             resolution_k: float = RESOLUTION_K) -> dict:
    """The three-part honest-current check for one :class:`RateStratum`. Returns a dict with
    ``resolved`` and the three sub-checks (``flat``, ``gain``, ``coverage``), each carrying its
    own numbers, plus one plain-language ``sentence``.

    The gain check (ii) is read against ``joint_stratum``'s OWN incumbent prediction
    (``incumbent_mu``/``incumbent_sd``/``incumbent_rate_supported``) -- the 3-input model's
    already-extrapolation-aware statement of whether comparing against the incumbent means
    anything at all for this pulse-width pair -- but the CANDIDATE side of that comparison is
    this rate's own, never-borrowed ``mu_star``/``sd_star``. That is the fix: the question of
    whether a comparison against the incumbent is even meaningful stays where it always was; the
    number being compared is no longer allowed to be drawn from other rates.
    """
    if rs.safe is not None and np.asarray(rs.safe).any():
        mu_safe = np.asarray(rs.mu)[np.asarray(rs.safe)]
        sd_safe = np.asarray(rs.sd)[np.asarray(rs.safe)]
        rng = float(np.nanmax(mu_safe) - np.nanmin(mu_safe))
        med_sd = float(np.nanmedian(sd_safe))
        flat_passes = bool(np.isfinite(rng) and np.isfinite(med_sd) and med_sd > 0
                           and rng > float(resolution_k) * med_sd)
    else:
        rng, med_sd, flat_passes = float("nan"), float("nan"), False
    flat = dict(range=rng, median_sd=med_sd, passes=flat_passes)

    if not joint_stratum.incumbent_rate_supported:
        gain = dict(gain=float("nan"), sd_diff=float("nan"), passes=None)
    else:
        g = float(joint_stratum.incumbent_mu) - float(rs.mu_star)
        sdd = float(np.sqrt(float(rs.sd_star) ** 2 + float(joint_stratum.incumbent_sd) ** 2))
        g_passes = bool(np.isfinite(sdd) and sdd > 0 and g > float(resolution_k) * sdd)
        gain = dict(gain=g, sd_diff=sdd, passes=g_passes)

    coverage = dict(rs.coverage or {})
    resolved = bool(flat["passes"] and gain["passes"] is True and coverage.get("passes"))

    reasons = []
    if not flat["passes"]:
        if not (rs.safe is not None and np.asarray(rs.safe).any()):
            reasons.append("no current combination at this rate clears the safety model")
        else:
            reasons.append(f"the fitted surface varies by {rng:.3f} across the whole grid against "
                           f"a typical uncertainty of {med_sd:.3f}")
    if gain["passes"] is None:
        reasons.append("this pulse-width pair never ran the setting currently in force, so there "
                       "is nothing to compare a gain against")
    elif not gain["passes"]:
        reasons.append(f"the best cell's predicted improvement, {gain['gain']:+.3f}, does not "
                       f"clear the uncertainty in that difference, {gain['sd_diff']:.3f}")
    if not coverage.get("passes"):
        reasons.append(
            f"only {coverage.get('n_pairs', 0)} current combination(s) have been tried with at "
            f"least {coverage.get('reports_per_pair_required', CURRENT_COVERAGE_MIN_REPORTS_PER_PAIR):g} "
            f"reports each (need {coverage.get('n_pairs_required', CURRENT_COVERAGE_MIN_PAIRS)}), "
            f"spanning {coverage.get('span_left_mA', 0.0):.2f} mA on the left and "
            f"{coverage.get('span_right_mA', 0.0):.2f} mA on the right (need "
            f"{coverage.get('span_required_mA', CURRENT_COVERAGE_MIN_SPAN_MA):g} mA on each)")
    if resolved:
        sentence = (f"a current can be recommended at {rs.rate_hz:g} Hz: the fitted surface "
                    f"varies by {rng:.3f} against a typical uncertainty of {med_sd:.3f}, "
                    f"{coverage.get('n_pairs', 0)} current combinations have been tried with "
                    f"enough spread, and the best cell beats the setting in force by "
                    f"{gain['gain']:+.3f} against an uncertainty of {gain['sd_diff']:.3f}")
    else:
        sentence = (f"no current can be recommended from this record at {rs.rate_hz:g} Hz: "
                    + "; and ".join(reasons))
    return dict(resolved=resolved, flat=flat, gain=gain, coverage=coverage, sentence=sentence)


def _fit_rate_stratum(pwl, pwr, rate, sub, *, amp_grid, sgp_left, sgp_right,
                      fixed_length_scale, beta) -> RateStratum:
    """Fit ONE (amplitude-Left, amplitude-Right) surface at a single rate. ``sub`` is already
    restricted to this (pulse-width pair, rate); the caller has already checked it clears
    ``RATE_STRATUM_MIN_EPOCHS``. ``sgp_left``/``sgp_right`` are the SAME shared, per-side safety
    models the enclosing :class:`JointStratum` fit was given -- one safety model per side, fitted
    once on the whole record, unchanged by this per-rate split."""
    grid = SUR.JointParameterGrid([rate], amp_grid, amp_grid)
    Xobs = sub[["freq_hz", "amp_mA_Left", "amp_mA_Right"]].to_numpy(float)
    gp = SUR.ObjectiveGP(grid, fixed_length_scale=fixed_length_scale, random_state=0).fit(
        Xobs, sub["J"].to_numpy(float), sub["obs_var"].to_numpy(float))
    mu, sd = gp.predict_grid()
    gx = grid.grid_X()
    safe = (np.asarray(sgp_left.safe_mask(X=gx[:, [0, 1]], beta=beta), bool)
            & np.asarray(sgp_right.safe_mask(X=gx[:, [0, 2]], beta=beta), bool))
    n_reports = np.zeros(len(grid))
    np.add.at(n_reports, grid.index_of(Xobs), sub["n"].to_numpy(float))
    i_star = int(np.argmin(np.where(safe, mu, np.inf)))
    coverage = current_coverage(sub)
    # The individual observed epochs behind this rate's own surface (2026-09-14, for the Stim
    # Optimizer page's own heatmap): one point per row of `sub`, carrying the two currents, how
    # many reports it rests on, the objective value the fit actually regressed, and which epoch it
    # came from. Not a grid cell -- the raw evidence a reader can overlay ON the grid.
    points = [dict(amp_left_mA=float(r["amp_mA_Left"]), amp_right_mA=float(r["amp_mA_Right"]),
                   n_reports=float(r["n"]), J=float(r["J"]), epoch=float(r["epoch"]))
             for _, r in sub.iterrows()]
    return RateStratum(
        pw_us_left=float(pwl), pw_us_right=float(pwr), rate_hz=float(rate),
        n_epochs=int(len(sub)), fitted=True,
        grid=grid, gp=gp,
        mu=grid.as_surface(mu)[0], sd=grid.as_surface(sd)[0],
        safe=grid.as_surface(safe.astype(float))[0] > 0,
        n_reports=grid.as_surface(n_reports)[0],
        x_star=(float(gx[i_star, 1]), float(gx[i_star, 2])),
        mu_star=float(mu[i_star]), sd_star=float(sd[i_star]),
        n_reports_total=float(sub["n"].sum()), coverage=coverage,
        meta=dict(kernel=gp.hyperparameters["kernel"], n_safe=int(safe.sum()), points=points))


def _pooled_slice_at_rate(sl: JointStratum, rate_hz: float) -> dict:
    """What the 3-input, POOLED-ACROSS-RATES surface says at ``rate_hz``, for reference only. This
    is never used to choose or resolve a current (see :class:`RateStratum`'s docstring) -- it is
    reported beside the honest per-rate surface so a reader can see exactly what the pooled model
    would have claimed and how it differs."""
    fi = int(np.argmin(np.abs(sl.grid.freqs - float(rate_hz))))
    mu3 = sl.grid.as_surface(sl.mu)[fi]
    safe3 = sl.grid.as_surface(sl.safe.astype(float))[fi] > 0
    rng = float(np.nanmax(mu3[safe3]) - np.nanmin(mu3[safe3])) if safe3.any() else float("nan")
    delivered = float(rate_hz) in set(np.round(np.asarray(sl.meta["rates_delivered"], float), 6))
    note = ("this rate was directly delivered on the pooled surface too, but the pooled surface "
            "still borrows its precision from every other rate through the shared, pinned rate "
            "axis; for reference only, not used for the recommendation" if delivered else
            "this rate's slice of the pooled surface is BORROWED from other rates through the "
            "shared, pinned rate axis; for reference only, not used for the recommendation")
    return dict(mu_range=rng, delivered_at_this_rate=bool(delivered), note=note)


def _fit_joint_stratum(pwl, pwr, sub, *, grid, sgp_left, sgp_right, incumbent_xyz,
                       fixed_length_scale, kappa, q, eta, beta, constraint=None) -> JointStratum:
    """Fit the joint 3-D surrogate to one (pulse-width-Left, pulse-width-Right) stratum.

    ``sgp_left``/``sgp_right`` are the SHARED, PER-SIDE safety models, each fitted once on the
    whole record (see the module docstring for why the safety model stays per side while the
    objective surface is joint). The joint safe set at a grid cell is "safe on the Left's own
    (rate, amp_Left) view of it AND safe on the Right's own (rate, amp_Right) view of it" —
    computed by handing each 2-D ``SafetyGP`` the matching two columns of the 3-D grid, which
    ``SafetyGP.safe_mask``'s own ``X=`` argument already supports with no change to that class.
    """
    Xobs = sub[["freq_hz", "amp_mA_Left", "amp_mA_Right"]].to_numpy(float)
    gp = SUR.ObjectiveGP(grid, fixed_length_scale=fixed_length_scale, random_state=0).fit(
        Xobs, sub["J"].to_numpy(float), sub["obs_var"].to_numpy(float))
    mu, sd = gp.predict_grid()

    n_reports = np.zeros(len(grid))
    np.add.at(n_reports, grid.index_of(Xobs), sub["n"].to_numpy(float))

    inc_mu, inc_sd = gp.predict(np.atleast_2d(incumbent_xyz), return_std=True)
    incumbent_mu, incumbent_sd = float(inc_mu[0]), float(inc_sd[0])
    gx = grid.grid_X()

    safe_left = sgp_left.safe_mask(X=gx[:, [0, 1]], beta=beta)
    safe_right = sgp_right.safe_mask(X=gx[:, [0, 2]], beta=beta)
    safe = np.asarray(safe_left, bool) & np.asarray(safe_right, bool)

    constrained = bool(constraint is not None and not constraint.lifted)
    if constrained:
        allowed = safe & ENV.grid_mask(grid, min_rate_hz=constraint.min_rate_hz)
    else:
        allowed = safe
    i_star_unc = int(np.argmin(np.where(safe, mu, np.inf)))
    envelope_empty = bool(constrained and not allowed.any())
    i_star = i_star_unc if envelope_empty else int(np.argmin(np.where(allowed, mu, np.inf)))

    queue, qmeta = ACQ.exploration_queue(mu, sd, n_reports, incumbent_mu, kappa=kappa)
    if constrained and queue.size:
        queue = queue[allowed[queue]]
    stopping = ACQ.check_stopping([], mu, sd, n_reports, incumbent_mu=incumbent_mu)
    try:
        batch = ACQ.select_batch_within_visit_joint(gp, grid, q=int(q), safe_mask=allowed,
                                                     n_reports=n_reports,
                                                     incumbent_mu=incumbent_mu, eta=eta)
    except ValueError as exc:
        batch = []
        batch_note = f"no within-visit batch available: {exc}"
    else:
        batch_note = ""

    rates = set(np.round(sub["freq_hz"].astype(float).to_numpy(), 6))
    inc_supported = bool(round(float(incumbent_xyz[0]), 6) in rates)
    opt_supported = bool(round(float(gx[i_star, 0]), 6) in rates)

    return JointStratum(
        pw_us_left=float(pwl), pw_us_right=float(pwr), n_epochs=int(len(sub)),
        grid=grid, gp=gp, mu=mu, sd=sd, safe=safe, i_star=i_star,
        x_star=(float(gx[i_star, 0]), float(gx[i_star, 1]), float(gx[i_star, 2])),
        mu_star=float(mu[i_star]), sd_star=float(sd[i_star]),
        incumbent_mu=incumbent_mu, incumbent_sd=incumbent_sd,
        n_reports=n_reports, queue=queue, stopping=stopping, batch=batch,
        incumbent_rate_supported=inc_supported, optimum_rate_supported=opt_supported,
        allowed=allowed, i_star_unconstrained=i_star_unc,
        x_star_unconstrained=(float(gx[i_star_unc, 0]), float(gx[i_star_unc, 1]),
                              float(gx[i_star_unc, 2])),
        mu_star_unconstrained=float(mu[i_star_unc]),
        envelope_empty=envelope_empty, envelope_constrained=constrained,
        meta=dict(kernel=gp.hyperparameters["kernel"],
                  log_marginal_likelihood=gp.hyperparameters["log_marginal_likelihood"],
                  n_reports_total=float(sub["n"].sum()),
                  rates_delivered=[float(v) for v in sorted(sub["freq_hz"].unique())],
                  amp_left_min=float(sub["amp_mA_Left"].min()),
                  amp_left_max=float(sub["amp_mA_Left"].max()),
                  amp_right_min=float(sub["amp_mA_Right"].min()),
                  amp_right_max=float(sub["amp_mA_Right"].max()),
                  n_safe=int(safe.sum()), n_allowed=int(allowed.sum()),
                  queue_size=int(queue.size),
                  best_optimistic_unexplored=float(qmeta.get("best_optimistic", float("nan"))),
                  batch_note=batch_note))


# ---------------------------------------------------------------------------------------------
# The stage runner
# ---------------------------------------------------------------------------------------------
@dataclass
class Stage1Result:
    """Everything Stage 1 produced, plus the frozen configuration it hands to the gate."""

    frozen: FrozenConfiguration
    slices: dict                           # dict[(pw_us_left, pw_us_right)] -> JointStratum
    summary: pd.DataFrame
    audit: dict
    D: pd.DataFrame
    skipped: dict = field(default_factory=dict)
    #: One row per (pulse-width pair, rate) that was even ATTEMPTED (2026-09-14): whether a
    #: per-rate surface was fitted, its resolution verdict and numbers when it was, and the
    #: POOLED 3-input model's own slice at that rate for reference -- see
    #: ``JointStratum.rate_strata`` and ``_pooled_slice_at_rate``. Empty when nothing was fitted
    #: at all.
    rate_summary: pd.DataFrame = field(default_factory=pd.DataFrame)

    def slices_for(self, hemisphere: str) -> list:
        """Every fitted joint stratum. Kept for callers written against the pre-joint API: since
        both hemispheres now come from the SAME set of joint strata, the argument no longer
        narrows the result and is accepted for compatibility only."""
        return list(self.slices.values())


def run_stage1(design_csv, *, hemispheres=("Left", "Right"), primary_item="left_leg",
              pw_col=None, freq_grid=PLT.FREQ_GRID, amp_grid=JOINT_AMP_GRID,
              fixed_length_scale=JOINT_FIXED_LENGTH_SCALE, beta=PLT.BETA, kappa=PLT.KAPPA,
              min_tolerated_h=MIN_TOLERATED_H,
              min_stratum_epochs=PW_STRATUM_MIN_EPOCHS, q=4, eta=1.0,
              incumbent_epoch=None, data_horizon=PLT.DATA_HORIZON, washin_min=PLT.WASHIN_MIN,
              resolution_k=RESOLUTION_K,
              explore_outside_reason=None, explore_outside_by=None,
              explore_outside_requested=None,
              adaptive_min_rate_hz=ENV.MIN_RATE_HZ,
              safety_ceiling_by_hemisphere=None, pooled_var_override=None) -> Stage1Result:
    """Run the open-loop search JOINTLY over both stimulators and freeze one configuration.

    Parameters
    ----------
    design_csv
        Epoch-level design matrix (path or DataFrame), as ``routines/objective.build_objective``
        requires, plus ``amp_mA_Left``, ``amp_mA_Right``, ``pw_us_Left`` and ``pw_us_Right``.
        Unlike the pre-joint version of this function, BOTH currents are always part of the fit —
        there is no longer a "fit the Left side only" mode that ignores the Right side's current,
        because that is exactly the confound this redesign removes. ``hemispheres`` still controls
        which side(s) get a :class:`HemisphereSetting` in the returned configuration; it no longer
        controls what gets modelled.
    fixed_length_scale
        Per-axis length-scale pinning for the joint 3-D surrogate, ``(rate, amp_Left, amp_Right)``.
        ``None`` (the default) pins the rate axis only (matching the pre-joint module's own
        reasoning: the frequency length scale is not identifiable from this design) and leaves both
        amplitude axes free to be fitted independently, since each current's own dose-response
        should be free to have its own smoothness.
    pw_col
        Column holding pulse width. ``None`` (the default) means EACH SIDE'S OWN column,
        ``pw_us_<side>``; when a side's own column is absent, ``pw_us_Left`` is used for it and the
        audit says so.
    min_stratum_epochs
        A (pulse-width-Left, pulse-width-Right) PAIR with fewer fitted epochs than this is SKIPPED,
        with its reason recorded in ``.skipped``, never silently pooled into a neighbouring pair.
    incumbent_epoch
        Defaults to the most recent epoch in the matrix, which is the setting currently in force.
        ``J`` is referenced to it, so every stratum shares one scale.
    explore_outside_reason, explore_outside_by, explore_outside_requested
        The adaptive envelope (``routines/adaptive_envelope.py``) is applied to the ONE shared rate
        axis before scoring, so the frozen rate is at or above the device's adaptive minimum. A
        NON-EMPTY ``explore_outside_reason`` lifts the constraint; see ``routines/adaptive_envelope``.
    safety_ceiling_by_hemisphere
        ``{hemisphere: (ceiling_mA, provenance)}`` from ``safety_ceiling.ceilings_by_hemisphere``:
        the current above which each side is not acceptable, stated by the PI, the severity-3 seed
        of that side's OWN safety model (still fitted per side; see the module docstring).
    pooled_var_override
        Passed straight to ``objective.build_objective``; see its own docstring. ``None`` (the
        default) is the original behaviour. Exists for a thin, independent design matrix (e.g. the
        clinic-sheet pain stream, ``StimOptimizer.clinic_pain``) that has no epoch with enough
        repeats to estimate its own pooled variance.

    Returns
    -------
    Stage1Result
        ``.frozen`` is the :class:`FrozenConfiguration` the gate reads, with one
        :class:`HemisphereSetting` per requested side, both derived from the SAME joint fit;
        ``.slices`` holds one :class:`JointStratum` per fitted (pulse-width-Left,
        pulse-width-Right) pair; ``.summary`` is one row per (hemisphere, joint stratum) — two rows
        per fitted stratum, the per-side VIEW of one joint result, kept in that shape so existing
        readers of the strata table need no change.
    """
    es = pd.read_csv(design_csv) if not isinstance(design_csv, pd.DataFrame) else design_csv.copy()
    if incumbent_epoch is None:
        if "t0" not in es.columns:
            raise KeyError("cannot derive the incumbent without a 't0' column; pass "
                           "incumbent_epoch explicitly")
        incumbent_epoch = float(es.sort_values("t0")["epoch"].iloc[-1])
    if float(incumbent_epoch) not in set(es["epoch"].astype(float)):
        raise ValueError(f"incumbent_epoch {incumbent_epoch} is not in this design matrix "
                         f"(epochs {es['epoch'].min():g}-{es['epoch'].max():g})")

    for col in ("amp_mA_Left", "amp_mA_Right"):
        if col not in es.columns:
            raise KeyError(f"design matrix has no {col!r} column; a joint fit needs both "
                           "currents on every row")

    # ONE objective build, ONE incumbent, so J is on a single scale across every stratum below.
    D = OBJ.build_objective(es, incumbent_epoch=float(incumbent_epoch),
                            cfg={"primary_item": primary_item} if primary_item else None,
                            pooled_var_override=pooled_var_override)
    inc_row = D.loc[D["epoch"].astype(float) == float(incumbent_epoch)].iloc[0]
    inc_rate = float(inc_row["freq_hz"])
    inc_amp_left = float(inc_row["amp_mA_Left"])
    inc_amp_right = float(inc_row["amp_mA_Right"])
    incumbent_xyz = (inc_rate, inc_amp_left, inc_amp_right)
    # The LEFT column's value, kept under the historical name for the callers that read it.
    inc_pw = float(inc_row["pw_us_Left"]) if "pw_us_Left" in D.columns else None
    resolved_item = str(D["primary_item"].iloc[0]) if "primary_item" in D.columns else primary_item

    pwl_col, pwl_fallback = ("pw_us_Left", False) if pw_col is None else (str(pw_col), False)
    if pw_col is None and "pw_us_Right" in D.columns:
        pwr_col, pwr_fallback = "pw_us_Right", False
    elif pw_col is None:
        pwr_col, pwr_fallback = "pw_us_Left", True
    else:
        pwr_col, pwr_fallback = str(pw_col), False
    inc_pw_left = (float(inc_row[pwl_col]) if pwl_col in D.columns
                  and np.isfinite(float(inc_row[pwl_col])) else None)
    inc_pw_right = (float(inc_row[pwr_col]) if pwr_col in D.columns
                   and np.isfinite(float(inc_row[pwr_col])) else None)
    inc_pw_by_side = {"Left": inc_pw_left, "Right": inc_pw_right}

    grid = SUR.JointParameterGrid(freq_grid, amp_grid, amp_grid)
    gx = grid.grid_X()
    safety_grid = SUR.ParameterGrid(freq_grid, amp_grid)

    # The adaptive envelope, built ONCE on the one shared rate axis.
    constraint = ENV.make_constraint(reason=explore_outside_reason, by=explore_outside_by,
                                     requested=explore_outside_requested,
                                     min_rate_hz=adaptive_min_rate_hz)
    grid_rates_excluded = ([] if constraint.lifted
                           else ENV.rates_excluded_from_grid(grid, min_rate_hz=constraint.min_rate_hz))

    # --- the two PER-SIDE safety models, each fitted once on the whole record --------------------
    sgp_by_side, safety_meta_by_side = {}, {}
    for hemi in ("Left", "Right"):
        amp_col = f"amp_mA_{hemi}"
        ceiling_h = (safety_ceiling_by_hemisphere or {}).get(hemi)
        Xs, sev, sv, seed_meta = SC.safety_seed(D, amp_col, freq_grid=freq_grid,
                                                ceiling=ceiling_h, min_tolerated_h=min_tolerated_h)
        sgp = SUR.SafetyGP(safety_grid, random_state=0).fit(Xs, sev, sv)
        sgp_by_side[hemi] = sgp
        safety_meta_by_side[hemi] = seed_meta

    # --- feasible epochs enter the joint fit. Unlike the pre-joint per-hemisphere fit, an epoch is
    # NOT excluded for having either current at 0 mA: 0 mA is a real point on that current's own
    # axis in a grid that already spans both currents together, and dropping it would throw away
    # exactly the asymmetric-dosing epochs (44 of 120 on RCS08) that let a joint fit tell the two
    # currents' effects apart in the first place.
    fit = D.loc[D["feasible"]].copy()
    # An explicitly-named pw_col that is not on this matrix at all (a caller asking about a
    # column that does not exist, as opposed to the None-default fallback above) means nothing
    # can be stratified: NOT OBSERVED, not a crash.
    pw_cols_present = [c for c in (pwl_col, pwr_col) if c in fit.columns]
    fit = fit.dropna(subset=["freq_hz", "amp_mA_Left", "amp_mA_Right", *pw_cols_present])
    if pwl_col not in fit.columns or pwr_col not in fit.columns:
        fit = fit.iloc[0:0]

    h_audit = {}
    for hemi, col in (("Left", pwl_col), ("Right", pwr_col)):
        h_audit[hemi] = dict(
            amp_delivered_min=float(D[f"amp_mA_{hemi}"].min()) if len(D) else float("nan"),
            amp_delivered_max=float(D[f"amp_mA_{hemi}"].max()) if len(D) else float("nan"),
            pw_col=str(col), pw_col_fallback=bool(pwr_fallback if hemi == "Right" else pwl_fallback),
            incumbent_pw_us=inc_pw_by_side[hemi],
            safety_ceiling=dict(safety_meta_by_side[hemi]))

    audit = dict(incumbent_epoch=float(incumbent_epoch), incumbent_rate_hz=inc_rate,
                 incumbent_pw_us=inc_pw, incumbent_pw_us_by_side=dict(inc_pw_by_side),
                 pw_col=("own" if pw_col is None else str(pw_col)),
                 n_epochs_eligible=int(len(fit)), per_hemisphere=h_audit)
    if len(fit):
        audit["design"] = pulse_width_pair_design_audit(fit, pwl_col=pwl_col, pwr_col=pwr_col,
                                                        min_epochs=min_stratum_epochs)

    # --- fit one 3-D surface per adequately-sampled joint pulse-width pair ------------------------
    slices, rows, skipped = {}, [], {}
    if len(fit):
        groups = [((float(pwl), float(pwr)), sub) for (pwl, pwr), sub
                 in fit.groupby([fit[pwl_col].astype(float), fit[pwr_col].astype(float)])]
    else:
        groups = []
    for (pwl, pwr), sub in groups:
        key = (pwl, pwr)
        if len(sub) < int(min_stratum_epochs):
            skipped[f"pwL{pwl:g}_pwR{pwr:g}"] = (
                f"{len(sub)} fitted epochs at (Left {pwl:g} us, Right {pwr:g} us), below the "
                f"{int(min_stratum_epochs)}-epoch floor for a three-dimensional surface")
            continue
        try:
            sl = _fit_joint_stratum(pwl, pwr, sub, grid=grid, sgp_left=sgp_by_side["Left"],
                                    sgp_right=sgp_by_side["Right"], incumbent_xyz=incumbent_xyz,
                                    fixed_length_scale=fixed_length_scale, kappa=kappa, q=q,
                                    eta=eta, beta=beta, constraint=constraint)
        except (ValueError, RuntimeError) as exc:
            skipped[f"pwL{pwl:g}_pwR{pwr:g}"] = f"{type(exc).__name__}: {exc}"
            continue
        # --- PER-RATE 2-input surfaces (2026-09-14): the honest current-recommendation engine.
        # Every rate this stratum actually delivered gets its own (amp_Left, amp_Right) fit when
        # it clears RATE_STRATUM_MIN_EPOCHS; a thinner rate is recorded as not fitted, never
        # silently pooled into a neighbour, exactly the discipline the pulse-width strata
        # themselves already use.
        rate_strata = {}
        for rate, subr in sub.groupby("freq_hz"):
            rate = float(rate)
            n_r = int(len(subr))
            if n_r < int(RATE_STRATUM_MIN_EPOCHS):
                rate_strata[rate] = RateStratum(
                    pw_us_left=float(pwl), pw_us_right=float(pwr), rate_hz=rate,
                    n_epochs=n_r, fitted=False,
                    reason=f"{n_r} epochs, below the {int(RATE_STRATUM_MIN_EPOCHS)}-epoch floor")
                continue
            try:
                rs = _fit_rate_stratum(pwl, pwr, rate, subr, amp_grid=amp_grid,
                                       sgp_left=sgp_by_side["Left"], sgp_right=sgp_by_side["Right"],
                                       fixed_length_scale=fixed_length_scale, beta=beta)
            except (ValueError, RuntimeError) as exc:
                rate_strata[rate] = RateStratum(
                    pw_us_left=float(pwl), pw_us_right=float(pwr), rate_hz=rate,
                    n_epochs=n_r, fitted=False, reason=f"{type(exc).__name__}: {exc}")
                continue
            rs.resolution = _rate_stratum_resolution(rs, sl, resolution_k=resolution_k)
            rate_strata[rate] = rs
        sl.rate_strata = rate_strata

        slices[key] = sl
        rows.append(dict(
            pw_us_left=pwl, pw_us_right=pwr, n_epochs=sl.n_epochs,
            n_reports=sl.meta["n_reports_total"],
            opt_rate_hz=sl.x_star[0], opt_amp_mA_left=sl.x_star[1], opt_amp_mA_right=sl.x_star[2],
            opt_posterior_mean=sl.mu_star, opt_posterior_sd=sl.sd_star,
            incumbent_mu=sl.incumbent_mu, incumbent_sd=sl.incumbent_sd,
            gain=sl.gain_over_incumbent(), sd_of_difference=sl.sd_of_difference(),
            optimum_resolved=sl.resolves_its_optimum(resolution_k),
            incumbent_rate_supported=sl.incumbent_rate_supported,
            optimum_rate_supported=sl.optimum_rate_supported,
            n_safe=sl.meta["n_safe"], queue_size=sl.meta["queue_size"],
            stop=bool(sl.stopping.stop), stop_binding=sl.stopping.binding,
            kernel=sl.meta["kernel"],
            adaptive_envelope_applied=bool(sl.envelope_constrained),
            opt_rate_hz_unconstrained=sl.x_star_unconstrained[0],
            opt_amp_mA_left_unconstrained=sl.x_star_unconstrained[1],
            opt_amp_mA_right_unconstrained=sl.x_star_unconstrained[2],
            opt_posterior_mean_unconstrained=sl.mu_star_unconstrained,
            optimum_moved_by_envelope=bool(sl.optimum_moved_by_envelope),
            no_safe_cell_in_envelope=bool(sl.envelope_empty),
            n_allowed=sl.meta["n_allowed"]))

    audit["n_epochs_in_fitted_strata"] = int(sum(s.n_epochs for s in slices.values()))

    settings, exclusions_by_side = _freeze_joint(
        slices, inc_rate, inc_pw_by_side, h_audit=h_audit, gx=gx, resolution_k=resolution_k,
        constraint=constraint, min_stratum_epochs=min_stratum_epochs, hemispheres=hemispheres)

    envelope = dict(
        constrained=not constraint.lifted,
        min_rate_hz=float(constraint.min_rate_hz),
        max_rate_hz=ENV.MAX_RATE_HZ, max_pw_us=ENV.MAX_PW_US,
        statement=constraint.statement(),
        override=(dict(reason=constraint.reason, by=constraint.by) if constraint.lifted else None),
        override_ignored=constraint.ignored_note,
        grid_rates_excluded=list(grid_rates_excluded),
        grid_rates_excluded_reason=(
            ", ".join(ENV.exclusion_reason(r, min_rate_hz=constraint.min_rate_hz)
                      for r in grid_rates_excluded)
            if grid_rates_excluded else None),
        exclusions=exclusions_by_side,
        # The joint exclusion list is duplicated under both side keys (one joint decision,
        # reported per side for the frontend's per-side chart); counted once, not twice.
        n_exclusions=len(exclusions_by_side.get("Left", [])),
        source=ENV.SOURCE,
    )
    audit["adaptive_envelope"] = dict(envelope)

    frozen = FrozenConfiguration(
        settings=tuple(settings), primary_item=resolved_item,
        incumbent_epoch=float(incumbent_epoch), incumbent_rate_hz=inc_rate, incumbent_pw_us=inc_pw,
        data_horizon=str(data_horizon), washin_min=float(washin_min),
        n_epochs_total=int(len(D)), audit=audit, adaptive_envelope=envelope,
        incumbent_pw_us_by_side=dict(inc_pw_by_side))

    # --- the strata table: one row per (hemisphere, joint stratum), a per-side VIEW of one joint
    # fit, so every existing reader of the "strata" table (DecisionStrip.js, ExcludedSettingsChart.js)
    # needs no change in shape, only in what one more field (`pw_us_left`/`pw_us_right`, both always
    # present now) lets a reader group by.
    summary_rows = []
    for hemi in ("Left", "Right"):
        for r in rows:
            row = dict(r)
            row["hemisphere"] = hemi
            row["pw_us"] = row["pw_us_left"] if hemi == "Left" else row["pw_us_right"]
            row["opt_amp_mA"] = row["opt_amp_mA_left"] if hemi == "Left" else row["opt_amp_mA_right"]
            row["opt_amp_mA_unconstrained"] = (row["opt_amp_mA_left_unconstrained"] if hemi == "Left"
                                               else row["opt_amp_mA_right_unconstrained"])
            row["joint_stratum_key"] = f"{row['pw_us_left']:g}_{row['pw_us_right']:g}"
            summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)

    # --- the per-rate table (2026-09-14): one row per (pulse-width pair, rate) that was even
    # attempted, fitted or not, with the pooled 3-input model's own slice at that rate alongside
    # it for reference. See ``JointStratum.rate_strata``.
    rate_rows = []
    for (pwl, pwr), sl in slices.items():
        for rate, rs in (sl.rate_strata or {}).items():
            pooled = _pooled_slice_at_rate(sl, rate)
            row = dict(pw_us_left=float(pwl), pw_us_right=float(pwr), rate_hz=float(rate),
                       fitted=bool(rs.fitted), n_epochs=int(rs.n_epochs),
                       pooled_across_rates_mu_range=pooled["mu_range"],
                       pooled_across_rates_delivered_at_this_rate=pooled["delivered_at_this_rate"],
                       pooled_across_rates_note=pooled["note"])
            if rs.fitted:
                res = rs.resolution or {}
                row.update(
                    n_reports=float(rs.n_reports_total),
                    amp_mA_left=rs.x_star[0], amp_mA_right=rs.x_star[1],
                    posterior_mean=rs.mu_star, posterior_sd=rs.sd_star,
                    resolved=bool(res.get("resolved")),
                    flat_range=res.get("flat", {}).get("range"),
                    flat_median_sd=res.get("flat", {}).get("median_sd"),
                    flat_passes=res.get("flat", {}).get("passes"),
                    gain=res.get("gain", {}).get("gain"),
                    gain_sd_of_difference=res.get("gain", {}).get("sd_diff"),
                    gain_passes=res.get("gain", {}).get("passes"),
                    coverage_n_pairs=res.get("coverage", {}).get("n_pairs"),
                    coverage_span_left_mA=res.get("coverage", {}).get("span_left_mA"),
                    coverage_span_right_mA=res.get("coverage", {}).get("span_right_mA"),
                    coverage_passes=res.get("coverage", {}).get("passes"),
                    sentence=res.get("sentence"), reason=None)
            else:
                row.update(n_reports=float("nan"), amp_mA_left=float("nan"),
                          amp_mA_right=float("nan"), posterior_mean=float("nan"),
                          posterior_sd=float("nan"), resolved=False, flat_range=float("nan"),
                          flat_median_sd=float("nan"), flat_passes=None, gain=float("nan"),
                          gain_sd_of_difference=float("nan"), gain_passes=None,
                          coverage_n_pairs=0, coverage_span_left_mA=float("nan"),
                          coverage_span_right_mA=float("nan"), coverage_passes=False,
                          sentence=None, reason=str(rs.reason))
            rate_rows.append(row)
    rate_summary = pd.DataFrame(rate_rows)

    return Stage1Result(frozen=frozen, slices=slices, summary=summary, audit=audit,
                        D=D, skipped=skipped, rate_summary=rate_summary)


def _freeze_joint(slices: dict, inc_rate, inc_pw_by_side: dict, *, h_audit, gx, resolution_k,
                  constraint, min_stratum_epochs, hemispheres) -> tuple:
    """Pick ONE joint stratum (rate, pulse-width-Left, pulse-width-Right, amp-Left, amp-Right) and
    state whether it is resolved. Returns ``(settings, exclusions_by_side)``.

    There is exactly ONE freeze decision now, not one per side: the device has one rate knob, and
    the joint fit already prices in both currents' effect on pain at once, so there is nothing left
    to freeze independently per side except the pulse width and the preferred current, which stay
    genuinely per-side because they are independently programmable.
    """
    all_strata = list(slices.values())
    min_rate = float(constraint.min_rate_hz) if constraint is not None else ENV.MIN_RATE_HZ
    constrained = bool(constraint is not None and not constraint.lifted)
    exclusions = []

    usable = all_strata
    if constrained:
        usable = []
        for s in all_strata:
            if s.envelope_empty:
                exclusions.append(dict(
                    kind="stratum",
                    what=(f"the (Left {s.pw_us_left:g} us, Right {s.pw_us_right:g} us) stratum, "
                          f"whose unconstrained optimum is {s.x_star_unconstrained[0]:g} Hz at "
                          f"{s.x_star_unconstrained[1]:.2f} / {s.x_star_unconstrained[2]:.2f} mA "
                          f"(posterior mean {s.mu_star_unconstrained:+.4f})"),
                    reason=(f"no safe cell on this stratum has a rate at or above the "
                            f"{min_rate:g} Hz adaptive minimum, so it cannot recommend a setting "
                            "the closed-loop mode can use"),
                    pw_us_left=float(s.pw_us_left), pw_us_right=float(s.pw_us_right),
                    unconstrained_rate_hz=float(s.x_star_unconstrained[0]),
                    unconstrained_amp_mA_left=float(s.x_star_unconstrained[1]),
                    unconstrained_amp_mA_right=float(s.x_star_unconstrained[2]),
                    unconstrained_posterior_mean=float(s.mu_star_unconstrained)))
                continue
            if s.optimum_moved_by_envelope:
                exclusions.append(dict(
                    kind="cell",
                    what=(f"{s.x_star_unconstrained[0]:g} Hz at "
                          f"{s.x_star_unconstrained[1]:.2f} / {s.x_star_unconstrained[2]:.2f} mA "
                          f"on the (Left {s.pw_us_left:g} us, Right {s.pw_us_right:g} us) stratum "
                          f"(posterior mean {s.mu_star_unconstrained:+.4f}), which the "
                          f"unconstrained search would have preferred; the best in-envelope cell "
                          f"on this stratum is {s.x_star[0]:g} Hz at "
                          f"{s.x_star[1]:.2f} / {s.x_star[2]:.2f} mA (posterior mean "
                          f"{s.mu_star:+.4f})"),
                    reason=ENV.exclusion_reason(s.x_star_unconstrained[0], min_rate_hz=min_rate),
                    pw_us_left=float(s.pw_us_left), pw_us_right=float(s.pw_us_right),
                    unconstrained_rate_hz=float(s.x_star_unconstrained[0]),
                    unconstrained_amp_mA_left=float(s.x_star_unconstrained[1]),
                    unconstrained_amp_mA_right=float(s.x_star_unconstrained[2]),
                    unconstrained_posterior_mean=float(s.mu_star_unconstrained),
                    constrained_rate_hz=float(s.x_star[0]),
                    constrained_amp_mA_left=float(s.x_star[1]),
                    constrained_amp_mA_right=float(s.x_star[2]),
                    constrained_posterior_mean=float(s.mu_star)))
            usable.append(s)

    # The exclusion list is one joint list; the frontend's per-side chart wants it keyed by side,
    # so it is duplicated under both keys with this side's own amplitude surfaced under the
    # generic `*_amp_mA` names the chart reads.
    exclusions_by_side = {}
    for hemi, idx in (("Left", 1), ("Right", 2)):
        view = []
        for x in exclusions:
            v = dict(x)
            v["unconstrained_amp_mA"] = x.get(f"unconstrained_amp_mA_{'left' if idx == 1 else 'right'}")
            if "constrained_amp_mA_left" in x:
                v["constrained_amp_mA"] = x.get(f"constrained_amp_mA_{'left' if idx == 1 else 'right'}")
            v["pw_us"] = x.get(f"pw_us_{'left' if idx == 1 else 'right'}")
            view.append(v)
        exclusions_by_side[hemi] = view

    def _no_setting(hemi, reason_text):
        return HemisphereSetting(
            hemisphere=hemi, rate_hz=float("nan"), pw_us=None, amp_star_mA=float("nan"),
            amp_delivered_min_mA=h_audit.get(hemi, {}).get("amp_delivered_min", float("nan")),
            amp_delivered_max_mA=h_audit.get(hemi, {}).get("amp_delivered_max", float("nan")),
            n_epochs_fitted=0, rate_resolved=None, pw_resolved=None,
            reasons=(reason_text,), detail=dict(n_slices=0))

    if not all_strata:
        settings = [_no_setting(h, "no (pulse-width-Left, pulse-width-Right) pair had enough "
                                  "fitted epochs to support a joint surface, so nothing was "
                                  "searched at all; the setting in force is carried forward as a "
                                  "default, not as a choice") for h in hemispheres]
        return settings, exclusions_by_side

    if not usable:
        excluded_pairs = ", ".join(f"(Left {s.pw_us_left:g}, Right {s.pw_us_right:g}) us"
                                   for s in all_strata)
        reason = (f"NO ADAPTIVE-CAPABLE SETTING CAN BE RECOMMENDED FROM THIS RECORD: "
                 f"{len(all_strata)} joint pulse-width strata were fitted ({excluded_pairs}) and "
                 f"none has a safe cell at or above the {min_rate:g} Hz adaptive minimum. What "
                 "each would have recommended without the constraint is listed under the "
                 "exclusions. A rate is deliberately not carried forward: recommending one the "
                 "closed-loop mode cannot use is what the constraint exists to prevent")
        settings = [HemisphereSetting(
            hemisphere=h, rate_hz=float("nan"), pw_us=None, amp_star_mA=float("nan"),
            amp_delivered_min_mA=h_audit.get(h, {}).get("amp_delivered_min", float("nan")),
            amp_delivered_max_mA=h_audit.get(h, {}).get("amp_delivered_max", float("nan")),
            n_epochs_fitted=int(sum(s.n_epochs for s in all_strata)),
            rate_resolved=None, pw_resolved=None, reasons=(reason,),
            detail=dict(n_slices=0, n_slices_fitted=len(all_strata),
                        adaptive_envelope=dict(constrained=True, min_rate_hz=min_rate,
                                               no_adaptive_capable_setting=True,
                                               n_excluded=len(exclusions))))
                   for h in hemispheres]
        return settings, exclusions_by_side

    best = min(usable, key=lambda s: s.mu_star)
    rate_resolved = best.resolves_its_optimum(resolution_k)
    gain = best.gain_over_incumbent()
    sd_diff = best.sd_of_difference()
    chosen_rate = float(best.x_star[0])

    # --- THE HONEST CURRENT RECOMMENDATION (2026-09-14). The rate and the pulse-width pair are
    # still chosen from the POOLED 3-input surface above -- that choice needs to pool across
    # rates to have any data to choose from at all. But the CURRENT itself is read from the
    # PER-RATE 2-input surface at the chosen rate, never from the pooled surface's own optimum,
    # because that is exactly what let a flat, borrowed surface recommend a current that was
    # noise (module docstring, "WHY THE SEARCH IS NOW JOINT"). A current is only handed back when
    # that rate's own surface clears all three checks in ``_rate_stratum_resolution``; otherwise
    # ``amp_star_mA`` is NaN and the reason names which check failed.
    rate_strata_here = best.rate_strata or {}
    rs_chosen = next((v for k, v in rate_strata_here.items() if abs(k - chosen_rate) < 1e-6), None)
    if rs_chosen is not None and rs_chosen.fitted and (rs_chosen.resolution or {}).get("resolved"):
        amp_left_current, amp_right_current = rs_chosen.x_star
        current_ok = True
        current_reason = f"CURRENT: {rs_chosen.resolution['sentence']}"
        current_resolution = dict(rs_chosen.resolution)
    else:
        amp_left_current = amp_right_current = float("nan")
        current_ok = False
        if rs_chosen is None:
            current_reason = (
                f"CURRENT: no current can be recommended at {chosen_rate:g} Hz: this rate was "
                f"never delivered at the chosen pulse-width pair (Left {best.pw_us_left:g} us, "
                f"Right {best.pw_us_right:g} us), so there is no rate-specific surface to read a "
                "current from")
            current_resolution = dict(resolved=False, sentence=current_reason)
        elif not rs_chosen.fitted:
            current_reason = (f"CURRENT: no current can be recommended at {chosen_rate:g} Hz: "
                              f"{rs_chosen.reason}")
            current_resolution = dict(resolved=False, sentence=current_reason,
                                      reason=rs_chosen.reason)
        else:
            current_reason = f"CURRENT: {rs_chosen.resolution['sentence']}"
            current_resolution = dict(rs_chosen.resolution)

    reasons = []
    if rate_resolved is None:
        reasons.append(
            f"the rate choice is NOT ASSESSED, not refused: the chosen joint stratum "
            f"(Left {best.pw_us_left:g} us, Right {best.pw_us_right:g} us) never delivered the "
            f"rate in force ({inc_rate:g} Hz) — it ran "
            f"{', '.join(f'{r:g}' for r in best.meta['rates_delivered'])} Hz — so its posterior "
            f"at the incumbent cell ({best.incumbent_mu:+.4f}, SD {best.incumbent_sd:.4f}) is an "
            "extrapolation across a PINNED frequency length scale, not a measurement. J is zero "
            "at the incumbent by construction, so any gain computed against that extrapolation "
            "is an artefact of the stratification and is discarded rather than reported")
    elif not rate_resolved:
        if abs(best.x_star[0] - inc_rate) < 1e-9:
            reasons.append(
                f"the chosen rate {best.x_star[0]:g} Hz is the rate already in force. Retaining "
                "the setting in force is not the same as having resolved it: the gain over the "
                "incumbent is zero by construction, so the resolution criterion cannot be met and "
                "the rate is carried forward as an unresolved default")
        else:
            reasons.append(
                f"the rate move {inc_rate:g} -> {best.x_star[0]:g} Hz is NOT resolved: the "
                f"posterior gain over the setting in force is {gain:+.4f} NRS points against a "
                f"standard deviation of that difference of {sd_diff:.4f}, so the difference is "
                "smaller than the uncertainty in the difference")
    else:
        reasons.append(
            f"the rate move {inc_rate:g} -> {best.x_star[0]:g} Hz IS resolved: gain {gain:+.4f} "
            f"NRS points against difference SD {sd_diff:.4f}, from the JOINT fit over both "
            "currents at once")

    if not best.optimum_rate_supported:
        reasons.append(
            f"the chosen rate {best.x_star[0]:g} Hz was never delivered at this pulse-width pair "
            f"in this record (that stratum ran "
            f"{', '.join(f'{r:g}' for r in best.meta['rates_delivered'])} Hz), so the proposal is "
            "an interpolation across the PINNED frequency length scale rather than a rate the "
            "surface has observed at this pulse-width pair")

    # --- pulse width: a JOINT pair contrast, against the incumbent's own pair when it was fitted --
    inc_pwl, inc_pwr = inc_pw_by_side.get("Left"), inc_pw_by_side.get("Right")
    incumbent_stratum = None
    if inc_pwl is not None and inc_pwr is not None:
        for s in usable:
            if abs(s.pw_us_left - inc_pwl) < 1e-9 and abs(s.pw_us_right - inc_pwr) < 1e-9:
                incumbent_stratum = s
                break

    if len(usable) < 2:
        pw_resolved = False
        reasons.append(
            f"only one joint pulse-width pair (Left {best.pw_us_left:g} us, Right "
            f"{best.pw_us_right:g} us) had enough fitted epochs to support a surface, so no "
            "pulse-width comparison was possible and the pulse widths are carried forward "
            "unresolved")
    elif incumbent_stratum is None:
        pw_resolved = None
        reasons.append(
            "the pulse-width choice is NOT ASSESSED, not refused: the (pulse-width-Left, "
            "pulse-width-Right) pair in force has no fitted joint stratum of its own, so there is "
            "no surface to compare the chosen pair against")
    elif incumbent_stratum is best:
        pw_resolved = False
        reasons.append(
            f"the best stratum IS the pulse-width pair in force (Left {best.pw_us_left:g} us, "
            f"Right {best.pw_us_right:g} us); there is nothing to resolve against and it is "
            "carried forward as an unresolved default")
    elif round(float(best.x_star[0]), 6) not in set(
            np.round(np.asarray(incumbent_stratum.meta["rates_delivered"], float), 6)):
        pw_resolved = None
        reasons.append(
            f"the pulse-width-pair contrast is NOT ASSESSED: the reference stratum (Left "
            f"{incumbent_stratum.pw_us_left:g} us, Right {incumbent_stratum.pw_us_right:g} us) "
            f"never delivered the chosen rate {best.x_star[0]:g} Hz, so a contrast at that cell "
            "would compare a measurement against an extrapolation")
    else:
        cell = np.atleast_2d(np.asarray(best.x_star, float))
        a_mu, a_sd = incumbent_stratum.gp.predict(cell, return_std=True)
        pw_gain = float(a_mu[0]) - float(best.mu_star)
        pw_sd_diff = float(np.sqrt(float(best.sd_star) ** 2 + float(a_sd[0]) ** 2))
        pw_resolved = bool(np.isfinite(pw_sd_diff) and pw_sd_diff > 0
                           and pw_gain > float(resolution_k) * pw_sd_diff)
        verdict = "IS" if pw_resolved else "is NOT"
        reasons.append(
            f"the pulse-width-pair move (Left {incumbent_stratum.pw_us_left:g}, Right "
            f"{incumbent_stratum.pw_us_right:g}) -> (Left {best.pw_us_left:g}, Right "
            f"{best.pw_us_right:g}) us {verdict} resolved at the chosen cell "
            f"({best.x_star[0]:g} Hz, {best.x_star[1]:.2f} / {best.x_star[2]:.2f} mA): posterior "
            f"gain {pw_gain:+.4f} NRS points against difference SD {pw_sd_diff:.4f}")

    # --- the adaptive envelope, said on the setting itself -----------------------------------
    chosen_rate = float(best.x_star[0])
    in_env = ENV.rate_in_envelope(chosen_rate, min_rate_hz=min_rate)
    env_detail = dict(constrained=constrained, min_rate_hz=min_rate,
                      chosen_rate_in_envelope=bool(in_env), n_excluded=len(exclusions),
                      n_strata_excluded_whole=sum(1 for x in exclusions if x["kind"] == "stratum"),
                      n_strata_usable=len(usable))
    if constrained:
        moved = [x for x in exclusions if x["kind"] == "cell"
                and abs(x["pw_us_left"] - best.pw_us_left) < 1e-9
                and abs(x["pw_us_right"] - best.pw_us_right) < 1e-9]
        if moved:
            x = moved[0]
            reasons.append(
                f"ADAPTIVE ENVELOPE: without the constraint this stratum would have recommended "
                f"{x['unconstrained_rate_hz']:g} Hz at "
                f"{x['unconstrained_amp_mA_left']:.2f} / {x['unconstrained_amp_mA_right']:.2f} "
                f"mA (posterior mean {x['unconstrained_posterior_mean']:+.4f}); "
                f"{x['reason']}. The recommendation is the best in-envelope cell instead: "
                f"{chosen_rate:g} Hz at {best.x_star[1]:.2f} / {best.x_star[2]:.2f} mA "
                f"(posterior mean {best.mu_star:+.4f})")
            env_detail["unconstrained_optimum"] = dict(
                rate_hz=x["unconstrained_rate_hz"], amp_mA_left=x["unconstrained_amp_mA_left"],
                amp_mA_right=x["unconstrained_amp_mA_right"],
                posterior_mean=x["unconstrained_posterior_mean"],
                pw_us_left=x["pw_us_left"], pw_us_right=x["pw_us_right"])
        elif exclusions:
            reasons.append(
                f"ADAPTIVE ENVELOPE: the chosen rate {chosen_rate:g} Hz is at or above the "
                f"{min_rate:g} Hz adaptive minimum; {len(exclusions)} exclusion(s) are listed "
                "under the frozen configuration")
        else:
            reasons.append(
                f"ADAPTIVE ENVELOPE: the chosen rate {chosen_rate:g} Hz is at or above the "
                f"{min_rate:g} Hz adaptive minimum and the constraint excluded nothing")
    elif constraint is not None and constraint.lifted and not in_env:
        who = f" by {constraint.by}" if constraint.by else ""
        reasons.append(
            f"OUTSIDE THE ADAPTIVE ENVELOPE: the chosen rate {chosen_rate:g} Hz is below the "
            f"{min_rate:g} Hz adaptive minimum and the closed-loop mode cannot be programmed with "
            f"it. It is recommended only because the constraint was lifted{who} for the stated "
            f"reason: {constraint.reason}")
        env_detail["override"] = dict(reason=constraint.reason, by=constraint.by)

    # The current recommendation's own honesty check (computed above, just after `best` was
    # chosen) is appended last, and a rate choice that was otherwise resolved is DOWNGRADED to
    # unresolved when the current cannot be: freezing a rate move with no idea what current to
    # run it at is not a configuration Stage 2 should ever receive. `False` -> `False` and
    # `None` -> `None` are left alone; only `True` -> `False` changes, and only for that reason.
    reasons.append(current_reason)
    rate_resolved_effective = (False if rate_resolved is True and not current_ok else rate_resolved)

    reasons_t = tuple(reasons)
    settings = []
    for hemi in hemispheres:
        pw_this = best.pw_us_left if hemi == "Left" else best.pw_us_right
        amp_this = float(amp_left_current if hemi == "Left" else amp_right_current)
        detail = dict(n_slices=len(usable), best_pw_us_left=float(best.pw_us_left),
                     best_pw_us_right=float(best.pw_us_right),
                     incumbent_pw_us_left=inc_pwl, incumbent_pw_us_right=inc_pwr,
                     adaptive_envelope=dict(env_detail),
                     current_resolution=dict(current_resolution))
        detail["adaptive_envelope"]["brainsense_pair"] = ENV.brainsense_pair_demonstrated(
            chosen_rate, pw_this, hemi)
        settings.append(HemisphereSetting(
            hemisphere=hemi, rate_hz=chosen_rate, pw_us=float(pw_this), amp_star_mA=amp_this,
            amp_delivered_min_mA=h_audit.get(hemi, {}).get("amp_delivered_min", float("nan")),
            amp_delivered_max_mA=h_audit.get(hemi, {}).get("amp_delivered_max", float("nan")),
            n_epochs_fitted=int(best.n_epochs), rate_resolved=rate_resolved_effective,
            pw_resolved=pw_resolved, gain=float(gain), sd_of_difference=float(sd_diff),
            reasons=reasons_t, detail=detail))
    return settings, exclusions_by_side
