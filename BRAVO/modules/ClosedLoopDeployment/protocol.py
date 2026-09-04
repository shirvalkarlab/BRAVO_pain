"""Generate the randomised paired titration session, and size it.

WHY THIS FILE EXISTS, AND WHAT IT CAN AND CANNOT DELIVER
-------------------------------------------------------
Every amplitude-to-power estimate in this project so far comes from the historical record, in which
the amplitude a participant was on is confounded with WHEN they were on it. Settings changed for
clinical reasons, in eras, and the eras differ in medication, in season, in electrode impedance and
in the participant's baseline pain. The strongest single result on the record makes the problem
concrete: on ONE_THREE_LEFT at 165 Hz all seventeen bands moved in the correct direction with a
median separation of d = 1.28, and that estimate still rests on two eras, so era-confounding is not
excluded by it.

Randomising the ORDER in which candidate configurations are tested inside ONE session is what breaks
that confound, and it is the entire point of this file. Nothing else here is novel; the arithmetic
of a step list is bookkeeping. Randomisation within a session is the prerequisite that makes the
amplitude-to-power edge interpretable, because it removes the systematic association between the
amplitude tested and the time at which it was tested.

What this file produces is a PLAN. It generates no data and it validates no biomarker. Its power
calculation says how large an effect a session of a given size could detect if the assumptions hold,
which is a statement about the design and not evidence about this participant. The plan cannot be
run retrospectively: the session has to happen.

THE MANUFACTURER'S PROCEDURE
----------------------------
The step structure follows rule ``D50`` (A610 clinician application manual p. 45), which specifies:
set the amplitude to 0.0 mA for 45 to 60 seconds to establish a physiologic baseline; then increase
the amplitude in steps of 0.1 to 0.5 mA, with the ramp interval adjustable from 0.5 to 10 seconds;
and after each adjustment stream for 30 to 45 seconds to determine the effect on LFP power. The two
adjustable ranges are imported from ``StimOptimizer.routines.percept_adaptive``
(``TITRATION_RAMP_RANGE_S``, ``TITRATION_SETTLE_RANGE_S``) rather than retyped here, so that the
device numbers live in one file and any parameter outside the permitted range is refused rather than
quietly emitted into a plan a clinician might follow.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import optimize, stats

from StimOptimizer.routines import percept_adaptive

from . import types

#: Manufacturer ranges for the titration, rule ``D50`` (A610 p. 45), imported so they cannot drift.
RAMP_RANGE_S = percept_adaptive.TITRATION_RAMP_RANGE_S        # (0.5, 10.0)
SETTLE_RANGE_S = percept_adaptive.TITRATION_SETTLE_RANGE_S    # (30.0, 45.0)

#: Baseline at 0.0 mA, rule ``D50``: "45 to 60 seconds". Quoted as a range for the same reason.
BASELINE_RANGE_S = (45.0, 60.0)

#: Amplitude increment range, rule ``D50``: "steps of 0.1 to 0.5 mA".
STEP_RANGE_mA = (0.1, 0.5)

#: The biomarker's own integration window, 1024-point Welch at 250 Hz, imported from
#: ``percept_adaptive``. Every validated pain-band association in this project was computed on it,
#: so it is the unit in which a streaming window's usable length should be counted: a dwell that
#: yields three of these windows supports a much weaker estimate than one that yields nine, and a
#: plan that reports only seconds hides that.
INTEGRATION_S = percept_adaptive.BIOMARKER_INTEGRATION_S      # 4.096 s

#: Multiple of the integration window discarded at the start of each streaming period, taken from
#: ``percept_adaptive.SETTLE_WINDOWS``. The reason is stated there: device averaging is
#: non-overlapping (rule ``D14``), so a power estimate spanning an amplitude change still contains
#: pre-change signal until one whole window has turned over, and analysing it would mix the two
#: amplitudes being compared. The multiple is a declared margin, not a measurement.
SETTLE_WINDOWS = percept_adaptive.SETTLE_WINDOWS              # 2.0
SETTLE_EXCLUDE_S = SETTLE_WINDOWS * INTEGRATION_S             # 8.192 s

#: Default number of paired blocks PER CANDIDATE. Chosen, not inherited: it is the smallest n that
#: reaches the plan's stated target of 80 percent power for a paired d of 1.28 with the alpha
#: divided across four candidate configurations.
#:
#: The arithmetic is worth spelling out because the round number is the wrong one.
#: ``paired_power(10, 1.28, 0.05, n_comparisons=4)`` returns about 0.797, and nine blocks returns
#: about 0.719, so ten blocks comes close to the target but does not reach it. Eleven blocks returns
#: about 0.857 and is therefore the smallest session that meets 80 percent. Ten was rejected as the
#: default despite being within a third of a percentage point: a session sized at 79.7 percent that
#: is reported as an 80 percent design is an overstatement about a study on a participant, and the
#: cost of the honest choice is one extra block, which this file prices explicitly in the plan's
#: duration. A caller who prefers the shorter session can pass ``n_pairs=10`` and read the power the
#: plan then states for it.
DEFAULT_N_PAIRS = 11

#: The effect size the plan is sized for. It is the median separation observed on ONE_THREE_LEFT at
#: 165 Hz in the historical record, and it is an ASSUMPTION carried into the design rather than a
#: guarantee: that estimate rests on two eras, so if any part of it was era-confounding rather than
#: amplitude, the true within-session effect is smaller and this session is underpowered. The
#: session is worth running anyway, because it is the only design that can find out.
DEFAULT_D_TARGET = 1.28

#: Conventional power target, used when solving for the effect size a given session could detect.
DEFAULT_POWER_TARGET = 0.80

#: Amplitude increment, at the top of the ``D50`` range. The increment size does not affect what is
#: measured, because the ramp is excluded from analysis; it only sets how long a ramp takes, and the
#: coarsest permitted increment therefore makes the shortest session. A clinician who needs finer
#: increments for tolerability can pass any value in the range and see the duration change.
DEFAULT_STEP_mA = 0.5

#: Interval between successive amplitude increments, in seconds. This is a DECLARED CHOICE inside
#: the manufacturer's 0.5 to 10 second range and not a device default, and it is the one parameter
#: here that this module cannot reason its way to. Because the ramp is excluded from analysis, the
#: measurement does not care how fast it is, so the only considerations are session length, which
#: favours the fast end, and how large an amplitude change this participant tolerates without
#: paresthesia, which is a clinical judgement no module can make. Two seconds is set as a value with
#: margin over the fastest permitted rate; it should be replaced with what the participant tolerates.
DEFAULT_RAMP_INTERVAL_S = 2.0


# --------------------------------------------------------------------------------------------
# Power
# --------------------------------------------------------------------------------------------
def paired_power(n_pairs, d, alpha=0.05, n_comparisons=1) -> float:
    """Power of a two-sided paired t-test at effect size ``d``, Bonferroni-corrected.

    ``n_pairs`` is the number of matched pairs, meaning the number of DIFFERENCES entering the test,
    and ``d`` is the standardised effect size of those differences: the mean difference divided by
    the standard deviation of the differences, which is Cohen's d for the paired case and is not
    interchangeable with a between-groups d. ``n_comparisons`` is the number of comparisons the
    familywise alpha is split across; the titration session tests one comparison per candidate
    configuration, so ``titration_plan`` passes the number of candidates.

    The calculation uses the noncentral t distribution rather than a normal approximation. That is
    not a refinement, it is a requirement at these sample sizes: with eleven pairs there are ten
    degrees of freedom, the two-sided critical value under Bonferroni correction across four
    comparisons is 3.04 against the normal approximation's 2.50, and treating the test statistic as
    normal would report 96 percent power where the exact calculation gives 86 percent, an
    overstatement of ten percentage points. The test statistic is distributed as
    noncentral t with ``n_pairs - 1`` degrees of freedom and noncentrality ``d * sqrt(n_pairs)``, and
    the power is the probability that it falls beyond either critical value.

    WHAT THIS DOES NOT ACCOUNT FOR. It assumes the pairs are independent of one another, that the
    differences are approximately normal, and that ``d`` is known rather than estimated. In this
    session the pairs are repeated blocks within one visit on one participant, so a real analysis
    should expect some correlation between blocks, and any such correlation makes the effective
    number of independent pairs smaller than the count used here. This function therefore gives an
    upper bound on the achievable power for a given number of blocks, and the honest reading of an
    80 percent result is "80 percent if the blocks behave as independent replicates".
    """
    n = int(n_pairs)
    if n < 2:
        raise ValueError(
            f"n_pairs must be at least 2, got {n_pairs!r}. A paired t-test on one difference has "
            "zero degrees of freedom and no power is defined for it.")
    d = float(d)
    if not np.isfinite(d):
        raise ValueError(f"d must be finite, got {d!r}.")
    a = float(alpha)
    if not (0.0 < a < 1.0):
        raise ValueError(f"alpha must lie strictly between 0 and 1, got {alpha!r}.")
    k = int(n_comparisons)
    if k < 1:
        raise ValueError(f"n_comparisons must be at least 1, got {n_comparisons!r}.")

    a_adj = a / k
    df = n - 1
    ncp = d * math.sqrt(n)
    t_crit = stats.t.ppf(1.0 - a_adj / 2.0, df)
    # Both tails are counted. The lower tail is negligible for a large positive d but not for the
    # small effects a reader may probe this function with, and dropping it would report a power of
    # exactly zero for a d of zero instead of the alpha it must equal.
    return float(_tail(t_crit, df, ncp, upper=True) + _tail(t_crit, df, ncp, upper=False))


def _tail(t_crit, df, ncp, *, upper):
    """One rejection tail of the noncentral t, with a fallback for a numerical failure in scipy.

    ``scipy.stats.nct`` returns NaN rather than an underflowed zero for the far tail: at ten degrees
    of freedom and a noncentrality of about 22, ``nct.cdf(-t_crit, df, ncp)`` is NaN even though the
    quantity is a wrong-direction rejection probability of order 1e-120. Left unhandled that NaN
    propagates into the power, and it broke the numerical solve in :func:`detectable_d`, which
    evaluates the power at effect sizes far larger than any that will be reported.

    The fallback is the noncentral t's own symmetry identity, which is exact rather than an
    approximation: the distribution of the statistic under a noncentrality of ``-ncp`` is the mirror
    image of its distribution under ``+ncp``, so the probability of falling below ``-t_crit`` with
    noncentrality ``ncp`` equals the probability of exceeding ``+t_crit`` with noncentrality
    ``-ncp``. scipy evaluates the identity's other side to a clean zero in exactly the cases where
    it fails on this one. Verified against the cases scipy computes successfully, where the two
    routes agree to the last displayed digit.

    A NaN that survives both routes is raised rather than replaced with a zero, because the regimes
    where the far tail is genuinely not negligible are the small degrees of freedom the noncentral t
    was chosen for in the first place, and silently dropping the tail there would understate the
    probability of a significant result in the WRONG direction.
    """
    if upper:
        v = float(stats.nct.sf(t_crit, df, ncp))
        if not np.isfinite(v):
            v = float(stats.nct.cdf(-t_crit, df, -ncp))
    else:
        v = float(stats.nct.cdf(-t_crit, df, ncp))
        if not np.isfinite(v):
            v = float(stats.nct.sf(t_crit, df, -ncp))
    if not np.isfinite(v):
        raise RuntimeError(
            f"the noncentral t {'upper' if upper else 'lower'} tail could not be evaluated at "
            f"df={df}, noncentrality={ncp:.6g}, critical value={t_crit:.6g}: scipy returned a "
            "non-finite value through both the direct route and the symmetry identity. The power "
            "is not reported rather than reported with a dropped tail.")
    return v


def detectable_d(n_pairs, power=DEFAULT_POWER_TARGET, alpha=0.05, n_comparisons=1) -> float | None:
    """Smallest paired effect size a session of ``n_pairs`` blocks can detect at ``power``.

    This is the inverse of :func:`paired_power` in ``d``, solved numerically because the noncentral t
    cumulative distribution has no closed-form inverse in the noncentrality parameter. It is
    reported on the plan so a clinician reading a session that does not reach the target power can
    see what the session CAN detect rather than only that it misses what was hoped for.

    Returns ``None`` when the target power is unreachable at this ``n_pairs`` within a d of 100,
    which happens for very small sessions under heavy correction. ``None`` is returned rather than a
    large number because a d of 100 is not an effect size anyone should read as attainable, and
    printing one would invite exactly that.
    """
    lo, hi = 0.0, 100.0
    if paired_power(n_pairs, hi, alpha, n_comparisons) < power:
        return None
    if paired_power(n_pairs, lo, alpha, n_comparisons) >= power:
        # Only possible if the requested power is at or below alpha, which is not a meaningful ask.
        return 0.0
    return float(optimize.brentq(
        lambda x: paired_power(n_pairs, x, alpha, n_comparisons) - power, lo, hi, xtol=1e-6))


# --------------------------------------------------------------------------------------------
# Candidate handling
# --------------------------------------------------------------------------------------------
def _coerce_candidates(candidates, reference_amp_mA):
    """Normalise the candidate list into ``[{label, test_amp_mA, ref_amp_mA, detail}, ...]``.

    Permissive about shape because the candidates arrive from several places in this project — the
    deployability screen, a hand-written list in a session note, a bare list of amplitudes to probe —
    and strict about content, because a candidate with no test amplitude cannot be titrated and a
    plan that silently dropped it would be a plan for a different session than the one requested.
    """
    if candidates is None:
        raise ValueError("candidates is None; there is nothing to titrate.")
    try:
        items = list(candidates)
    except TypeError as exc:
        raise ValueError(f"candidates is not iterable: {candidates!r}") from exc
    if not items:
        raise ValueError(
            "candidates is empty. A titration session with no configurations to test has no steps, "
            "and returning an empty plan would look like a successfully generated session.")

    label_keys = ("label", "id", "name", "config", "cell", "channel")
    amp_keys = ("test_amp_mA", "amp_mA", "amplitude_mA", "amp", "amplitude")
    ref_keys = ("ref_amp_mA", "reference_amp_mA", "ref_mA")

    out = []
    for i, c in enumerate(items):
        default_label = f"cfg{i + 1}"
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            # A bare number is a test amplitude with a generated label. It is rewritten into the
            # mapping form rather than appended directly so that it goes through the SAME reference
            # resolution and the same validity checks as every other candidate; an early return here
            # was a real bug, because it left the reference amplitude unset and produced a plan whose
            # steps had no amplitude to ramp to.
            c = {"label": default_label, "test_amp_mA": float(c)}

        if isinstance(c, dict):
            get = c.get
            keys = set(c)
            detail = {k: v for k, v in c.items() if k not in amp_keys and k not in ref_keys}
        else:
            def get(k, default=None, _c=c):
                return getattr(_c, k, default)
            keys = {k for k in label_keys + amp_keys + ref_keys if hasattr(c, k)}
            detail = {}

        amp = None
        for k in amp_keys:
            v = get(k)
            if v is not None:
                amp = float(v)
                break
        if amp is None:
            raise ValueError(
                f"candidate {i} ({c!r}) carries no test amplitude. Looked for the keys or "
                f"attributes {list(amp_keys)}; found {sorted(keys)}. Every candidate needs the "
                "amplitude that is to be tested, because the amplitude is what the session varies.")
        if amp < 0:
            raise ValueError(f"candidate {i} has a negative test amplitude {amp!r}.")

        label = None
        for k in label_keys:
            v = get(k)
            if v is not None:
                label = str(v)
                break
        if label is None:
            label = default_label

        ref = None
        for k in ref_keys:
            v = get(k)
            if v is not None:
                ref = float(v)
                break
        if reference_amp_mA is not None:
            ref = float(reference_amp_mA)
        if ref is None:
            # The manufacturer's own baseline is 0.0 mA, so it is the fallback reference. The
            # consequence is recorded on the plan's note rather than left implicit: a 0.0 mA
            # reference makes every contrast test-against-off, which answers whether stimulation
            # moves the band at all, and not whether one amplitude differs from the clinical one.
            ref = 0.0
        if ref < 0:
            raise ValueError(f"candidate {i} has a negative reference amplitude {ref!r}.")
        if abs(ref - amp) < 1e-12:
            raise ValueError(
                f"candidate {i} ({label!r}) has its reference amplitude equal to its test amplitude "
                f"({amp!r} mA). The pair would contrast a setting with itself, and its difference "
                "would be measurement noise entering the power calculation as if it were a "
                "comparison.")
        out.append({"label": label, "test_amp_mA": amp, "ref_amp_mA": ref, "detail": detail})

    labels = [c["label"] for c in out]
    if len(set(labels)) != len(labels):
        raise ValueError(
            f"candidate labels are not unique: {labels}. The analysis groups differences by label, "
            "so duplicates would silently pool two configurations into one comparison.")
    return out


def _check_range(name, value, rng, rule):
    lo, hi = rng
    if not (lo - 1e-9 <= value <= hi + 1e-9):
        raise ValueError(
            f"{name}={value!r} lies outside the manufacturer's permitted range of {lo:g} to {hi:g} "
            f"({rule}). This is refused rather than clipped because the returned plan is something "
            "a clinician may follow at the programmer, and a step list containing a value the "
            "device does not permit is worse than no plan.")


# --------------------------------------------------------------------------------------------
# The session
# --------------------------------------------------------------------------------------------
def titration_plan(candidates, n_pairs=DEFAULT_N_PAIRS, alpha=0.05, seed=None, *,
                   d_target=DEFAULT_D_TARGET,
                   baseline_s=BASELINE_RANGE_S[0],
                   dwell_s=SETTLE_RANGE_S[1],
                   step_mA=DEFAULT_STEP_mA,
                   ramp_interval_s=DEFAULT_RAMP_INTERVAL_S,
                   reference_amp_mA=None,
                   return_amp_mA=None,
                   randomise_within_pair=True) -> types.Protocol:
    """Build the randomised paired titration session for ``candidates``.

    ``candidates`` is a sequence of configurations to test. Each may be a mapping or an object
    carrying a test amplitude (``test_amp_mA``, ``amp_mA``, ``amplitude_mA``, ``amp`` or
    ``amplitude``), optionally a label and optionally its own matched reference amplitude
    (``ref_amp_mA``); a bare number is read as a test amplitude with a generated label.

    ``n_pairs`` is the number of blocks, and therefore the number of paired differences PER
    CANDIDATE. It is not the total number of measurements: a session tests every candidate in every
    block, so the number of streaming periods is ``2 * n_pairs * len(candidates)``.

    ``alpha`` is the familywise error rate. It is divided by the number of candidates, because each
    candidate contributes one comparison and the session would otherwise buy its significance by
    testing several configurations at the nominal level.

    ``seed`` seeds the random generator. When it is None a seed is drawn and RECORDED on the result,
    so a plan generated without one is still reproducible after the fact; the alternative, an
    unrecorded seed, would make the session's own randomisation unauditable, and an audit of the
    randomisation is the thing that makes the resulting estimate believable.

    STRUCTURE, AND WHY IT IS THIS SHAPE. The session opens with a baseline at 0.0 mA (rule ``D50``)
    and repeats one baseline at the start of every block. Re-baselining costs about a minute per
    block and buys the ability to distinguish a real amplitude effect from drift across an hour-long
    visit; with a single opening baseline, a monotone drift in band power would appear as an
    amplitude effect in whichever configurations happened to be tested late. Inside each block the
    order of candidates is randomised afresh, which is what breaks the confound between amplitude
    and time. Inside each pair the order of the reference and the test measurement is randomised
    too, unless ``randomise_within_pair`` is False, so that any carryover from the preceding
    amplitude falls on the reference and the test equally often instead of always on one of them.
    The session closes by returning the amplitude to the reference, because a session must not end
    with the participant left at a probe amplitude.

    EVERY STEP CARRIES ITS PURPOSE AND ITS ANALYSIS STATUS. Ramp steps are marked
    ``analysis=False``: they are transitions, and the power estimate spanning an amplitude change
    contains signal from both amplitudes. Measurement steps additionally report how much of their
    dwell is usable after the settle exclusion and how many of the biomarker's own integration
    windows that leaves, because a dwell at the bottom of the manufacturer's range leaves five such
    windows and one at the top leaves eight, and that difference matters more to the resulting
    estimate than the raw seconds suggest.
    """
    _check_range("baseline_s", float(baseline_s), BASELINE_RANGE_S, "D50, A610 p. 45")
    _check_range("dwell_s", float(dwell_s), SETTLE_RANGE_S, "D50, A610 p. 45")
    _check_range("step_mA", float(step_mA), STEP_RANGE_mA, "D50, A610 p. 45")
    _check_range("ramp_interval_s", float(ramp_interval_s), RAMP_RANGE_S, "D50, A610 p. 45")

    baseline_s = float(baseline_s)
    dwell_s = float(dwell_s)
    step_mA = float(step_mA)
    ramp_interval_s = float(ramp_interval_s)

    n_pairs = int(n_pairs)
    if n_pairs < 2:
        raise ValueError(
            f"n_pairs must be at least 2, got {n_pairs!r}; the paired test needs at least two "
            "differences to have any degrees of freedom.")

    cands = _coerce_candidates(candidates, reference_amp_mA)
    n_cand = len(cands)

    usable_s = dwell_s - SETTLE_EXCLUDE_S
    if usable_s <= 0:
        raise ValueError(
            f"a dwell of {dwell_s:g} s leaves nothing usable after the {SETTLE_EXCLUDE_S:.3f} s "
            "settle exclusion, which is the time needed for a non-overlapping power estimate to be "
            "free of the previous amplitude. Lengthen the dwell or reduce SETTLE_WINDOWS with a "
            "stated reason.")
    n_windows = int(math.floor(usable_s / INTEGRATION_S))

    if seed is None:
        # Drawn from the operating system's entropy and then recorded, so the plan is reproducible
        # even though the caller did not choose a seed.
        seed = int(np.random.SeedSequence().generate_state(1)[0])
    seed = int(seed)
    rng = np.random.default_rng(seed)

    steps = []
    t = 0.0
    amp = 0.0   # the session begins at 0.0 mA for the D50 baseline

    def add(role, amplitude, dwell, purpose, *, analysis, block=None, candidate=None, pair=None):
        nonlocal t
        rec = {
            "index": len(steps),
            "block": block,
            "candidate": candidate,
            "pair": pair,
            "role": role,
            "amplitude_mA": round(float(amplitude), 4),
            "dwell_s": round(float(dwell), 3),
            "t_start_s": round(t, 3),
            "t_end_s": round(t + float(dwell), 3),
            "analysis": bool(analysis),
            "purpose": purpose,
        }
        if analysis:
            rec["settle_exclude_s"] = round(SETTLE_EXCLUDE_S, 3)
            rec["usable_s"] = round(usable_s, 3)
            rec["n_integration_windows"] = n_windows
        steps.append(rec)
        t += float(dwell)

    def ramp_to(target, *, block=None, candidate=None, pair=None, why=""):
        """Emit the amplitude change as its own non-analysed step, with the D50 increment timing."""
        nonlocal amp
        target = float(target)
        if abs(target - amp) < 1e-12:
            return
        n_inc = int(math.ceil((abs(target - amp) - 1e-12) / step_mA))
        dur = n_inc * ramp_interval_s
        add("ramp", target, dur,
            f"Change amplitude from {amp:.1f} to {target:.1f} mA in {n_inc} increment(s) of at most "
            f"{step_mA:g} mA at {ramp_interval_s:g} s intervals (D50, A610 p. 45). Not analysed: a "
            f"power estimate spanning an amplitude change contains signal from both amplitudes. "
            + why,
            analysis=False, block=block, candidate=candidate, pair=pair)
        amp = target

    order_log = []
    for b in range(1, n_pairs + 1):
        ramp_to(0.0, block=b, why="Returning to 0.0 mA for this block's baseline.")
        add("baseline", 0.0, baseline_s,
            f"Physiologic baseline at 0.0 mA for {baseline_s:g} s (D50, A610 p. 45). Repeated at "
            f"the start of every block so that drift in band power across the visit can be "
            f"separated from the amplitude effect; with one baseline at the start of the session, "
            f"a monotone drift would appear as an amplitude effect in whichever configurations "
            f"were tested late.",
            analysis=True, block=b, candidate=None, pair=None)

        cand_order = list(rng.permutation(n_cand))
        order_log.append([cands[j]["label"] for j in cand_order])
        for j in cand_order:
            c = cands[j]
            pair_id = f"{c['label']}#b{b}"
            roles = [("reference", c["ref_amp_mA"]), ("test", c["test_amp_mA"])]
            if randomise_within_pair and bool(rng.integers(2)):
                roles = roles[::-1]
            for role, a in roles:
                ramp_to(a, block=b, candidate=c["label"], pair=pair_id)
                add(role, a, dwell_s,
                    f"Stream {dwell_s:g} s at {a:.1f} mA on {c['label']} to estimate band power for "
                    f"the {role} arm of this block's pair (D50 specifies 30 to 45 s of streaming "
                    f"after each adjustment). The first {SETTLE_EXCLUDE_S:.3f} s are excluded, "
                    f"leaving {usable_s:.3f} s, which is {n_windows} non-overlapping "
                    f"{INTEGRATION_S:.3f} s integration windows.",
                    analysis=True, block=b, candidate=c["label"], pair=pair_id)

    restore = float(return_amp_mA) if return_amp_mA is not None else float(cands[0]["ref_amp_mA"])
    ramp_to(restore, why="Restoring the closing amplitude; the session must not end at a probe "
                         "amplitude.")
    add("restore", restore, 0.0,
        f"Session ends at {restore:.1f} mA. This is "
        + ("the amplitude requested by the caller."
           if return_amp_mA is not None
           else "the first candidate's reference amplitude, used because no closing amplitude was "
                "specified; pass return_amp_mA to end at the participant's clinical setting.")
        + " Confirm the closing programme at the programmer before the visit ends.",
        analysis=False)

    duration_min = t / 60.0
    n_measure = sum(1 for s in steps if s["analysis"] and s["role"] in ("reference", "test"))
    power = paired_power(n_pairs, float(d_target), float(alpha), n_comparisons=n_cand)
    det_d = detectable_d(n_pairs, DEFAULT_POWER_TARGET, float(alpha), n_comparisons=n_cand)

    note = _build_note(
        n_cand=n_cand, cands=cands, n_pairs=n_pairs, alpha=float(alpha), d_target=float(d_target),
        power=power, det_d=det_d, duration_min=duration_min, n_measure=n_measure,
        n_windows=n_windows, usable_s=usable_s, dwell_s=dwell_s, seed=seed,
        randomise_within_pair=bool(randomise_within_pair), order_log=order_log,
        used_zero_reference=any(abs(c["ref_amp_mA"]) < 1e-12 for c in cands))

    return types.Protocol(
        steps=steps,
        n_pairs=n_pairs,
        alpha=float(alpha),
        power=float(power),
        detectable_d=det_d,
        duration_min=float(duration_min),
        seed=seed,
        note=note,
    )


def _build_note(*, n_cand, cands, n_pairs, alpha, d_target, power, det_d, duration_min, n_measure,
                n_windows, usable_s, dwell_s, seed, randomise_within_pair, order_log,
                used_zero_reference):
    """Assemble the plan's caveat text, in one place so it cannot be omitted by a caller."""
    parts = [
        f"Randomised paired titration for {n_cand} configuration(s) over {n_pairs} blocks: "
        f"{n_measure} streaming measurements plus {n_pairs} baselines, "
        f"{duration_min:.1f} minutes of session time.",
        "The randomisation is the point of this session, not a detail of it. The historical record "
        "confounds the amplitude a participant was on with the era they were on it in, so an "
        "amplitude-to-power estimate taken from that record cannot separate the two. Randomising "
        "the order of the configurations within each block removes the systematic association "
        "between the amplitude tested and the time it was tested, which is the prerequisite that "
        "makes the amplitude-to-power edge interpretable at all.",
        f"Seed {seed} is recorded so the allocation can be audited and reproduced. "
        + ("The order of the reference and test measurement within each pair was randomised too, "
           "so that carryover from the preceding amplitude falls on both arms equally often."
           if randomise_within_pair else
           "The reference was always measured before the test within each pair, which was asked "
           "for explicitly; any carryover from the preceding amplitude now falls systematically on "
           "the reference arm."),
    ]

    if duration_min > 90:
        parts.append(
            f"AT {duration_min:.0f} MINUTES THIS DOES NOT FIT A ROUTINE VISIT. The session length "
            "is reported rather than trimmed because the trade is the clinician's: fewer blocks "
            "lowers the power stated below, fewer configurations raises it by weakening the "
            "correction, and a shorter dwell reduces the number of integration windows behind each "
            "estimate. Splitting the blocks across two visits reintroduces a between-session term "
            "that the within-session design exists to avoid, so it is a change of design and not a "
            "scheduling convenience.")
    elif duration_min > 45:
        parts.append(
            f"At {duration_min:.0f} minutes this is a long but feasible single visit, with no "
            "allowance for setup, consent, breaks or a side-effect check between steps. Add those "
            "before booking the room.")
    else:
        parts.append(
            f"At {duration_min:.0f} minutes this fits a routine visit, with no allowance for "
            "setup, consent, breaks or a side-effect check between steps.")

    parts.append(
        f"Power: {power * 100:.1f} percent to detect a paired d of {d_target} with "
        f"{n_pairs} pairs, two-sided, at a familywise alpha of {alpha} Bonferroni-corrected across "
        f"{n_cand} configuration(s), giving a per-comparison alpha of {alpha / n_cand:.4g}. "
        "Computed from the noncentral t distribution, which matters at this sample size: the normal "
        "approximation would overstate it by roughly ten percentage points.")

    if det_d is None:
        parts.append(
            f"No effect size below d = 100 reaches {DEFAULT_POWER_TARGET * 100:.0f} percent power "
            f"with {n_pairs} pairs under this correction, which means the session as configured "
            "cannot be sized to a conventional target and the number of blocks or configurations "
            "has to change.")
    else:
        parts.append(
            f"The smallest effect this session reaches {DEFAULT_POWER_TARGET * 100:.0f} percent "
            f"power for is a paired d of {det_d:.2f}. Effects smaller than that will not be "
            "reliably detected, and a null result from this session should be reported as such "
            "rather than as an absence of an amplitude effect.")

    parts.append(
        f"The d of {d_target} the session is sized for is an ASSUMPTION carried in from the "
        "historical record — the median separation observed on ONE_THREE_LEFT at 165 Hz — and that "
        "estimate rests on two eras, so era-confounding is not excluded from it. If part of that "
        "separation was era rather than amplitude, the true within-session effect is smaller and "
        "this session is underpowered for it. The power figure above is a property of the design "
        "under its assumptions and is not evidence about this participant.")

    parts.append(
        f"Each measurement contributes {n_windows} non-overlapping {INTEGRATION_S:.3f} s "
        f"integration windows ({usable_s:.1f} usable seconds of a {dwell_s:g} s dwell after the "
        f"settle exclusion). The exclusion is required because device averaging is non-overlapping "
        "(rule D14), so an estimate spanning an amplitude change still contains the previous "
        "amplitude's signal.")
    if n_windows < 4:
        parts.append(
            f"With only {n_windows} integration window(s) per measurement, the within-step estimate "
            "of band power is itself noisy, and that noise enters the paired difference as if it "
            "were biological variability. Lengthen the dwell toward the top of the permitted range "
            "before adding blocks.")

    parts.append(
        "The pairs are repeated blocks within one visit on one participant and are therefore "
        "unlikely to be fully independent; any correlation between blocks makes the effective "
        "number of pairs smaller than the count used in the power calculation, so treat the stated "
        "power as an upper bound.")

    if used_zero_reference:
        parts.append(
            "One or more candidates use a 0.0 mA reference, which is the manufacturer's own "
            "baseline. That makes those contrasts a comparison of the test amplitude against "
            "stimulation OFF, which answers whether stimulation moves the band at all, and not "
            "whether the test amplitude differs from the participant's clinical setting. Pass a "
            "per-candidate ref_amp_mA, or reference_amp_mA for the session, to ask the second "
            "question instead.")

    parts.append(
        "This is a plan and not a result. It generates no data, validates no biomarker and cannot "
        "be run retrospectively; every conclusion it is designed to support requires the session "
        "to be carried out. It also contains no clinical safety review: the amplitudes it lists "
        "must be inside limits a clinician has approved for this participant, and tolerability and "
        "side-effect monitoring at each step are outside anything this module checks.")

    parts.append("Block order: " + "; ".join(
        f"block {i + 1}: " + ", ".join(o) for i, o in enumerate(order_log[:3]))
        + ("; ..." if len(order_log) > 3 else "") + ".")

    return " ".join(parts)
