"""Stage 2 of the two-stage architecture: the CLOSED-LOOP search over a control policy.

WHAT CHANGES BETWEEN THE STAGES
-------------------------------
Stage 1 chose a setting. Stage 2 does not choose a setting at all — it chooses a CONTROL POLICY, and
the device then moves amplitude within that policy in response to a sensed LFP band. The free
parameters are therefore completely different from Stage 1's, and the parameters Stage 1 searched
are no longer free:

    frozen by the device once BrainSense is configured   rate, pulse width
    searched here                                        threshold mode; sensed band centre and
                                                         width; the threshold value(s); the
                                                         adaptive amplitude limits and the paused
                                                         amplitude

"Pulse width and rate cannot be adjusted once BrainSense has been set up for either hemisphere"
(A610 Clinician Programming Guide, pp. 34-35, recorded verbatim in ``routines/percept_adaptive``).
That is why the frozen configuration arrives here as an INPUT and is enforced as one in three
separate ways rather than merely documented. :class:`~StimOptimizer.stage1_openloop.
FrozenConfiguration` is a frozen dataclass, so assignment to it raises ``FrozenInstanceError``.
:func:`run_stage2` refuses a caller-supplied ``rate_hz`` or ``pw_us`` outright instead of accepting
and ignoring it. And every policy this module emits reads its rate and pulse width off the frozen
configuration rather than from any argument, so there is no path by which a proposal can carry a
rate the clinician did not freeze.

REJECT, NEVER CLIP
------------------
Every candidate goes through ``percept_adaptive.validate_policy`` and a candidate with any problem
is DISCARDED, with its problems recorded. It is never repaired by clipping a value into range. This
is a deliberate choice and it is the opposite of what a numerical optimizer usually does. Clipping
turns "this policy is not programmable" into "here is a nearby policy", and a nearby policy is a
different clinical proposal that nobody evaluated: clipping a 6 Hz band centre up to 10.5 Hz to fit
the adaptive range substitutes a different control signal, and clipping an amplitude ceiling down to
the declared limit silently discards the reason the higher ceiling was proposed. A rejection with
its reason attached is information; a clipped value is a fabrication wearing the shape of a result.

WHY THE RANKING IS NOT AN EFFICACY RANKING
------------------------------------------
Stage 1 ranks candidates by a pain objective because pain outcomes exist for open-loop settings in
this record. No closed-loop pain outcome exists for anyone here — the loop has never been run — so
there is nothing to fit a surrogate to and no honest way to predict which valid policy relieves more
pain. Stage 2 therefore ranks the valid policies by DEPLOYABILITY, using the device's own criterion
for whether a threshold can be placed at all: the standardised separation between the two LFP
captures, from ``routines/lfp_response.assess_response``. A better-separated band is one where the
device can put a threshold the signal reliably crosses in both directions. That is a necessary
condition for the loop to function and it is not a claim about benefit. The distinction is stated in
:attr:`Stage2Result.ranking_basis` and in every summary this module produces, because a ranked table
invites being read as a preference ordering and this one is not.

Typical use::

    from StimOptimizer import stage1_openloop as S1, stage2_closedloop as S2
    from StimOptimizer.routines import stage_gate as GATE

    s1 = S1.run_stage1("rcs08_bo_design_matrix.csv", data_horizon="2026-08-12")
    gate = GATE.evaluate_gate(s1.frozen)                 # no LFP evidence -> will refuse
    s2 = S2.run_stage2(s1.frozen, gate)
    print(s2.describe())
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .routines import lfp_response as LFP
from .routines import percept_adaptive as PA
from .routines import stage_gate as GATE

#: Threshold modes Stage 2 will consider. ``SINGLE_INVERSE`` is deliberately absent from the default
#: because it is available only in a Sensing Only configuration and cannot drive therapy at all
#: (white paper p. 15). It is still accepted if a caller passes it explicitly, and it is then
#: rejected by ``validate_policy`` with that reason attached — which is more useful than pretending
#: the mode does not exist.
DEFAULT_MODES = (PA.DUAL, PA.SINGLE)

#: Sensed-band widths considered, in Hz. Ours, not the device's: the labelling fixes the permitted
#: RANGE (8-30 Hz) and leaves the width a configuration choice. Three widths are swept because the
#: device's band power is a SUM over the bins in the band, so the width changes the numeric scale of
#: the threshold as well as the signal's bandwidth.
DEFAULT_BAND_WIDTHS_HZ = (4.0, 5.0, 6.0)

#: Half-widths, in mA, of the narrower adaptive amplitude windows tried around the amplitude Stage 1
#: preferred, in addition to the full delivered envelope. A narrow window gives the loop less
#: authority and less room to help; a wide one gives it more of both. Both are offered rather than
#: one being chosen here, because that trade-off is a clinical judgement.
DEFAULT_AMP_WINDOW_HALF_WIDTHS_MA = (0.5, 1.0)


@dataclass(frozen=True)
class ClosedLoopPolicy:
    """One candidate closed-loop control policy, with its frozen inheritance made explicit.

    Frozen, like the configuration it inherits from, so a caller cannot adjust a validated policy
    into an unvalidated one. ``rate_hz`` and ``pw_us`` are carried on the policy for the sole
    purpose of being handed to ``validate_policy``, which needs the rate to check the adaptive
    minimum. They are copies of the frozen configuration's values and are never search variables
    here.
    """

    hemisphere: str
    mode: str
    center_hz: float
    band_width_hz: float
    amp_min_mA: float
    amp_max_mA: float
    paused_amp_mA: float
    rate_hz: float
    pw_us: float | None
    threshold_lower: float | None = None
    threshold_upper: float | None = None
    threshold_single: float | None = None
    thresholds_determined: bool = False
    lfp_responds_to_stimulation: bool = False
    sensing_hemisphere: str | None = None
    n_neurostimulators: int = 1
    evidence: dict = field(default_factory=dict)

    @property
    def band_hz(self) -> tuple:
        return (self.center_hz - self.band_width_hz / 2.0,
                self.center_hz + self.band_width_hz / 2.0)

    def as_device_policy(self) -> dict:
        """The mapping ``percept_adaptive.validate_policy`` expects.

        ``lfp_responds_to_stimulation`` is passed through as measured and is never asserted here.
        ``validate_policy`` treats anything other than ``True`` as a problem, which means a policy
        whose control signal has not been shown to move with amplitude cannot be accepted — the
        behaviour this module wants, so it is left alone rather than worked around.
        """
        return dict(mode=self.mode, center_hz=float(self.center_hz),
                    band_width_hz=float(self.band_width_hz),
                    amp_min_mA=float(self.amp_min_mA), amp_max_mA=float(self.amp_max_mA),
                    paused_amp_mA=float(self.paused_amp_mA), rate_hz=float(self.rate_hz),
                    hemisphere=self.hemisphere, sensing_hemisphere=self.sensing_hemisphere,
                    n_neurostimulators=int(self.n_neurostimulators),
                    lfp_responds_to_stimulation=bool(self.lfp_responds_to_stimulation))

    def problems(self) -> list:
        """Device-constraint problems with this policy. Empty means nothing objects."""
        return PA.validate_policy(self.as_device_policy())

    def is_valid(self) -> bool:
        return not self.problems()


@dataclass
class Stage2Result:
    """What Stage 2 concluded, including the case where it never started.

    ``started`` is ``False`` whenever the gate refused. That is a legitimate terminal answer and not
    an error: on this project's current data it is the expected one, and the refusal reasons carry
    more information than any policy table would.
    """

    started: bool
    frozen: object
    gate: object
    policies: pd.DataFrame
    rejected: pd.DataFrame
    refusal_reasons: list = field(default_factory=list)
    ranking_basis: str = ""
    ranking_assessed: bool | None = None
    notes: list = field(default_factory=list)

    @property
    def n_valid(self) -> int:
        return int(len(self.policies))

    def best(self, hemisphere=None):
        """Top-ranked VALID policy row, or ``None`` when there is none.

        Ranked by deployability, never by predicted benefit — see :attr:`ranking_basis`.
        """
        if self.policies.empty:
            return None
        p = self.policies
        if hemisphere is not None:
            p = p.loc[p["hemisphere"] == hemisphere]
            if p.empty:
                return None
        return p.iloc[0]

    def describe(self) -> str:
        if not self.started:
            lines = ["STAGE 2 DID NOT START — the stage gate refused. Named reasons:"]
            lines += [f"  - {n}: {d}" for n, d in self.refusal_reasons]
            lines.append("This is a terminal answer, not a failure: rate and pulse width freeze "
                         "when BrainSense is configured, so configuring it on an unlicensed "
                         "Stage 1 result would foreclose the open-loop search for nothing.")
            return "\n".join(lines)
        lines = [f"STAGE 2 ran: {self.n_valid} valid policies of "
                 f"{self.n_valid + len(self.rejected)} enumerated.",
                 f"Ranking basis: {self.ranking_basis}"]
        if self.ranking_assessed is not True:
            lines.append("Ranking is NOT ASSESSED: the policies are reported as a valid set with "
                         "no order.")
        for n in self.notes:
            lines.append(f"  note: {n}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# Candidate enumeration
# ---------------------------------------------------------------------------------------------
def _amp_windows(setting, *, half_widths, ceiling_mA) -> list:
    """Candidate ``(min_mA, max_mA)`` adaptive limit pairs for one hemisphere.

    Always bounded by the DELIVERED envelope on that hemisphere and by the declared ceiling. The
    envelope bound is not a formality: this record establishes that amplitude does not predict
    side-effect severity, and only 5 of the 417 non-procedural rows with stimulation on sit above
    4 mA, so amplitudes above what was delivered are UNKNOWN rather than safe. A pair that would
    fall outside the envelope is dropped here rather than clipped into it.
    """
    lo_env = float(setting.amp_delivered_min_mA)
    hi_env = min(float(setting.amp_delivered_max_mA), float(ceiling_mA))
    if not (np.isfinite(lo_env) and np.isfinite(hi_env)):
        return []
    out = []
    if hi_env > lo_env:
        out.append((lo_env, hi_env))
    star = float(setting.amp_star_mA)
    if np.isfinite(star):
        for hw in half_widths:
            lo, hi = star - float(hw), star + float(hw)
            if lo >= lo_env - 1e-9 and hi <= hi_env + 1e-9 and hi > lo:
                out.append((round(lo, 3), round(hi, 3)))
    # Order-preserving de-duplication, so the full envelope stays first.
    seen, uniq = set(), []
    for pair in out:
        k = (round(pair[0], 6), round(pair[1], 6))
        if k not in seen:
            seen.add(k)
            uniq.append(pair)
    return uniq


def _thresholds_for(mode, response) -> dict:
    """Threshold fields for one mode, given an LFP-response result, or all ``None``.

    The two modes place thresholds by different mechanisms and the difference is not ours to
    smooth over. In Dual Threshold mode the clinician sets an upper and a lower threshold manually,
    so the two LFP captures are the natural pair. In Single Threshold mode the clinician sets
    NOTHING: the device computes ``0.75 * (upper - lower) + lower`` from the two captures (white
    paper p. 15). A Single-mode policy must therefore PREDICT the threshold the device will produce
    rather than propose one, which is what ``lfp_response`` already computed by mirroring the same
    procedure, so its value is used here rather than recomputed.
    """
    if response is None or response.responds is not True:
        return dict(threshold_lower=None, threshold_upper=None, threshold_single=None,
                    thresholds_determined=False)
    lo, hi = sorted((float(response.power_low), float(response.power_high)))
    if mode == PA.SINGLE:
        return dict(threshold_lower=None, threshold_upper=None,
                    threshold_single=float(response.derived_threshold),
                    thresholds_determined=True)
    return dict(threshold_lower=lo, threshold_upper=hi, threshold_single=None,
                thresholds_determined=True)


def enumerate_candidates(frozen, *, lfp=None, hemispheres=None, modes=DEFAULT_MODES,
                         band_centers=GATE.DEFAULT_BAND_CENTERS_HZ,
                         band_widths=DEFAULT_BAND_WIDTHS_HZ,
                         amp_window_half_widths=DEFAULT_AMP_WINDOW_HALF_WIDTHS_MA,
                         ceiling_mA=GATE.AMP_CEILING_MA, contralateral=False,
                         n_neurostimulators=1, min_sep_d=LFP.MIN_CAPTURE_SEPARATION_D):
    """Build the closed-loop candidate set and split it into valid and rejected.

    Every candidate is checked with ``percept_adaptive.validate_policy`` and nothing is clipped: a
    candidate with problems goes to the rejected list carrying them. Rate and pulse width are read
    off ``frozen`` and are not parameters of this function.

    ``lfp`` is a :class:`~StimOptimizer.routines.stage_gate.LfpEvidence` or ``None``. With ``None``,
    ``lfp_responds_to_stimulation`` stays ``False`` on every candidate and ``validate_policy``
    rejects all of them, naming the unmeasured response. That is the correct behaviour and not a
    degenerate case to special-case away: a control signal that has not been shown to move with
    amplitude gives the loop no authority.

    Returns ``(accepted, rejected)``, both lists. ``accepted`` holds
    :class:`ClosedLoopPolicy` objects; ``rejected`` holds ``(policy, problems)`` pairs.
    """
    hemis = tuple(frozen.hemispheres) if hemispheres is None else tuple(hemispheres)
    accepted, rejected = [], []
    # Response verdicts are cached per (band centre, width) because assess_response fits a
    # regression and the same band is reused across every mode and amplitude window.
    resp_cache = {}

    for hemi in hemis:
        setting = frozen.setting(hemi)
        windows = _amp_windows(setting, half_widths=amp_window_half_widths, ceiling_mA=ceiling_mA)
        for c in band_centers:
            for w in band_widths:
                key = (round(float(c), 6), round(float(w), 6))
                if key not in resp_cache:
                    r = None
                    if lfp is not None:
                        power = lfp.power_for(c, w)
                        if power is not None:
                            r = LFP.assess_response(power, lfp.amplitude_mA, era=lfp.era,
                                                    cluster=lfp.cluster,
                                                    mode_requires=lfp.mode_requires,
                                                    min_sep_d=min_sep_d)
                    resp_cache[key] = r
                response = resp_cache[key]
                responds = bool(response is not None and response.responds is True)
                for mode in modes:
                    thr = _thresholds_for(mode, response)
                    for lo, hi in windows:
                        pol = ClosedLoopPolicy(
                            hemisphere=hemi, mode=mode, center_hz=float(c),
                            band_width_hz=float(w), amp_min_mA=float(lo), amp_max_mA=float(hi),
                            # The device's "Paused" amplitude must lie inside the adaptive limits.
                            # The lower limit is used because a pause should not deliver more than
                            # the loop's own floor.
                            paused_amp_mA=float(lo),
                            rate_hz=float(setting.rate_hz), pw_us=setting.pw_us,
                            lfp_responds_to_stimulation=responds,
                            sensing_hemisphere=(None if contralateral else hemi),
                            n_neurostimulators=int(n_neurostimulators),
                            evidence=dict(
                                separation_d=(float(response.separation_d) if response is not None
                                              else float("nan")),
                                response_reason=(response.reason if response is not None
                                                 else "no LFP evidence supplied"),
                                slope_log_per_mA=(float(response.slope_log_per_mA)
                                                  if response is not None else float("nan")),
                                slope_p=(float(response.slope_p) if response is not None
                                         else float("nan"))),
                            **thr)
                        probs = pol.problems()
                        if probs:
                            rejected.append((pol, probs))
                        else:
                            accepted.append(pol)
    return accepted, rejected


def _policy_frame(policies) -> pd.DataFrame:
    rows = []
    for p in policies:
        lo, hi = p.band_hz
        rows.append(dict(
            hemisphere=p.hemisphere, mode=p.mode, center_hz=p.center_hz,
            band_width_hz=p.band_width_hz, band_lo_hz=lo, band_hi_hz=hi,
            amp_min_mA=p.amp_min_mA, amp_max_mA=p.amp_max_mA, paused_amp_mA=p.paused_amp_mA,
            rate_hz=p.rate_hz, pw_us=p.pw_us,
            threshold_lower=p.threshold_lower, threshold_upper=p.threshold_upper,
            threshold_single=p.threshold_single,
            thresholds_determined=p.thresholds_determined,
            separation_d=p.evidence.get("separation_d", float("nan")),
            slope_log_per_mA=p.evidence.get("slope_log_per_mA", float("nan")),
            slope_p=p.evidence.get("slope_p", float("nan"))))
    return pd.DataFrame(rows)


def _rejected_frame(rejected) -> pd.DataFrame:
    rows = []
    for p, probs in rejected:
        rows.append(dict(hemisphere=p.hemisphere, mode=p.mode, center_hz=p.center_hz,
                         band_width_hz=p.band_width_hz, amp_min_mA=p.amp_min_mA,
                         amp_max_mA=p.amp_max_mA, rate_hz=p.rate_hz,
                         n_problems=len(probs), problems=" | ".join(probs)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------
# The stage runner
# ---------------------------------------------------------------------------------------------
def run_stage2(frozen, gate, *, lfp=None, rate_hz=None, pw_us=None, allow_gate_failure=False,
               **candidate_kwargs) -> Stage2Result:
    """Configure the closed-loop search on a frozen configuration, or refuse and say why.

    Parameters
    ----------
    frozen
        A :class:`~StimOptimizer.stage1_openloop.FrozenConfiguration`. Read only.
    gate
        The :class:`~StimOptimizer.routines.stage_gate.GateResult` for that configuration. If it did
        not pass, Stage 2 returns immediately with ``started=False`` and the named refusals.
    lfp
        LFP evidence, passed through to :func:`enumerate_candidates`.
    rate_hz, pw_us
        Present ONLY to be refused. Rate and pulse width freeze when BrainSense is configured, so a
        caller asking Stage 2 to change either has misunderstood the sequencing, and accepting the
        argument and ignoring it would hide the misunderstanding. Passing anything other than
        ``None`` raises ``ValueError``.
    allow_gate_failure
        Escape hatch for testing the enumeration in isolation. It does NOT make a refused
        configuration deployable and it records itself in ``.notes``. Never set it in a clinical
        path.

    Returns
    -------
    Stage2Result
        ``started=False`` with ``refusal_reasons`` when the gate refused; otherwise the valid and
        rejected policy sets, ranked by deployability.
    """
    if rate_hz is not None or pw_us is not None:
        raise ValueError(
            "Stage 2 cannot set the stimulation rate or the pulse width. Both FREEZE when "
            "BrainSense is configured (A610 manual pp. 34-35: 'Pulse width and rate cannot be "
            "adjusted once BrainSense has been set up for either hemisphere'), and changing either "
            "one requires removing BrainSense from the group, which discards the closed-loop "
            f"configuration. Got rate_hz={rate_hz!r}, pw_us={pw_us!r}. The frozen configuration "
            f"carries rate "
            + ", ".join(f"{s.hemisphere} {s.rate_hz:g} Hz" for s in frozen.settings)
            + "; to change it, re-run Stage 1.")

    notes = []
    if not gate.passed and not allow_gate_failure:
        return Stage2Result(started=False, frozen=frozen, gate=gate,
                            policies=pd.DataFrame(), rejected=pd.DataFrame(),
                            refusal_reasons=list(gate.refusals()),
                            ranking_basis="not applicable: Stage 2 did not start",
                            ranking_assessed=None,
                            notes=["the gate refused; no policy was enumerated"])
    if not gate.passed:
        notes.append(
            "allow_gate_failure=True: the gate REFUSED this configuration and the enumeration ran "
            "anyway. Nothing below is deployable. Blocking conditions: "
            + "; ".join(n for n, _ in gate.refusals()))

    accepted, rejected = enumerate_candidates(frozen, lfp=lfp, **candidate_kwargs)
    pol = _policy_frame(accepted)
    rej = _rejected_frame(rejected)

    basis = ("capture separation d between the two LFP captures (routines/lfp_response), the "
             "device's own criterion for whether a threshold can be placed at all. This is a "
             "DEPLOYABILITY ordering and NOT an efficacy ordering: no closed-loop pain outcome "
             "exists for this patient, so no valid policy can be claimed to relieve more pain "
             "than another.")
    assessed = None
    if not pol.empty and pol["separation_d"].notna().any() and np.isfinite(
            pol["separation_d"].to_numpy(float)).any():
        pol = pol.sort_values(["separation_d", "amp_max_mA"], ascending=[False, True]
                              ).reset_index(drop=True)
        assessed = True
    elif not pol.empty:
        basis = ("NONE — no capture separation is available for any valid policy, so the set is "
                 "reported unordered.")
        notes.append("policies are unordered: no LFP capture separation was available to rank them")

    if pol.empty:
        notes.append("no candidate policy satisfied the device constraints; see .rejected for the "
                     "problems recorded against each")
    return Stage2Result(started=True, frozen=frozen, gate=gate, policies=pol, rejected=rej,
                        refusal_reasons=[], ranking_basis=basis, ranking_assessed=assessed,
                        notes=notes)
