"""Amplitude-response evidence built from WITHIN-VISIT clinic steps, not chronic exposure epochs.

WHY THIS EXISTS ALONGSIDE ``lfp_evidence.build_all``. That builder reads exposure epochs whose
amplitude is entangled with calendar time, so era blocking is the only defence against the
confound. On RCS08 that defence fails in both directions and for opposite reasons:

  * the FULL-RECORD window fails on capture DIRECTION in all 18 bands, because the two capture arms
    straddle two programming regimes and power therefore RISES across them; and
  * the FIVE-ERA window fails on capture SEPARATION in 14 of 18, because restricting to recent eras
    removes the low amplitudes and the contrast collapses from 2.9 mA to 1.0.

Inside one clinic visit the rate, pulse width and contacts are fixed and the whole amplitude ladder
happens within hours, so there is no time confound to adjust for. The measured within-visit span on
RCS08 reaches 3.5 mA, and the resulting capture separation runs 0.53 to 0.89 per cell rather than
0.41 to 0.93 — which is why separation stops being the binding constraint.

The output is deliberately the SAME shape ``lfp_evidence.build_all`` returns, a
``{(channel, hemisphere, rate): LfpEvidence}`` mapping plus an audit frame, so ``screen_cells`` and
the whole gate downstream of it run unchanged. Only the evidence source is swapped.

DEPENDENCY NOTE. Nothing here imports Biomarkers. The harmonic-landing flag that accompanies the
per-band scores needs ``Biomarkers.routines.analytics.harmonic_landings_hz`` and therefore lives in
``ClosedLoopDeployment.clinic_steps``, which already depends on both. Keeping the flag out of this
file is what lets StimOptimizer stay free of that import.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import stage_gate as GATE
from .lfp_evidence import EvidenceAudit

#: Seconds after a step's onset that are discarded as ramp transient.
#:
#: CHANGED FROM 45.0 TO 20.0 ON 2026-09-06, because the device's own amplitude record was read for
#: the first time and the 45 was five times too large for the band range the biomarker uses. The
#: two measurements behind the old and new figures ask DIFFERENT QUESTIONS and both are kept below,
#: because a reader who conflates them will put the wrong number back.
#:
#: WHAT THE OLD 45 WAS FOR. The clinic sheets warn that the amplitude ramps rather than stepping,
#: and an earlier ramp analysis measured the STIMULATION-FREQUENCY artefact -- the band containing
#: the stimulation rate itself -- still rising at 150 s. 45 s was the sheets' own figure, adopted
#: because a longer exclusion left almost no settled signal, with the residual risk recorded rather
#: than removed. That measurement is not superseded: nothing below says the stimulation-frequency
#: band settles quickly, and a caller working in that band should pass a longer ``ramp_s``.
#:
#: WHAT THE NEW 20 IS FOR, and how it was measured. On RCS08's 2026-08-18 clinic visit the
#: per-sample amplitude in ``BrainSenseLfp[].LfpData[].{Left,Right}.mA`` (2 Hz, on the same clock as
#: the neural signal) shows that each "step" on the sheet is a BURST of 4-5 small increments the
#: device delivers over a few seconds -- 0.5, 0.6, 0.7, 0.8, 1.0 -- followed by a hold. Across all
#: 27 steps on both stimulators the current finishes moving in 6.5 s median, 9.0 s at most on the
#: left and 17.5 s at most on the right. Holds are 57.5 s median. So 20 s covers the worst case
#: observed with a margin, and it is the smallest defensible figure rather than a comfortable one.
#:
#: AND WHY A SHORTER EXCLUSION IS NOT MERELY CHEAPER BUT BETTER. Aligning 1-second epochs to the
#: moment each ramp finished, across 15 left plateaus, band power in 8-30 Hz deviates from its own
#: settled level by 5-20% with NO monotonic decay and no difference between harmonic-contaminated
#: and clean bands -- there is no settling transient left to exclude. Meanwhile a single 1-second
#: epoch swings by about 100% as one standard deviation inside a stretch where the amplitude is not
#: changing at all. The noise is five times the transient, so what the analysis needs is MORE
#: settled seconds to average, not a wider guard band: the 45 kept 754 settled epochs where 0 s
#: keeps 1423. The two rules agree on the SIGN of the amplitude relationship in 22 of 23 bands, so
#: this change buys precision and does not buy a different answer -- which is also why it is safe.
#:
#: Tables: RCS08_20260818_device_amplitude_steps.csv, RCS08_20260818_settling_profile.csv.
RAMP_EXCLUDE_S = 20.0

#: The longest ramp actually observed in the device's own amplitude record, in seconds. Kept as a
#: named number so that a future reader can see what ``RAMP_EXCLUDE_S`` above has to cover, and so
#: that a test can assert the exclusion is not smaller than the thing it exists to exclude.
LONGEST_OBSERVED_RAMP_S = 17.5

#: Ramp exclusion for a band containing the stimulation rate itself. NOT the default: see the block
#: above. The earlier measurement found that artefact still rising at 150 s, so no exclusion this
#: module offers makes such a band safe, and a caller who needs one should treat the band as
#: unusable rather than pass a larger number and believe the problem is handled.
STIM_FREQUENCY_BAND_UNSAFE_AT_ANY_EXCLUSION = True

#: Amplitude bin width for forming capture arms, in mA.
#:
#: A JUDGEMENT. The programmer steps finely while a capture arm needs rows: one RCS08 visit carried
#: 29 distinct amplitude levels across 36 steps, so grouping on the raw level leaves roughly one
#: step per level and no arm reaches ``lfp_response.MIN_ROWS_PER_ARM``. 0.5 mA is the coarsest
#: grouping that still separates clinically distinct settings.
AMP_ARM_BIN_MA = 0.5

#: Minimum settled tiles a step must contribute before its median is used. Two is the arithmetic
#: minimum for a median to mean anything, and it is deliberately low because the median RCS08 step
#: yields only about five settled tiles. The thinness is reported per step, not hidden.
MIN_SETTLED_TILES = 2


def amplitude_arm_bins(amp_mA, bin_mA=AMP_ARM_BIN_MA):
    """Amplitudes rounded to the declared arm bin. See :data:`AMP_ARM_BIN_MA` for why."""
    a = np.asarray(amp_mA, dtype=float)
    if not np.isfinite(bin_mA) or bin_mA <= 0:
        raise ValueError(f"bin_mA must be positive and finite, got {bin_mA}")
    return np.round(a / float(bin_mA)) * float(bin_mA)


#: Most changes of current a single ramp may contain before the block is refused as a recording in
#: which the amplitude never holds still. Measured 2026-09-06 across the whole RCS08 record: clinic
#: step ladders use a MEDIAN OF 4 increments per step and 35 at the very most (a 0-to-3.5 mA sweep
#: the device chose to deliver in 35 pieces over 75 s). The refused regime is two orders of
#: magnitude away -- a median of 494 changes per block, up to 5,139 -- so any threshold between
#: about 50 and 400 separates them cleanly and 100 is not a delicate choice.
MAX_INCREMENTS_PER_RAMP = 100


class ContinuousAmplitudeError(ValueError):
    """Raised when a block's current never holds still, so it has no ramps or plateaus.

    Deliberately an exception rather than an empty return. An empty frame is indistinguishable
    from "this block had no amplitude changes at all", and the two need different handling: the
    first means the caller pointed a step-ladder routine at an at-home recording, the second means
    the stimulation simply sat at one value. Callers that sweep many blocks should catch this and
    count it, which is what the all-sessions extraction now does.
    """


def ramp_windows_from_amplitude(amp_t, amp_mA, *, min_hold_s=20.0, burst_gap_s=10.0,
                                tol_mA=1e-9):
    """When did the device actually finish moving the current? Measured, not assumed.

    This replaces the visit sheet as the source of step timing. The sheet gives one hand-written
    time per setting and a printed warning that the ramp takes 30-45 s. The device's own record
    (``BrainSenseLfp[].LfpData[].{Left,Right}.mA``, 2 Hz, on the same clock as the neural signal)
    shows what really happens: a setting the sheet records as one step is a BURST of four or five
    small increments -- 0.5, 0.6, 0.7, 0.8, 1.0 -- delivered over a few seconds, then a hold. On
    RCS08's 2026-08-18 visit the current finishes moving in 6.5 s median and 9.0 s at most for an
    ordinary 0.5 mA step; the single 17.5 s case was a double-size 1.0 mA jump.

    A BURST IS ONE STEP. Consecutive changes closer together than ``burst_gap_s`` belong to the same
    ramp, and the plateau begins at the LAST of them. Treating each increment as its own step would
    turn one clinical setting into five, each with a few seconds of signal.

    WHY THERE IS NO AMPLITUDE-DEPENDENT MARGIN HERE, tested at the PI's request 2026-09-06. Ramp
    duration against the current stepped to gives r = +0.33, p = 0.108 -- not significant. It tracks
    how many increments the device chose (r = +0.69, p = 0.0001), not how high the current is. So a
    single flat margin after the measured ramp is what the data supports, and a per-amplitude rule
    would add complexity for about ten seconds at the low end.

    Returns a DataFrame with one row per plateau: ``ramp_start``, ``ramp_end``, ``ramp_s``,
    ``n_increments``, ``mA_from``, ``mA_to``, ``hold_s``, ``plateau_end``. Pass ``ramp_end`` as
    ``step_t0`` to :func:`step_settled_stats` so the exclusion runs from the measured end of the
    ramp rather than from a nominal onset.
    """
    t = np.asarray(amp_t, dtype=float)
    a = np.asarray(amp_mA, dtype=float)
    if t.shape != a.shape:
        raise ValueError(f"amp_t {t.shape} and amp_mA {a.shape} must match")
    ok = np.isfinite(t) & np.isfinite(a)
    t, a = t[ok], a[ok]
    if t.size and np.any(np.diff(t) < 0):
        order = np.argsort(t); t, a = t[order], a[order]
    if t.size < 2:
        return pd.DataFrame(columns=["ramp_start", "ramp_end", "ramp_s", "n_increments",
                                     "mA_from", "mA_to", "hold_s", "plateau_end"])
    ch = np.where(np.abs(np.diff(a)) > tol_mA)[0] + 1
    rows, i = [], 0
    # ------------------------------------------------------------------------------------------
    # REFUSE THE RECORDING WHERE THE AMPLITUDE NEVER HOLDS STILL. Found 2026-09-06 while auditing
    # this function against the whole record, and it is a defect of the burst rule above rather
    # than a property of the data.
    #
    # Two regimes are present in RCS08's record and they need different treatment. Of 600 blocks
    # with a moving amplitude, 583 are STEP LADDERS -- a median of 4 increments then a 57.5 s hold,
    # which is what this function is for. The other 17 are recordings in which the amplitude
    # changes almost continuously: a median of 494 changes per block, and in the worst case 5,139
    # changes across 615.6 s with only 3.85 s of hold at the end.
    #
    # Because every consecutive change there is closer together than ``burst_gap_s``, the burst
    # rule glues thousands of them into ONE block and reports it as a single 615-second "ramp".
    # That number is not wrong arithmetically, it is MEANINGLESS as a description -- there is no
    # ramp and no plateau in such a recording, and a caller that takes it at face value would
    # exclude ten minutes of signal to protect against a settling transient that has no defined
    # start. These blocks are at-home sessions rather than clinic ladders.
    #
    # So: say so and return nothing, rather than returning a description that reads as a ramp.
    # The ``min_hold_s`` filter already removed them in practice, which is why the 326-step
    # analysis was unaffected -- but it removed them silently and for the wrong reason.
    if ch.size > MAX_INCREMENTS_PER_RAMP:
        span = t[ch[-1]] - t[ch[0]] if ch.size > 1 else 0.0
        raise ContinuousAmplitudeError(
            f"the amplitude changes {ch.size} times over {span:.1f} s in this block, more than "
            f"the {MAX_INCREMENTS_PER_RAMP} allowed for a step ladder. This is a recording in "
            f"which the current never holds still, so it has no ramps and no plateaus to measure; "
            f"pass it to a routine written for continuously varying amplitude instead.")
    while i < ch.size:
        j = i
        while j + 1 < ch.size and (t[ch[j + 1]] - t[ch[j]]) <= burst_gap_s:
            j += 1
        ramp_start, ramp_end = t[ch[i]], t[ch[j]]
        nxt = t[ch[j + 1]] if j + 1 < ch.size else t[-1]
        hold = nxt - ramp_end
        if hold >= min_hold_s:
            rows.append(dict(ramp_start=float(ramp_start), ramp_end=float(ramp_end),
                             ramp_s=float(ramp_end - ramp_start), n_increments=int(j - i + 1),
                             mA_from=float(a[ch[i] - 1]), mA_to=float(a[ch[j]]),
                             hold_s=float(hold), plateau_end=float(nxt)))
        i = j + 1
    return pd.DataFrame(rows)


def amplitude_response_shape(amp_mA, power, *, min_points=8):
    """Does band power rise and then FALL across the currents tested, rather than run straight?

    WHY THIS EXISTS, and it is not a refinement. Every amplitude test in this project fits a
    straight line: the slope sign, the polarity rule, the two-point comparison. A relationship that
    rises to a peak inside the tested range and comes back down has a straight-line slope near zero,
    so all of those report "does not respond" -- while the response is in fact large. Measured on
    RCS08 ONE_THREE_LEFT, 2026-08-18, 55 Hz, 15 amplitude steps: on the eight bands from 23 to 30 Hz
    a straight line explains 0.0-4.5% of the variation and allowing a peak explains 38-74%.

    WHAT THE PEAK IS NOT, and I had this wrong for one turn on 2026-09-06 before the PI corrected
    me. I first read the peak as stimulation artifact, because the affected bands coincided with the
    folded harmonic landings. That inference was wrong and the reasons are worth recording, since it
    is an easy trap:

    * A stimulation artifact GROWS WITH CURRENT and keeps growing. Measured on this same visit, the
      bands containing the 55 Hz stimulation rate itself rise MONOTONICALLY to 18.2 times their
      starting value. A folded harmonic is that same artifact reappearing at a lower frequency, so
      it must have the same monotonic shape. A response that comes back down cannot be it.
    * The apparent coincidence with the harmonic landings was a THRESHOLD ARTEFACT of my own making.
      The curvature p-values run smoothly with frequency -- 0.711 at 20 Hz, 0.261 at 21, 0.055 at
      22, 0.026 at 23, then below 0.001 -- so the "clean split" was just where a 0.05 cutoff crossed
      a continuous gradient.
    * A folded harmonic lands at ONE frequency (25.0 Hz at 55 Hz stimulation). It cannot produce a
      smoothly DRIFTING peak position across neighbouring bands, which is what the data show: the
      peak current falls from 2.17 mA at 22 Hz to 1.72 mA at 29 Hz, r = -0.89, p = 0.0013 over the
      nine bands where the peak is resolved.

    So a detected peak is a real, organised amplitude response with a turning point, and the honest
    description is that the relationship is not monotonic. Whether it is physiological is a separate
    question this function does not answer; a harmonic check remains worth running alongside, but a
    peak is not evidence for artifact and the absence of one is not evidence against it.

    WHAT IT DELIBERATELY DOES NOT DO. It does not gate, score or veto anything, and it does not
    replace the linear fit. It answers one question so that a "does not respond" verdict can say
    whether it means "flat" or "not straight", which are different findings that the linear test
    alone renders identical.

    Returns a dict: ``curves`` (bool, the quadratic term is significant), ``peaks_inside`` (bool,
    and the curve opens downward with its turning point among the currents tested), ``peak_mA``,
    ``p_curvature``, ``r2_linear``, ``r2_quadratic``, and ``verdict`` in plain words.
    """
    x = np.asarray(amp_mA, dtype=float)
    y = np.asarray(power, dtype=float)
    if x.shape != y.shape:
        raise ValueError(f"amp_mA {x.shape} and power {y.shape} must match")
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    out = dict(curves=False, peaks_inside=False, peak_mA=float("nan"),
               p_curvature=float("nan"), r2_linear=float("nan"), r2_quadratic=float("nan"),
               n=int(x.size), verdict="not assessed")
    # Three coefficients plus a residual degree of freedom is the arithmetic floor; min_points is
    # the practical one. Below it the F test is not merely weak, it is undefined or absurd.
    if x.size < max(4, min_points) or np.unique(x).size < 3:
        out["verdict"] = (f"not assessed: {x.size} usable points at "
                          f"{np.unique(x).size} distinct currents")
        return out
    ss = float(np.sum((y - y.mean()) ** 2))
    if ss <= 0:
        out["verdict"] = "not assessed: band power does not vary at all"
        return out
    lin = np.polyfit(x, y, 1)
    qua = np.polyfit(x, y, 2)
    rss1 = float(np.sum((y - np.polyval(lin, x)) ** 2))
    rss2 = float(np.sum((y - np.polyval(qua, x)) ** 2))
    dof = x.size - 3
    out["r2_linear"] = 1.0 - rss1 / ss
    out["r2_quadratic"] = 1.0 - rss2 / ss
    if rss2 <= 0 or dof < 1:
        out["verdict"] = "not assessed: the quadratic fit is exact, so its residual has no spread"
        return out
    f_stat = ((rss1 - rss2) / 1.0) / (rss2 / dof)
    from scipy import stats as _st
    out["p_curvature"] = float(1.0 - _st.f.cdf(f_stat, 1, dof))
    out["curves"] = bool(out["p_curvature"] < 0.05)
    peak = -qua[1] / (2.0 * qua[0]) if qua[0] != 0 else float("nan")
    out["peaks_inside"] = bool(out["curves"] and qua[0] < 0
                               and np.isfinite(peak) and x.min() <= peak <= x.max())
    out["peak_mA"] = float(peak) if out["peaks_inside"] else float("nan")
    if out["peaks_inside"]:
        out["verdict"] = (f"rises then falls, peaking at {out['peak_mA']:.2f} mA inside the "
                          f"{x.min():.2f}-{x.max():.2f} mA tested; a straight line explains "
                          f"{100 * out['r2_linear']:.0f}% of the variation and a curve "
                          f"{100 * out['r2_quadratic']:.0f}%. A LINEAR SLOPE OR TWO-POINT "
                          f"COMPARISON WILL REPORT THIS AS NO RESPONSE")
    elif out["curves"]:
        out["verdict"] = ("curved but without a peak inside the currents tested, so a straight "
                          "line understates it without inverting it")
    else:
        out["verdict"] = "no curvature detected; a straight line is an adequate summary"
    return out


#: How a step's settled values are combined into one number. PI decision 2026-09-06: "generate
#: those new plots not using the middle value of the whole settled plateau but using the average of
#: the settled values. We've already decided that the averaging is better."
#:
#: WHY IT WAS THE MIDDLE VALUE BEFORE, and why changing it is now safe. The median was chosen
#: because a capture window can contain a transient and a middle value ignores it. That reason has
#: since been measured away for the settled portion: aligning 1-second epochs to the moment each
#: ramp finished, across 15 plateaus, band power deviates from its own settled level by 5-20% with
#: NO monotonic decay -- there is no transient left inside the window the exclusion hands over.
#:
#: WHAT THE CHANGE COSTS, stated because it is not free. Single short epochs are strongly
#: right-skewed: at 1-second resolution the 99.5th percentile is 7 times the median across bands and
#: 12 times at 8 Hz. A mean is pulled upward by those excursions and a median is not, so the mean of
#: a plateau sits above its median by an amount that depends on how many excursions that plateau
#: happened to contain. Both are computed and returned, so the difference is always inspectable
#: rather than a matter of belief.
STEP_SUMMARY = "mean"

def step_settled_stats(step_t0, step_window_s, tile_t, tile_power, *,
                       ramp_s=RAMP_EXCLUDE_S, min_tiles=MIN_SETTLED_TILES,
                       summary=STEP_SUMMARY, return_both=False):
    """One power vector per step: the AVERAGE across that step's SETTLED tiles.

    ``summary`` is ``"mean"`` (the default since 2026-09-06) or ``"median"``. With
    ``return_both=True`` the return gains a fourth element, the other summary computed on identical
    tiles, so a caller can report how far apart they are without re-deriving the windows.

    Named ``step_settled_stats`` because it no longer only returns medians; ``step_settled_medians``
    remains as a thin alias pinned to ``summary="median"`` so that existing callers and tests keep
    their exact previous behaviour rather than silently changing summary.

    THE UNIT IS THE STEP, NOT THE TILE. A device capture is a short recording summarised to one
    number, so the step median is its analogue, and a median rather than a mean because a capture
    window can contain a transient.

    WHAT THE CHOICE PROTECTS, measured rather than assumed. It does NOT protect the standardised
    separation: on a construction with a large between-step spread and a small within-step one,
    separation came out 2.54 at step level and 2.64 at tile level, a ratio of 1.04, with the slope
    identical to four decimals. A Cohen-style d divides by the pooled within-ARM spread, and an arm
    contains many different steps whichever unit is used, so between-step variation dominates the
    denominator either way. What tiles inflate is the INFERENCE: on that same construction the
    slope p-value went from 4.7e-54 to 1.7e-63 -- ten orders of magnitude -- on an n inflated
    twentyfold from 24 to 480 with the cluster count unchanged. Cluster-robust standard errors do
    not rescue it, because the clusters stay fixed while the rows inside each one multiply.

    ``tile_t`` must be sorted ascending. Returns ``(medians, n_tiles, kept)``.
    """
    t0 = np.asarray(step_t0, dtype=float)
    win = np.asarray(step_window_s, dtype=float)
    tt = np.asarray(tile_t, dtype=float)
    tp = np.asarray(tile_power, dtype=float)
    if t0.shape != win.shape:
        raise ValueError(f"step_t0 {t0.shape} and step_window_s {win.shape} must match")
    if tp.ndim != 2 or tp.shape[0] != tt.size:
        raise ValueError(f"tile_power must be (n_tiles, n_centres) aligned to tile_t "
                         f"({tt.size}); got {tp.shape}")
    if tt.size and np.any(np.diff(tt) < 0):
        raise ValueError("tile_t must be sorted ascending")

    if summary not in ("mean", "median"):
        raise ValueError(f"summary must be 'mean' or 'median'; got {summary!r}")
    meds, counts, kept, others = [], [], [], []
    for i, (a, w) in enumerate(zip(t0, win)):
        if not np.isfinite(a) or not np.isfinite(w) or w <= ramp_s:
            continue
        i0 = int(np.searchsorted(tt, a + ramp_s))
        i1 = int(np.searchsorted(tt, a + w))
        if i1 - i0 < int(min_tiles):
            continue
        block = tp[i0:i1, :]
        # Both are computed on IDENTICAL tiles so the pair is comparable by construction. The cost
        # of the second one is a single pass over a block of at most a few hundred rows.
        m_mean = np.nanmean(block, axis=0)
        m_med = np.nanmedian(block, axis=0)
        meds.append(m_mean if summary == "mean" else m_med)
        others.append(m_med if summary == "mean" else m_mean)
        counts.append(i1 - i0)
        kept.append(i)
    if not meds:
        n_cen = tp.shape[1] if tp.ndim == 2 else 0
        empty = (np.empty((0, n_cen)), np.empty(0, dtype=int), np.empty(0, dtype=int))
        return empty + (np.empty((0, n_cen)),) if return_both else empty
    out = (np.vstack(meds), np.asarray(counts, dtype=int), np.asarray(kept, dtype=int))
    return out + (np.vstack(others),) if return_both else out


def step_settled_medians(step_t0, step_window_s, tile_t, tile_power, *,
                         ramp_s=RAMP_EXCLUDE_S, min_tiles=MIN_SETTLED_TILES):
    """The middle value across each step's settled tiles -- the behaviour before 2026-09-06.

    Kept as a named alias rather than deleted so that a caller which genuinely wants the middle
    value says so, and so that existing tests pin the old behaviour explicitly instead of depending
    on what the default happens to be. New work should call :func:`step_settled_stats`.
    """
    return step_settled_stats(step_t0, step_window_s, tile_t, tile_power,
                              ramp_s=ramp_s, min_tiles=min_tiles, summary="median")


def build_within_visit_evidence(steps, *, channel, hemisphere, rate_hz, centers_hz,
                                tile_t, tile_power, band_width_hz=5.0,
                                amp_col=None, visit_col="visit", ramp_s=RAMP_EXCLUDE_S,
                                bin_mA=AMP_ARM_BIN_MA, min_tiles=MIN_SETTLED_TILES,
                                mode_requires=None):
    """One :class:`stage_gate.LfpEvidence` from clinic steps, plus its audit.

    ``steps`` needs ``t0`` (epoch seconds), ``window_s``, a per-hemisphere amplitude column and a
    visit label. The VISIT supplies both the era and the cluster, which is the whole point of the
    design: amplitude varies WITHIN a visit, so blocking on visit removes calendar time without
    absorbing the amplitude contrast. On the chronic epochs the opposite held -- each old era
    carried a single amplitude, so its dummy absorbed the era entirely and contributed nothing.
    """
    aud = EvidenceAudit(channel=str(channel), hemisphere=str(hemisphere), rate_hz=float(rate_hz))
    S = pd.DataFrame(steps)
    aud.n_psd_rows = int(np.asarray(tile_t).size)
    if amp_col is None:
        amp_col = f"amp_mA_{hemisphere}"
    for need in ("t0", "window_s", visit_col, amp_col):
        if need not in S.columns:
            aud.reason_unusable = f"steps frame has no {need!r} column"
            return None, aud
    aud.amp_col, aud.era_col = amp_col, visit_col
    aud.era_source = f"clinic visit ({visit_col!r}); amplitude varies WITHIN each visit"

    rate_num = pd.to_numeric(S.get("rate_hz"), errors="coerce")
    n0 = len(S)
    S = S[np.isclose(rate_num, float(rate_hz))] if rate_num is not None else S
    aud.n_dropped_other_rate = n0 - len(S)
    n0 = len(S)
    S = S[pd.to_numeric(S[amp_col], errors="coerce") > 0]
    aud.n_dropped_stim_off = n0 - len(S)
    S = S.dropna(subset=["t0", "window_s", amp_col])
    if not len(S):
        aud.reason_unusable = (f"no step at {rate_hz:g} Hz with stimulation on and a usable "
                               f"{amp_col}")
        return None, aud

    # The AVERAGE of the settled values, not the middle one -- PI decision 2026-09-06. See the
    # STEP_SUMMARY block for what the change costs and why it is now safe.
    med, cnt, kept = step_settled_stats(S["t0"].to_numpy(float),
                                          S["window_s"].to_numpy(float),
                                          tile_t, tile_power,
                                          ramp_s=ramp_s, min_tiles=min_tiles)
    aud.n_joined = int(len(kept))
    aud.n_dropped_no_epoch = int(len(S) - len(kept))
    aud.n_final = int(len(kept))
    if not len(kept):
        aud.reason_unusable = (f"no step had at least {min_tiles} tiles in its settled window "
                               f"(ramp exclusion {ramp_s:g} s)")
        return None, aud

    K = S.iloc[kept]
    amp = amplitude_arm_bins(pd.to_numeric(K[amp_col], errors="coerce").to_numpy(float), bin_mA)
    era = K[visit_col].astype(str).to_numpy()
    aud.amplitudes = tuple(sorted(np.unique(np.round(amp, 2)).tolist()))
    aud.n_eras = int(pd.Series(era).nunique())
    if len(aud.amplitudes) < 2:
        aud.reason_unusable = (f"only one binned amplitude ({aud.amplitudes}) — a capture needs "
                               f"two therapeutic amplitudes to contrast")
        return None, aud

    cen = np.asarray(centers_hz, dtype=float)
    if med.shape[1] != cen.size:
        raise ValueError(f"centers_hz has {cen.size} entries but the tile power has "
                         f"{med.shape[1]} columns")
    bp = {(round(float(c), 6), round(float(band_width_hz), 6)): med[:, j]
          for j, c in enumerate(cen)}
    kw = {} if mode_requires is None else {"mode_requires": mode_requires}
    ev = GATE.LfpEvidence(amplitude_mA=amp, band_power=bp, era=era, cluster=era,
                          hemisphere=str(hemisphere), **kw)
    return ev, aud


def build_all_within_visit(steps, *, centers_hz, tiles_by_channel,
                           hemispheres=("Left", "Right"), rates=None, channels=None, **kw):
    """Within-visit evidence for every (channel, hemisphere, rate) cell.

    ``tiles_by_channel`` maps a channel name to ``(tile_t, tile_power)``. Returns
    ``(dict, audit_frame)`` in the same shape as :func:`lfp_evidence.build_all`, so
    ``lfp_evidence.screen_cells`` consumes it without modification -- the majority-of-bands rule,
    the era-significance condition and the amplitude ceiling all apply identically.
    """
    S = pd.DataFrame(steps)
    chans = list(channels) if channels is not None else sorted(tiles_by_channel)
    if rates is None:
        rates = sorted(pd.to_numeric(S.get("rate_hz"), errors="coerce").dropna().unique().tolist())
    out, rows = {}, []
    for ch in chans:
        tt, tp = tiles_by_channel.get(ch, (np.empty(0), np.empty((0, len(centers_hz)))))
        for h in hemispheres:
            for r in rates:
                ev, aud = build_within_visit_evidence(
                    S, channel=ch, hemisphere=h, rate_hz=r, centers_hz=centers_hz,
                    tile_t=tt, tile_power=tp, **kw)
                rows.append({**aud.__dict__, "usable": ev is not None})
                if ev is not None:
                    out[(ch, h, float(r))] = ev
    return out, pd.DataFrame(rows)


# =================================================================================================
# SEARCHING THE BAND AXIS: A CLUSTER-BASED PERMUTATION TEST
# =================================================================================================
# WHY THE MAJORITY RULE CANNOT FIND A LOCALISED SIGNAL. `screen_cells` requires a MAJORITY of the
# scanned bands to respond, and that rule exists for a good reason: the 18 bands are 5 Hz wide on a
# 1 Hz grid, so they overlap heavily and the best of eighteen is the maximum of a correlated family
# rather than a finding. But the rule is a poor instrument for an effect confined to a few adjacent
# centres. A response localised to, say, 24.5-27.5 Hz occupies four of eighteen bands and can never
# reach 50%, however large and however consistent it is. On RCS08 that is not hypothetical: the
# within-visit screen found ONE_THREE_LEFT responding in 5 and 6 of 18 bands with 3 and 4
# significant negative era-blocked slopes, refused on the majority rule alone.
#
# THE STANDARD ANSWER IS A CLUSTER-BASED PERMUTATION TEST (Maris & Oostenveld 2007, J Neurosci
# Methods 164(1):177-190, doi:10.1016/j.jneumeth.2007.03.024). Compute a statistic per band,
# threshold it, group the survivors into runs of ADJACENT same-signed bands, and take each run's
# summed statistic as its cluster mass. Then permute the condition labels, recompute, and keep the
# largest cluster mass per replicate. The observed largest cluster is compared against that
# distribution. Because neighbouring bands are correlated, a real localised effect accumulates mass
# that noise does not, which is exactly the sensitivity the majority rule lacks.
#
# THREE LIMITATIONS, ENCODED BECAUSE THEY DECIDE HOW THE RESULT MAY BE USED.
#
#   1. IT ESTABLISHES EXISTENCE, NOT LOCATION. The test licenses "this cell responds to amplitude
#      somewhere in the adaptive window" and NOT "the response is at 24.5-27.5 Hz". This is not a
#      quibble; it is the documented property of the method (Sassenhagen & Draschkow 2019,
#      Psychophysiology 56(6):e13335, "Cluster-based permutation tests of MEG/EEG data do not
#      establish significance of effect latency or location"; see also Rousselet 2025, Eur J
#      Neurosci, on cluster-sum inference offering only weak family-wise control). THEREFORE THIS
#      FUNCTION MUST NEVER FEED THE DEPLOYABILITY GATE. Programming a device requires naming one
#      band, and this test cannot name one. It is a search instrument that decides whether a cell
#      is worth collecting targeted data on.
#   2. IT IS PRONE TO MISSING NARROW EFFECTS. An effect spanning very few bands accumulates little
#      mass, so its cluster does not stand out from noise clusters (Groppe, Urbach & Kutas 2011).
#      A null result here is therefore weak evidence of absence, and is reported as such.
#   3. IT DEPENDS ON THE CLUSTER-FORMING THRESHOLD, which is a free parameter and not a
#      significance level. Maris & Oostenveld are explicit that the threshold need not come from
#      any null distribution without invalidating the test, but it does change sensitivity, so
#      `t_threshold` is reported on the result and a sweep is cheap. Threshold-free cluster
#      enhancement (Smith & Nichols 2009, NeuroImage 44(1):83-98) removes the dependence and is
#      the natural upgrade if the choice ever turns out to matter here.
#
# WHY THE PERMUTATION NULL ALSO REPAIRS SOMETHING ELSE. The per-band statistic is a cluster-robust
# t, and the wild-bootstrap work earlier in this project established that this variance estimator is
# ANTI-CONSERVATIVE at the cluster counts available here (6 to 12 visits). Under a permutation null
# that ceases to matter for the family-wise p-value, because the SAME statistic, with the same bias,
# is recomputed on every permuted replicate: the bias is common to observation and null and cancels
# in the comparison. The per-band t values reported alongside remain biased and must not be read as
# significances on their own.

#: Cluster-forming threshold on the per-band |t|. Two is close to the conventional two-sided 5%
#: critical value for a comfortable residual degrees of freedom, and is a THRESHOLD rather than a
#: test level (see limitation 3 above).
CLUSTER_T_THRESHOLD = 2.0


def _band_t_cluster_robust(logp, amp, era, cluster):
    """Cluster-robust t on the amplitude coefficient of ``logp ~ amp + C(era)``.

    Hand-rolled for speed, because the permutation loop refits this thousands of times. It is the
    SAME model ``lfp_response.assess_response`` fits with statsmodels, and a test asserts the two
    agree on real data -- a fast reimplementation that silently disagreed with the gate's estimator
    would make the search and the verdict answer different questions.
    """
    y = np.asarray(logp, dtype=float)
    a = np.asarray(amp, dtype=float)
    ok = np.isfinite(y) & np.isfinite(a)
    if ok.sum() < 4:
        return np.nan
    y, a = y[ok], a[ok]
    era_v = np.asarray(era)[ok]
    clus = np.asarray(cluster)[ok]

    cols = [np.ones_like(a), a]
    levels = [u for u in pd.unique(era_v)][1:]          # drop one level as the reference
    for u in levels:
        cols.append((era_v == u).astype(float))
    X = np.column_stack(cols)
    if np.linalg.matrix_rank(X) < X.shape[1]:
        return np.nan
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta

    # CR0 sandwich: sum over clusters of (X_g' u_g)(X_g' u_g)'
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in pd.unique(clus):
        m = clus == g
        Xu = X[m].T @ resid[m]
        meat += np.outer(Xu, Xu)
    V = XtX_inv @ meat @ XtX_inv

    # STATSMODELS' FINITE-SAMPLE CORRECTION, applied so this matches the gate's estimator exactly.
    # Raw CR0 omits it; measured against `smf.ols(...).fit(cov_type="cluster")` the two differed by
    # a ratio of 1.134349 on a 90-row, 6-cluster construction, against a predicted
    # sqrt(G/(G-1) * (N-1)/(N-K)) of 1.134349 -- agreement to six decimals, which identified the
    # discrepancy as exactly this factor rather than a modelling difference.
    #
    # It does NOT change the family-wise p-value. N, K and G are fixed across permutations, so the
    # factor is a constant that scales every t and therefore every cluster mass identically in the
    # observation and in the null, and cancels in the comparison. It is applied because the
    # cluster-forming THRESHOLD and the reported per-band t values would otherwise mean something
    # different here than in `assess_response`, which a reader comparing the two would not expect.
    G = int(pd.unique(clus).size)
    N, K = X.shape[0], X.shape[1]
    if G > 1 and N > K:
        V = V * (G / (G - 1.0)) * ((N - 1.0) / (N - K))

    se = float(np.sqrt(V[1, 1])) if V[1, 1] > 0 else np.nan
    if not np.isfinite(se) or se == 0:
        return np.nan
    return float(beta[1] / se)


def _clusters_along_axis(t, threshold):
    """Runs of ADJACENT same-signed bands whose |t| clears the threshold, with their masses.

    Adjacency is position on the ordered centre axis, so the caller must pass centres in order.
    Returns ``[(i_start, i_stop_exclusive, mass), ...]``.
    """
    t = np.asarray(t, dtype=float)
    sup = np.isfinite(t) & (np.abs(t) >= float(threshold))
    out, i = [], 0
    while i < t.size:
        if not sup[i]:
            i += 1
            continue
        s = np.sign(t[i])
        j = i
        while j < t.size and sup[j] and np.sign(t[j]) == s:
            j += 1
        out.append((i, j, float(np.sum(t[i:j]))))
        i = j
    return out


def band_cluster_permutation(power_by_center, amp_mA, visits, *, n_perm=2000, seed=0,
                             t_threshold=CLUSTER_T_THRESHOLD, bin_mA=AMP_ARM_BIN_MA,
                             extra_thresholds=()):
    """Family-wise corrected answer to "does this cell respond to amplitude ANYWHERE?"

    The null permutes amplitude BETWEEN STEPS WITHIN EACH VISIT. That is the exchangeability the
    design actually supports: visits differ in overall power level and in which amplitudes were
    tried, so shuffling across visits would break the blocking and test a different, weaker null.
    Shuffling within a visit tests exactly "within this visit, amplitude carries no information
    about band power", which is the question.

    Returns the observed clusters, the largest cluster's family-wise p, and the resolution floor of
    that p. Read the module notes above before using it to justify anything: it CANNOT name a band.

    ``extra_thresholds`` evaluates additional cluster-forming thresholds in the SAME permutation
    loop and returns a p for each under ``threshold_sweep``. This is nearly free, because the
    expensive step is refitting the per-band t values on every permuted replicate and the threshold
    only affects how those t values are grouped afterwards. It is offered because the threshold is
    a free parameter (limitation 3) and the honest way to handle that is to show the whole sweep
    rather than one chosen value -- reporting the sweep is a sensitivity analysis, whereas reporting
    the best entry of it would be selection.
    """
    centers = sorted(float(c) for c in power_by_center)
    if len(centers) < 3:
        return {"available": False, "reason": f"a cluster test over the band axis needs at least "
                                              f"three centres, got {len(centers)}"}
    Y = np.column_stack([np.asarray(power_by_center[c], dtype=float) for c in centers])
    amp = amplitude_arm_bins(amp_mA, bin_mA)
    vis = np.asarray(visits)
    if not (Y.shape[0] == amp.size == vis.size):
        raise ValueError(f"power rows {Y.shape[0]}, amplitude {amp.size} and visits {vis.size} "
                         f"must all match")
    uv = pd.unique(vis)
    if uv.size < 2:
        return {"available": False, "reason": f"only {uv.size} visit(s); the null permutes "
                                              f"amplitude WITHIN visits and needs at least two"}
    # a visit with a single amplitude contributes no permutable contrast; say so rather than
    # letting it silently narrow the null
    per_visit = {str(v): int(np.unique(amp[vis == v]).size) for v in uv}
    n_informative = sum(1 for k in per_visit.values() if k >= 2)
    if n_informative == 0:
        return {"available": False, "reason": "no visit contains two amplitudes, so permuting "
                                              "within visits cannot change anything",
                "amplitudes_per_visit": per_visit}

    t_obs = np.array([_band_t_cluster_robust(Y[:, j], amp, vis, vis)
                      for j in range(len(centers))])
    # every threshold to evaluate, primary first, de-duplicated but order-preserving
    thresholds = [float(t_threshold)]
    for x in extra_thresholds:
        if float(x) not in thresholds:
            thresholds.append(float(x))
    obs_by_thresh = {th: _clusters_along_axis(t_obs, th) for th in thresholds}
    obs = obs_by_thresh[float(t_threshold)]
    if not obs:
        return {"available": True, "n_clusters": 0, "p_fwer": None,
                "t_per_band": {c: (None if not np.isfinite(t) else float(t))
                               for c, t in zip(centers, t_obs)},
                "t_threshold": float(t_threshold), "n_perm": int(n_perm),
                "amplitudes_per_visit": per_visit,
                "note": (f"no band reached |t| >= {t_threshold:g}, so there is no cluster to test. "
                         f"Given limitation 2 (narrow effects accumulate little mass) this is weak "
                         f"evidence of absence, not a demonstration that the cell is flat.")}

    rng = np.random.default_rng(seed)
    idx_by_visit = [np.flatnonzero(vis == v) for v in uv]
    null_max = {th: np.empty(int(n_perm), dtype=float) for th in thresholds}
    for k in range(int(n_perm)):
        a_perm = amp.copy()
        for ix in idx_by_visit:
            a_perm[ix] = rng.permutation(amp[ix])
        # the t values are computed ONCE per replicate and reused at every threshold; only the
        # grouping differs, which is what makes the sweep nearly free
        t_p = np.array([_band_t_cluster_robust(Y[:, j], a_perm, vis, vis)
                        for j in range(len(centers))])
        for th in thresholds:
            cl = _clusters_along_axis(t_p, th)
            null_max[th][k] = max((abs(m) for _, _, m in cl), default=0.0)

    def _p_for(th):
        cl = obs_by_thresh[th]
        if not cl:
            return None, None
        big = max(cl, key=lambda c: abs(c[2]))
        m = abs(big[2])
        return float((1 + np.sum(null_max[th] >= m)) / (1 + int(n_perm))), big

    p, biggest = _p_for(float(t_threshold))
    sweep = {}
    for th in thresholds:
        p_th, big_th = _p_for(th)
        sweep[th] = {"p_fwer": p_th, "n_clusters": len(obs_by_thresh[th]),
                     "largest_mass": (None if big_th is None else big_th[2]),
                     "largest_lo_hz": (None if big_th is None else centers[big_th[0]]),
                     "largest_hi_hz": (None if big_th is None else centers[big_th[1] - 1]),
                     "largest_n_bands": (None if big_th is None else big_th[1] - big_th[0])}
    return {
        "available": True,
        "n_clusters": len(obs),
        "clusters": [{"lo_hz": centers[i], "hi_hz": centers[j - 1], "n_bands": j - i,
                      "mass": m, "sign": ("negative" if m < 0 else "positive")}
                     for i, j, m in obs],
        "largest_cluster": {"lo_hz": centers[biggest[0]], "hi_hz": centers[biggest[1] - 1],
                            "n_bands": biggest[1] - biggest[0], "mass": biggest[2],
                            "sign": ("negative" if biggest[2] < 0 else "positive")},
        "p_fwer": p,
        "p_resolution": 1.0 / (1 + int(n_perm)),
        "t_threshold": float(t_threshold),
        "threshold_sweep": sweep,
        "n_perm": int(n_perm),
        "t_per_band": {c: (None if not np.isfinite(t) else float(t))
                       for c, t in zip(centers, t_obs)},
        "amplitudes_per_visit": per_visit,
        "n_visits_informative": n_informative,
        "note": ("Family-wise corrected across the band axis. Establishes EXISTENCE of an amplitude "
                 "response, NOT its location: the cluster's frequency limits are descriptive and "
                 "must not be used to choose a band to program (Sassenhagen & Draschkow 2019). The "
                 "per-band t values are cluster-robust and anti-conservative at these cluster "
                 "counts; only the family-wise p is calibrated, because the permutation recomputes "
                 "the same biased statistic under the null."),
    }


# =================================================================================================
# AVERAGING THE LAST 30 SECONDS BEFORE THE CURRENT IS CHANGED AGAIN
# =================================================================================================
# Added 2026-09-06 at the PI's instruction, and it is a DIFFERENT rule from the one
# `step_settled_medians` above applies. That older function throws away the first 45 seconds of each
# setting and takes the MEDIAN of whatever 3 second pieces are left, wherever in the setting they
# happen to fall. The rule below takes the MEAN of the ten 3 second pieces that make up the last 30
# seconds a setting was held, counting backwards from the moment the current was changed again.
#
# WHY THE LAST 30 SECONDS AND NOT THE FIRST. When the programmer raises the current the device does
# not jump to the new value, it slides up to it, and the earlier ramp work in this project measured
# the stimulation-frequency artefact still climbing 150 seconds after a step began. The last 30
# seconds a setting was held are therefore the most settled part of it, and they are the part
# furthest away from the slide.
#
# WHY THE CURRENT MUST HAVE GONE UP TO REACH THE SETTING. The PI's words: the rule "should only
# apply when the stimulus amplitude is being monotonically increased. For example, 1, 1.1, 1.2. If
# the stimulation amplitude value goes 0 and then goes back up to another amplitude, of course you
# shouldn't use that same rule because then it's not reflecting the last amplitude." If a setting
# was reached by turning the current DOWN, then whatever is left over in the brain signal from the
# higher current that came before it is still washing out during the 30 seconds we are about to
# average, and the number would be a mixture of two currents rather than a measurement of one. So a
# setting is only measured when the current that came immediately before it, at the same
# stimulation rate, was LOWER.
#
# WHERE THE 30 SECONDS ARE TAKEN FROM, which is the part that has to be got right. The 30 seconds
# end at the moment the NEXT setting starts, and they lie inside the setting we are measuring, so
# the average always describes the current that was actually running during those 30 seconds. It is
# never the 30 seconds after the change. The function refuses to let the window slide back past the
# start of its own setting: if a setting was held for less than 30 seconds, the window is cut short
# at the setting's own start and the piece count is reported as short rather than being topped up
# from the setting before it.

#: Length of one piece of recording, in seconds. Three seconds is what the streaming cache already
#: cuts the recording into, so this is the cache's own granularity and not a new choice.
CHUNK_S = 3.0

#: How far back from the next current change the average reaches, in seconds. The PI asked for 30
#: seconds, which at three seconds a piece is exactly ten pieces.
PRE_CHANGE_WINDOW_S = 30.0

#: How many three second pieces must be present before an average is reported. Ten is the number
#: the 30 second window holds when the recording has no gap in it. A setting with fewer pieces than
#: this gets no number at all, and the plotting code leaves that square of the picture empty
#: instead of colouring it, because colouring a square computed from three pieces the same way as a
#: square computed from ten would hide the difference.
MIN_CHUNKS_PRE_CHANGE = 10


def rising_current_settings(current_mA, block=None, *, tol_mA=1e-9):
    """Say, for each setting in a time-ordered list, whether the current went UP to reach it.

    ``current_mA`` is the stimulation current of each setting, in milliamps, in the order the
    settings were run. ``block`` optionally labels which stimulation rate (or whichever other
    grouping the caller wants) each setting belongs to; a setting is never compared with a setting
    in a different block, because a current of 2 mA at 10 Hz and a current of 2 mA at 55 Hz are not
    two points on one ladder.

    Returns two boolean arrays of the same length as ``current_mA``:

    ``reached_by_rise``
        True when the setting immediately before this one, in the same block, carried a STRICTLY
        smaller current. False for the first setting of a block, because there is nothing before it
        to compare with, and False when the current stayed the same or fell.
    ``followed_by_rise``
        True when the setting immediately after this one, in the same block, carries a strictly
        larger current. This is reported for the caller's information: it says whether the moment
        the 30 second window ends is a further step UP the ladder or is instead the ladder being
        abandoned, and the PI's example of the current dropping to zero and climbing again is
        exactly the case this column marks.
    """
    a = np.asarray(current_mA, dtype=float)
    n = a.size
    if block is None:
        b = np.zeros(n, dtype=object)
    else:
        b = np.asarray(block, dtype=object)
        if b.size != n:
            raise ValueError(f"block has {b.size} entries but current_mA has {n}")
    tol = float(tol_mA)
    up_from_previous = np.zeros(n, dtype=bool)
    up_to_next = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if b[i] == b[i - 1] and np.isfinite(a[i]) and np.isfinite(a[i - 1]):
            if a[i] - a[i - 1] > tol:
                up_from_previous[i] = True
                up_to_next[i - 1] = True
    return up_from_previous, up_to_next


def mean_power_before_next_change(step_t0, current_mA, tile_t, tile_power, *,
                                  block=None, step_end_t=None,
                                  window_s=PRE_CHANGE_WINDOW_S,
                                  min_chunks=MIN_CHUNKS_PRE_CHANGE,
                                  require_rise_into_setting=True,
                                  ramp_end_t=None, ramp_margin_s=RAMP_EXCLUDE_S):
    """One band-power vector per setting: the MEAN of the pieces in the last ``window_s`` seconds.

    THE NUMBERS COME OUT IN THE UNITS ``tile_power`` IS ALREADY IN, and nothing here takes a
    logarithm. The device forms band power as the linear sum of squared magnitude across the band,
    so a device band power is a number of order a hundred, and the mean of ten such numbers is
    another number of order a hundred. If a caller hands in logarithms this function will happily
    average logarithms, so the caller must hand in the device's own numbers.

    Arguments
    ---------
    step_t0
        The moment each setting started, in epoch seconds, in time order.
    current_mA
        The stimulation current of each setting, in milliamps. This must be the current of the ONE
        side whose ladder is being measured. Handing in the other side's current, or a sum of the
        two, would test the wrong ladder.
    tile_t, tile_power
        The recording cut into three second pieces: ``tile_t`` the start of each piece in epoch
        seconds, sorted ascending, and ``tile_power`` a ``(n_pieces, n_bands)`` array of band
        power. Rows whose band power is entirely missing are ignored.
    block
        Optional label per setting, passed through to :func:`rising_current_settings`. Pass the
        stimulation rate here when a visit ran more than one rate.
    step_end_t
        Optional explicit end for each setting, in epoch seconds. When it is not given, a setting
        is taken to end when the next setting in the same block starts, and the last setting of a
        block gets no window at all, because we do not know when the current was changed again and
        guessing would put the window somewhere the current may already have moved.
    window_s
        How far back from the end of the setting to reach. Thirty seconds by default.
    ramp_end_t, ramp_margin_s
        Optional per-setting moment the current FINISHED MOVING, from the device's own amplitude
        record, plus how long after that to keep excluding. When ``ramp_end_t`` is given the window
        is clipped so it cannot begin before ``ramp_end_t + ramp_margin_s``; a setting whose clipped
        window then holds fewer than ``min_chunks`` pieces is refused with a reason naming the ramp.

        WHY THIS CLIP EXISTS, added 2026-09-06 at the PI's request. The rule this function
        implements -- average the last ``window_s`` seconds before the current next moves -- assumes
        the setting has been held for longer than ``window_s``. Measured across RCS08's whole record,
        that assumption fails on 188 of 600 plateaus, where the hold after the ramp is under 30 s and
        a 30 s look-back therefore reaches back into the ramp and averages signal recorded while the
        current was still changing. On the specific visits behind the published figures the exposure
        is much smaller because those visits hold longer -- 2 of 27 plateaus on 2026-08-18, 1 of 33
        on 2026-06-24, and 6 of 29 on 2025-08-21 -- but it is not zero, and the 2025-08-21 visit is
        the pre-registered one.

        THIS IS A CLIP AND NOT A NEW RULE. Where the hold is longer than the window, which is the
        common case, nothing changes and the values are identical. Passing ``ramp_end_t=None``
        reproduces the original behaviour exactly, which is why every existing test still passes
        unchanged. Get the ramp ends from :func:`ramp_windows_from_amplitude`, which measures them
        from ``BrainSenseLfp[].LfpData[].{Left,Right}.mA`` rather than assuming a fixed duration --
        the ramp is NOT predictable from the step size, running 0.0 s for a single-increment step and
        up to 75.0 s for one the device chose to deliver in 35 pieces.
    min_chunks
        How many pieces must be found in that window before an average is reported. Ten by default.
    require_rise_into_setting
        When True, which is the default, a setting is only measured if the current went UP to reach
        it. Set it to False only to see what the looser rule would have given; the numbers it lets
        through are mixtures of the setting and the higher current that preceded it.

    Returns ``(power, table)``. ``power`` is a ``(n_settings, n_bands)`` array whose refused rows
    are all missing. ``table`` is a ``pandas.DataFrame`` with one row per setting carrying the
    current, the window that was used, how many pieces were found, whether the setting was
    accepted, and if it was refused, the plain reason why.
    """
    t0 = np.asarray(step_t0, dtype=float)
    amp = np.asarray(current_mA, dtype=float)
    tt = np.asarray(tile_t, dtype=float)
    tp = np.asarray(tile_power, dtype=float)
    n = t0.size
    if amp.size != n:
        raise ValueError(f"step_t0 has {n} entries but current_mA has {amp.size}")
    if tp.ndim != 2 or tp.shape[0] != tt.size:
        raise ValueError(f"tile_power must be (n_pieces, n_bands) aligned to tile_t "
                         f"({tt.size}); got {tp.shape}")
    if tt.size and np.any(np.diff(tt) < 0):
        raise ValueError("tile_t must be sorted ascending")
    if step_end_t is not None and np.asarray(step_end_t, dtype=float).size != n:
        raise ValueError("step_end_t must have one entry per setting")
    if not np.isfinite(window_s) or window_s <= 0:
        raise ValueError(f"window_s must be positive and finite, got {window_s}")
    ramp_end = None
    if ramp_end_t is not None:
        ramp_end = np.asarray(ramp_end_t, dtype=float)
        if ramp_end.shape != t0.shape:
            raise ValueError(f"ramp_end_t has shape {ramp_end.shape} but there are {t0.shape[0]} "
                             f"settings; pass one measured ramp end per setting, or None")
        if not np.isfinite(ramp_margin_s) or ramp_margin_s < 0:
            raise ValueError(f"ramp_margin_s must be finite and not negative, got {ramp_margin_s}")

    n_bands = tp.shape[1]
    up_from_previous, up_to_next = rising_current_settings(amp, block)
    b = (np.zeros(n, dtype=object) if block is None else np.asarray(block, dtype=object))

    # When the caller did not say when each setting ended, a setting ends when the next one in the
    # same block starts. The last setting of a block therefore has no end, and gets no window.
    if step_end_t is None:
        t_end = np.full(n, np.nan)
        for i in range(n - 1):
            if b[i] == b[i + 1]:
                t_end[i] = t0[i + 1]
    else:
        t_end = np.asarray(step_end_t, dtype=float).copy()

    power = np.full((n, n_bands), np.nan)
    rows = []
    for i in range(n):
        want_lo = t_end[i] - float(window_s)
        lo = max(want_lo, t0[i]) if np.isfinite(t_end[i]) else np.nan
        # CLIP AT THE MEASURED END OF THE RAMP, when the caller supplies one. Without this the
        # window silently reaches back into the stretch where the current was still moving on any
        # setting held for less than window_s -- 188 of 600 plateaus across RCS08's record. Where
        # the hold is longer than the window, which is the common case, this changes nothing and
        # the values are bit-identical to the unclipped rule.
        clipped_by_ramp = False
        if ramp_end_t is not None and np.isfinite(lo):
            floor_t = float(ramp_end[i]) + float(ramp_margin_s)
            if np.isfinite(floor_t) and floor_t > lo:
                lo, clipped_by_ramp = floor_t, True
        n_found = 0
        if np.isfinite(t_end[i]):
            sel = (tt >= lo) & (tt < t_end[i])
            if sel.any():
                sub = tp[sel, :]
                sel_rows = ~np.all(~np.isfinite(sub), axis=1)
                sub = sub[sel_rows, :]
                n_found = int(sub.shape[0])
            else:
                sub = np.empty((0, n_bands))
        else:
            sub = np.empty((0, n_bands))

        reason = ""
        if require_rise_into_setting and not up_from_previous[i]:
            reason = ("the current did not go up to reach this setting, so the 30 seconds would "
                      "mix this setting with the higher or equal current before it")
        elif not np.isfinite(t_end[i]):
            reason = ("the moment the current was next changed is not known, so there is no "
                      "30 second window that is certain to sit inside this setting")
        elif n_found < int(min_chunks) and clipped_by_ramp:
            reason = (f"the current finished moving only {float(t_end[i]) - float(ramp_end[i]):.0f} "
                      f"seconds before it was changed again, so after excluding the ramp and "
                      f"{float(ramp_margin_s):.0f} further seconds only {n_found} three second "
                      f"pieces were left, fewer than the {int(min_chunks)} required")
        elif n_found < int(min_chunks):
            reason = (f"only {n_found} three second pieces of recording were found in the "
                      f"{float(window_s):g} seconds before the next current change, and "
                      f"{int(min_chunks)} are required")
        if not reason:
            power[i, :] = np.nanmean(sub, axis=0)

        rows.append(dict(
            setting_index=i,
            block=b[i],
            current_mA=float(amp[i]) if np.isfinite(amp[i]) else np.nan,
            t_start_s=float(t0[i]),
            t_next_change_s=float(t_end[i]) if np.isfinite(t_end[i]) else np.nan,
            window_start_s=float(lo) if np.isfinite(lo) else np.nan,
            window_shortened_by_setting_start=bool(np.isfinite(t_end[i]) and want_lo < t0[i]),
            current_rose_into_this_setting=bool(up_from_previous[i]),
            next_change_is_a_further_rise=bool(up_to_next[i]),
            n_chunks_found=n_found,
            accepted=(not reason),
            refusal_reason=reason,
        ))
    return power, pd.DataFrame(rows)
