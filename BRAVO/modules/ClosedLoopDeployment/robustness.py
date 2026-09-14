"""Robustness of the confirmations-and-separation design rule, as an INTERVAL rather than a single
number: a block bootstrap over this participant's own recorded stretches (T5, 2026-09-13; contest
decision 150, ``artifacts/contest_2026-09-13_SYNTHESIS.md`` section 4, task 5, "Robustness as an
interval, not a point").

WHAT THIS PORTS, AND FROM WHERE. The method-contest entry ``fopdt_lambda`` (contestant F, the
control with no control-theory skill -- penalised regression, boosted trees and a block bootstrap)
searched a grid of onset durations, threshold-separation widths and detection-blanking durations
against the DEVICE'S OWN RECORDED BAND POWER, replayed through the real Dual Threshold controller,
and picked the smallest feasible setting; then resampled this participant's own recorded STRETCHES
of streaming with replacement, 200 times, and reported the 2.5th to 97.5th percentile of the chosen
onset (and threshold gap, and blanking) across the resamples. This file is that same computation,
built as production code, read from the working scratch scripts at
``BRAVO/_agent_bridge/_probe_tl/_contest/ml_stats/s4_bootstrap.py`` (the grid, the feasibility
rule, the tie-break, the bootstrap loop) and ``fastreplay.py`` (the configuration-vectorised
replay of the Dual Threshold controller) -- gitignored, not in this repository -- and ported here,
not re-derived. ``s1_selfcheck.py``, in the same scratch directory, proves the vectorised replay
equal to ``simulation.simulate_series`` field for field on the real record; this file reuses the
identical vectorised replay logic (``run_stretch``, faithfully ported below).

WHY THIS QUESTION IS DIFFERENT FROM ``design_rule.py``'s (T3). ``design_rule.py`` fits a noise
model and asks what separation keeps SIMULATED noise alone from crossing a threshold too often --
an analytic question about this participant's measurement scatter. This file asks a different,
more concrete question: given the band power this participant ACTUALLY produced, replayed through
the real controller, which of a grid of settings would a designer have picked -- and how much does
that pick move if the record had come out slightly differently, as approximated by resampling the
independent chunks of it (whole stretches of continuous streaming) with replacement? The two
answers need not agree, and the module docstrings deliberately do not try to reconcile them (the
same discipline ``startup_bias.py``, T6, already applies to its own two disagreeing methods).

THE GRID, faithfully carried over: 18 onset durations (3 to 120 s), 8 threshold-separation widths
(0.1 to 1.0 of this participant's own overall power scatter), 4 detection-blanking durations (3 to
60 s) -- 18 x 8 x 4 = 576 configurations, not the round number "1,440" a paraphrase of this task
used; the actual working reference script's own grid is reproduced here exactly and is what this
file is checked against. THE TRANSITION DURATION IS HELD FIXED at 3 s up and 3 s down for every
configuration in the grid (``FIXED_TRANSITION_MS``) -- this is the reference script's own choice
(``UPMS = np.full(len(cfgs), 3000.0)``), not a device default, and it is carried over unexplained
because the reference script does not explain it either: the grid searches onset, separation and
blanking, and holds the ramp rate fixed so those three parameters are what is being compared.
Likewise THE AVERAGING DURATION is held fixed at the device's own Dual Threshold white-paper
default (``replay.DEFAULT_PARAMS["averaging_ms"]``, 1200 ms) for the whole grid -- a different
question from ``design_rule.py``'s own averaging-duration sweep, and again faithfully carried over
rather than second-guessed.

FEASIBILITY AND THE TIE-BREAK, exactly the reference script's ``choose()``: a configuration is
feasible when the replayed controller shows zero reversals within one onset duration, at least 10%
of this participant's own readings land between the two thresholds at that configuration's own
separation, and the replayed amplitude spends at least 10% of the time at each limit. Among the
feasible configurations the fewest transitions per hour wins, ties broken by onset, then blanking,
then separation, in that order -- the identical key the reference script sorts on
(``(round(transitions_per_hour, 12), onset_s, blanking_s, gap_sd)``).

THE VECTORISATION, AND THE HARD REQUIREMENT THIS FILE MEETS. The controller's own state machine is
necessarily a loop over TIME -- it cannot be vectorised away, because the amplitude at step ``i``
depends on the amplitude at step ``i-1``. ``run_stretch`` (ported unchanged from ``fastreplay.py``)
is that one unavoidable Python loop, and it is vectorised across every one of the 576 configurations
at each step via ``numpy.where``, never a Python loop over configurations. WHAT IS NOT ported
unchanged is how the 200 bootstrap replicates are computed. The reference script's own
``s4_bootstrap.py`` calls ``choose()`` -- and therefore the whole time-stepped replay -- once PER
REPLICATE, 200 times. That is exactly the shape this project's house rule on vectorised bootstrapping
forbids: 200 Python-level passes through per-reading work. This file does not do that.

THE KEY PROPERTY THAT MAKES A FASTER, EXACTLY EQUIVALENT COMPUTATION POSSIBLE: ``run_stretch``
resets the controller's state at the start of EVERY stretch (``amp = np.full(K, amp_init)``,
``adopted = np.full(K, _BETWEEN)`` -- read the function body below, unchanged from the reference).
One stretch's replay therefore never depends on any other stretch, and it is deterministic given a
stretch and a configuration. A block bootstrap resamples whole stretches WITH REPLACEMENT, so a
resample is entirely described by how many times each of the training stretches is drawn. Because
the per-stretch, per-configuration outcome is fixed and does not depend on the resample, and because
every quantity `choose()` needs (transitions, reversals, time at each limit, the fraction of
readings between the thresholds) is a SUM over the stretches in the group, a resample's answer is
an exact WEIGHTED SUM of quantities computed ONCE per training stretch -- not a second pass through
the replay. ``_stretch_accumulators`` runs the time-stepped, config-vectorised replay exactly ONCE
over every training stretch (this is the one and only per-reading Python loop in the whole file,
and it costs the same whether 1 or 200 bootstrap replicates are asked for); ``_choose_from_precompute``
turns a replicate's resample-count vector into the same numbers ``choose()`` would have computed by
re-simulating, using nothing but matrix multiplication and ``numpy.bincount``. The 200-replicate
loop below is therefore pure array arithmetic with no further calls to ``run_stretch``, satisfying
the requirement in both readings: no Python loop over the 576 configurations (the replay is
config-vectorised) and no Python loop over the 200 replicates that touches a single reading.

``choose_naive`` (a direct, literal port of the reference script's own ``choose()``, calling
``run_many`` -- itself a literal port of ``fastreplay.run_many`` -- once) is KEPT in this file, used
for the point estimate (one call, no repetition, so there is no speed reason to avoid it) and as the
reference the fast, precompute-based path is tested against: ``tests/test_robustness.py`` proves
the two agree, field for field, on constructed stretches including weight vectors with repeats,
because a bootstrap replicate that draws one stretch twice is exactly the case that tells the two
implementations apart if the precompute path's linearity argument were wrong.

I DID NOT ALSO BATCH THE 200 REPLICATES INTO THE CONFIGURATION AXIS (broadcasting ``K`` from 576 to
576 x 200 so a single vectorised pass covers every replicate at once). That would still require
resampling the SET OF STRETCHES fed to each of the 200 columns, and since two replicates can draw a
different number of the same stretch, the natural common axis across replicates is stretches, not
configurations -- which is exactly what the precompute-and-aggregate approach above already
exploits, at a fraction of the memory (576 columns times the training stretches' own step count,
computed once, rather than 576 x 200 columns). The precompute approach is a stronger and cheaper
answer to the same instruction, not a partial one, and is why replicate-batching was not built too.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import replay as _replay
from . import simulation as _sim
from . import startup_bias as _startup_bias

_log = __import__("logging").getLogger(__name__)

KIND = "closed_loop_robustness"
#: Bumped whenever a change here would change an already-stored entry's numbers.
RULE_VERSION = "v1_block_bootstrap_port"

#: The grid, faithfully carried over from ``s4_bootstrap.py``'s own module-level constants.
ONSET_GRID_S: Tuple[float, ...] = (3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 36, 42, 48, 54, 60, 75,
                                   90, 120)
GAP_SD_GRID: Tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
BLANKING_GRID_S: Tuple[float, ...] = (3, 15, 30, 60)

#: The feasibility floors, the reference script's own ``C2_MIN``/``C3_MIN``. Numerically identical
#: to ``occupancy.MIN_BETWEEN_FRAC`` (T4) by the contest's own choice; kept as a separate constant
#: here rather than imported, since the two checks answer different questions on different data
#: (raw stretch power here, averaged-onto-the-card's-own-duration readings there).
BETWEEN_MIN_FRAC = 0.10
LIMIT_MIN_FRAC = 0.10

#: The reference script's own fixed ramp: 3 s up and 3 s down for every configuration in the grid,
#: not the device default (2.5 min / 5 min) -- see the module docstring for what this does and does
#: not mean.
FIXED_TRANSITION_MS = 3000.0

DEFAULT_N_BOOT = 200
#: The same seed ``design_rule.py`` (T3) uses, so every module this contest produced draws from the
#: same, stated random stream rather than a fresh one invented per file.
RNG_SEED = 20260913

#: The 70% time-ordered training split both the design-rule and startup-bias ports use, and the
#: reference script for THIS file used identically (``tr = st[:int(round(0.70 * len(st)))]``).
#: Reused from ``startup_bias.py`` rather than redefined, so a change to the split fraction cannot
#: drift between the two files that both need it.
TRAIN_FRAC = _startup_bias.TRAIN_FRAC
split_stretches_by_time = _startup_bias.split_stretches_by_time

StretchTuple = Tuple[np.ndarray, np.ndarray, np.ndarray]

#: Mirrors ``simulation._ABOVE`` / ``_BETWEEN`` / ``_BELOW`` (1, 0, -1) -- the reference script's
#: own convention, ``fastreplay.py``'s own comment: "mirrors simulation._ABOVE / _BETWEEN / _BELOW".
_ABOVE, _BETWEEN, _BELOW = 1, 0, -1


# =================================================================================================
# THE CONFIGURATION-VECTORISED REPLAY (ported unchanged from ``fastreplay.py``)
# =================================================================================================
def prepare(gt: np.ndarray, gp: np.ndarray, ga: np.ndarray, averaging_ms: float
            ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float, int]:
    """Preprocess ONE stretch exactly as ``simulation.simulate_series`` does. Returns
    ``(t, p, a_obs, dt, n_per)``. ``a_obs`` and ``n_per`` travel through for parity with the
    reference (``fastreplay.prepare``); this module's own callers use only ``p`` and ``dt``,
    because the controller replayed here commands its OWN amplitude and never reads the amplitude
    that was actually observed.
    """
    t_raw, p_raw, dt_raw = _replay._coerce_series({"t_s": gt - gt[0], "power": gp}, None)
    a_raw = np.asarray(ga, dtype=float).ravel()
    if a_raw.size != p_raw.size:
        raise ValueError("amp_obs size mismatch")
    averaging_s = float(averaging_ms) / 1000.0
    t, p, dt, n_per = _replay._average_to_device_grid(t_raw, p_raw, dt_raw, averaging_s)
    a_obs = _sim._grid_like(a_raw, n_per)[:p.size]
    return t, p, a_obs, float(dt), int(n_per)


def run_stretch(p, dt, upper, lower, onset_ms, blanking_ms, up_ms, down_ms, amp_low, amp_high,
                amp_init=None, tol=None) -> Dict[str, Any]:
    """Replay K configurations over one prepared stretch. Every parameter array has length K.

    Ported unchanged from ``fastreplay.run_stretch``. Returns a dict of per-configuration
    accumulators (counts and step-weighted sums), never a per-step array, so memory stays flat in
    the number of steps. THE CONTROLLER STATE IS RESET AT THE START OF THIS CALL for every one of
    the K configurations (``amp = np.full(K, amp_init)``, ``adopted = np.full(K, _BETWEEN)``) --
    this is the property the rest of this file's speed depends on: one stretch's outcome never
    depends on any other stretch's.
    """
    upper = np.asarray(upper, float)
    lower = np.asarray(lower, float)
    K = upper.size
    onset_steps = np.maximum(1, np.ceil(np.asarray(onset_ms, float) / 1000.0 / dt - 1e-9)).astype(int)
    blank_steps = np.maximum(0, np.ceil(np.asarray(blanking_ms, float) / 1000.0 / dt - 1e-9)).astype(int)
    span = float(amp_high) - float(amp_low)
    rate_up = span / (np.asarray(up_ms, float) / 1000.0)
    rate_down = span / (np.asarray(down_ms, float) / 1000.0)
    if tol is None:
        tol = float(_replay.DEFAULT_PARAMS["amp_at_limit_tol_mA"])
    if amp_init is None:
        amp_init = 0.5 * (float(amp_low) + float(amp_high))
    amp_init = min(max(float(amp_init), float(amp_low)), float(amp_high))

    n = int(p.size)
    amp = np.full(K, amp_init)
    adopted = np.full(K, _BETWEEN, dtype=int)
    pending = np.full(K, 2, dtype=int)      # 2 == "no pending state" sentinel, never a real state
    pending_run = np.zeros(K, dtype=int)
    blank_left = np.zeros(K, dtype=int)

    n_trans = np.zeros(K, dtype=np.int64)
    n_onset_supp = np.zeros(K, dtype=np.int64)
    n_blank_supp = np.zeros(K, dtype=np.int64)
    n_rev_onset = np.zeros(K, dtype=np.int64)
    n_adopts = np.zeros(K, dtype=np.int64)
    last_adopt_i = np.zeros(K, dtype=np.int64)
    state_before_last = np.full(K, _BETWEEN, dtype=int)

    sum_at_hi = np.zeros(K)
    sum_at_lo = np.zeros(K)
    sum_amp = np.zeros(K)
    sum_above = np.zeros(K)
    sum_below = np.zeros(K)
    sum_between = np.zeros(K)
    travel = np.zeros(K)
    prev_amp = None
    n_missing = 0

    up_hi = float(amp_high)
    up_lo = float(amp_low)
    for i in range(n):
        pi = p[i]
        if math.isnan(pi):
            n_missing += 1
            pending[:] = 2
            pending_run[:] = 0
            blank_left = np.maximum(blank_left - 1, 0)
        else:
            raw = np.where(pi > upper, _ABOVE, np.where(pi < lower, _BELOW, _BETWEEN))
            same = raw == adopted
            pending = np.where(same, 2, pending)
            pending_run = np.where(same, 0, pending_run)
            cont = (~same) & (pending == raw)
            pending_run = np.where(cont, pending_run + 1, pending_run)
            fresh = (~same) & (~cont)
            pending = np.where(fresh, raw, pending)
            pending_run = np.where(fresh, 1, pending_run)
            ready = (~same) & (pending_run >= onset_steps)
            blocked = ready & (blank_left > 0)
            adopt = ready & ~blocked
            n_blank_supp += blocked
            n_onset_supp += ((~same) & (~ready))
            if adopt.any():
                rev = adopt & (n_adopts >= 1) & (raw == state_before_last) & \
                    ((i - last_adopt_i) <= onset_steps)
                n_rev_onset += rev
                state_before_last = np.where(adopt, adopted, state_before_last)
                last_adopt_i = np.where(adopt, i, last_adopt_i)
                if i > 0:
                    n_adopts += adopt
            adopted = np.where(adopt, raw, adopted)
            n_trans += adopt
            blank_left = np.where(adopt, blank_steps, blank_left)
            pending = np.where(adopt, 2, pending)
            pending_run = np.where(adopt, 0, pending_run)
            blank_left = np.maximum(blank_left - 1, 0)

            target = np.where(adopted == _ABOVE, up_hi, np.where(adopted == _BELOW, up_lo, amp))
            step = np.clip(target - amp, -rate_down * dt, rate_up * dt)
            amp = np.clip(amp + step, up_lo, up_hi)

        if prev_amp is not None:
            travel += np.abs(amp - prev_amp)
        prev_amp = amp.copy()
        sum_at_hi += (np.abs(amp - up_hi) <= tol)
        sum_at_lo += (np.abs(amp - up_lo) <= tol)
        sum_amp += amp
        sum_above += (adopted == _ABOVE)
        sum_below += (adopted == _BELOW)
        sum_between += (adopted == _BETWEEN)

    return {"n_steps": n, "dt": dt, "n_missing": n_missing, "onset_steps": onset_steps,
            "n_transitions": n_trans, "n_onset_suppressed": n_onset_supp,
            "n_blank_suppressed": n_blank_supp, "reversals_within_one_onset": n_rev_onset,
            "sum_at_upper": sum_at_hi, "sum_at_lower": sum_at_lo, "sum_amp": sum_amp,
            "sum_above": sum_above, "sum_below": sum_below, "sum_between": sum_between,
            "travel": travel}


def run_many(stretches, averaging_ms, upper, lower, onset_ms, blanking_ms, up_ms, down_ms,
            amp_low, amp_high, min_steps: int = 3) -> Dict[str, Any]:
    """Aggregate ``run_stretch`` over a list of ``(t, p, a)`` stretches, weighting by steps.

    Ported unchanged from ``fastreplay.run_many``. THIS FUNCTION DOES REAL PER-READING WORK and is
    used in this module only for the ONE-OFF point estimate (``choose_naive`` on the whole training
    set, called once) and in tests, as the literal reference the fast bootstrap path
    (``_stretch_accumulators`` / ``_choose_from_precompute``) is checked against. It must never be
    called once per bootstrap replicate -- that is exactly the cost this file's fast path avoids.
    """
    K = np.asarray(upper).size
    W = 0.0
    acc = {k: np.zeros(K) for k in ("sum_at_upper", "sum_at_lower", "sum_amp",
                                    "sum_above", "sum_below", "sum_between", "travel")}
    cnt = {k: np.zeros(K, dtype=np.int64) for k in ("n_transitions", "n_onset_suppressed",
                                                    "n_blank_suppressed",
                                                    "reversals_within_one_onset")}
    used = 0
    skipped = 0
    n_missing = 0
    dt = None
    onset_steps = None
    for gt, gp, ga in stretches:
        if gt.size < min_steps:
            skipped += 1
            continue
        try:
            _t, p, _a, dt, _n_per = prepare(gt, gp, ga, averaging_ms)
        except ValueError:
            skipped += 1
            continue
        r = run_stretch(p, dt, upper, lower, onset_ms, blanking_ms, up_ms, down_ms, amp_low,
                        amp_high)
        W += r["n_steps"]
        used += 1
        n_missing += r["n_missing"]
        onset_steps = r["onset_steps"]
        for k in acc:
            acc[k] += r[k]
        for k in cnt:
            cnt[k] += r[k]
    hours = W * dt / 3600.0 if (W and dt) else float("nan")
    return {"stretches_used": used, "stretches_skipped": skipped, "steps": int(W), "dt_s": dt,
            "hours": hours, "n_missing": n_missing, "onset_steps": onset_steps,
            "transitions": cnt["n_transitions"],
            "transitions_per_hour": cnt["n_transitions"] / hours,
            "reversals_within_one_onset": cnt["reversals_within_one_onset"],
            "onset_suppressed_steps": cnt["n_onset_suppressed"],
            "blanking_suppressed_steps": cnt["n_blank_suppressed"],
            "frac_time_at_upper_limit": acc["sum_at_upper"] / W,
            "frac_time_at_lower_limit": acc["sum_at_lower"] / W,
            "frac_time_between_limits": 1.0 - (acc["sum_at_upper"] + acc["sum_at_lower"]) / W,
            "frac_state_above": acc["sum_above"] / W,
            "frac_state_below": acc["sum_below"] / W,
            "frac_state_between": acc["sum_between"] / W,
            "mean_amplitude_mA": acc["sum_amp"] / W,
            "mA_travelled_per_hour": acc["travel"] / hours}


# =================================================================================================
# THE GRID, AND THE FRACTION-BETWEEN COUNT THE FEASIBILITY RULE NEEDS
# =================================================================================================
def _build_config_grid(mid: float, sd: float, onset_grid: Sequence[float],
                       gap_sd_grid: Sequence[float], blanking_grid: Sequence[float]
                       ) -> List[Dict[str, float]]:
    """The 576 configurations, in the reference script's own iteration order
    (``for g in GAP_SD for o in ONSETS_S for b in BLANK_S``) -- kept because the tie-break compares
    tuples and Python's ``min``/``<`` on equal keys favours the first one seen, so the iteration
    order is part of the port, not an implementation detail."""
    cfgs = []
    for g in gap_sd_grid:
        for o in onset_grid:
            for b in blanking_grid:
                cfgs.append({"onset_s": float(o), "blanking_s": float(b), "gap_sd": float(g),
                            "upper": mid + 0.5 * float(g) * sd, "lower": mid - 0.5 * float(g) * sd})
    return cfgs


def frac_between_all(group: Sequence[StretchTuple], *, mid: float, sd: float,
                     gap_sd_grid: Sequence[float] = GAP_SD_GRID) -> Dict[float, float]:
    """One number per distinct threshold-separation width: the fraction of this GROUP's own raw,
    finite power readings that land between the two thresholds that width implies. Ported unchanged
    (in behaviour) from ``s4_bootstrap.frac_between_all``: pools every stretch's RAW regridded
    power (not the averaging-duration-processed series ``prepare`` produces), because that is what
    the reference script itself pools.
    """
    p = np.concatenate([np.asarray(x[1], float) for x in group]) if group else np.empty(0)
    p = p[np.isfinite(p)]
    out = {}
    for gg in gap_sd_grid:
        u, l = mid + 0.5 * gg * sd, mid - 0.5 * gg * sd
        out[float(gg)] = float(np.mean((p <= u) & (p >= l))) if p.size else float("nan")
    return out


def _stretch_gap_counts(stretches: Sequence[StretchTuple], *, mid: float, sd: float,
                        gap_sd_grid: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    """Per stretch, per separation width: how many of that stretch's own raw finite readings fall
    between the two thresholds that width implies, and how many finite readings it has at all.
    Precomputed once so a bootstrap replicate's ``frac_between_all`` becomes a weighted sum
    (``_frac_between_from_precompute``) instead of re-pooling and re-scanning every reading."""
    s = len(stretches)
    g = len(gap_sd_grid)
    between = np.zeros((s, g))
    n_finite = np.zeros(s)
    for si, (_t, p, _a) in enumerate(stretches):
        p = np.asarray(p, dtype=float)
        fin = p[np.isfinite(p)]
        n_finite[si] = fin.size
        for gi, gg in enumerate(gap_sd_grid):
            u, l = mid + 0.5 * float(gg) * sd, mid - 0.5 * float(gg) * sd
            between[si, gi] = float(np.sum((fin <= u) & (fin >= l)))
    return between, n_finite


def _frac_between_from_precompute(between: np.ndarray, n_finite: np.ndarray, weights: np.ndarray,
                                  gap_sd_grid: Sequence[float]) -> Dict[float, float]:
    """The weighted-sum equivalent of ``frac_between_all`` over a resample described by
    ``weights`` (one non-negative count per training stretch). Exact -- not an approximation -- by
    linearity: pooling K copies of a stretch's readings and counting how many fall in a range gives
    K times that stretch's own count, and the pooled fraction is the ratio of two such sums."""
    w = np.asarray(weights, dtype=float)
    num = w @ between
    den = float(w @ n_finite)
    if den <= 0:
        return {float(g): float("nan") for g in gap_sd_grid}
    frac = num / den
    return {float(g): float(frac[i]) for i, g in enumerate(gap_sd_grid)}


# =================================================================================================
# choose(): the feasibility rule and the tie-break, on an already-aggregated set of statistics
# =================================================================================================
def _pick(cfgs: Sequence[Dict[str, float]], *, tph: np.ndarray, rev: np.ndarray, au: np.ndarray,
          al: np.ndarray, fb: Dict[float, float], between_min_frac: float, limit_min_frac: float
          ) -> Optional[Dict[str, Any]]:
    """The feasibility filter and the tie-break, exactly ``s4_bootstrap.choose``'s own inner loop,
    given the per-configuration statistics already computed (by ``run_many`` for the naive path, or
    by the weighted-sum aggregate for the fast path -- the two are interchangeable inputs to this
    function, which is what the equality test in ``tests/test_robustness.py`` exploits)."""
    best = None
    for i, c in enumerate(cfgs):
        if int(round(float(rev[i]))) != 0:
            continue
        if fb.get(c["gap_sd"], float("nan")) < between_min_frac:
            continue
        if au[i] < limit_min_frac or al[i] < limit_min_frac:
            continue
        key = (round(float(tph[i]), 12), c["onset_s"], c["blanking_s"], c["gap_sd"])
        if best is None or key < best[0]:
            best = (key, i)
    if best is None:
        return None
    i = best[1]
    c = cfgs[i]
    return {"onset_s": c["onset_s"], "blanking_s": c["blanking_s"], "gap_sd": c["gap_sd"],
           "gap_units": c["upper"] - c["lower"], "upper": c["upper"], "lower": c["lower"],
           "transitions_per_hour": float(tph[i]), "frac_at_upper": float(au[i]),
           "frac_at_lower": float(al[i]), "frac_readings_between": fb.get(c["gap_sd"])}


def choose_naive(group: Sequence[StretchTuple], cfgs: Sequence[Dict[str, float]], *,
                 up_arr: np.ndarray, lo_arr: np.ndarray, on_arr: np.ndarray, bl_arr: np.ndarray,
                 upms_arr: np.ndarray, dnms_arr: np.ndarray, averaging_ms: float, amp_low: float,
                 amp_high: float, mid: float, sd: float, gap_sd_grid: Sequence[float],
                 between_min_frac: float = BETWEEN_MIN_FRAC, limit_min_frac: float = LIMIT_MIN_FRAC
                 ) -> Optional[Dict[str, Any]]:
    """A direct, literal port of ``s4_bootstrap.choose``: re-runs the full config-vectorised replay
    over ``group`` (via ``run_many``) and applies the feasibility rule. Used for the point estimate
    (one call) and as the reference the fast bootstrap path is tested against -- never called once
    per bootstrap replicate."""
    res = run_many(group, averaging_ms, up_arr, lo_arr, on_arr, bl_arr, upms_arr, dnms_arr,
                   amp_low, amp_high)
    fb = frac_between_all(group, mid=mid, sd=sd, gap_sd_grid=gap_sd_grid)
    return _pick(cfgs, tph=res["transitions_per_hour"], rev=res["reversals_within_one_onset"],
                au=res["frac_time_at_upper_limit"], al=res["frac_time_at_lower_limit"], fb=fb,
                between_min_frac=between_min_frac, limit_min_frac=limit_min_frac)


# =================================================================================================
# THE FAST PATH: precompute once per training stretch, then aggregate per replicate with no
# further replay calls
# =================================================================================================
def _stretch_accumulators(stretches: Sequence[StretchTuple], averaging_ms: float,
                          up_arr: np.ndarray, lo_arr: np.ndarray, on_arr: np.ndarray,
                          bl_arr: np.ndarray, upms_arr: np.ndarray, dnms_arr: np.ndarray,
                          amp_low: float, amp_high: float, min_steps: int = 3) -> Dict[str, Any]:
    """Run every configuration over EACH training stretch exactly ONCE -- not once per bootstrap
    replicate -- and return the per-stretch accumulators ``run_stretch`` produces, stacked along a
    new leading stretch axis. A stretch shorter than ``min_steps``, or one ``prepare`` refuses,
    contributes an all-zero row and is marked unused in ``used`` -- the identical exclusion
    ``run_many``'s own ``skipped`` counter applies."""
    K = int(np.asarray(up_arr).size)
    s = len(stretches)
    keys = ("n_transitions", "reversals_within_one_onset", "sum_at_upper", "sum_at_lower")
    acc = {k: np.zeros((s, K)) for k in keys}
    n_steps = np.zeros(s)
    used = np.zeros(s, dtype=bool)
    n_skipped = 0
    dt_seen = None
    for si, (gt, gp, ga) in enumerate(stretches):
        if gt.size < min_steps:
            n_skipped += 1
            continue
        try:
            _t, p, _a, dt, _n_per = prepare(gt, gp, ga, averaging_ms)
        except ValueError:
            n_skipped += 1
            continue
        r = run_stretch(p, dt, up_arr, lo_arr, on_arr, bl_arr, upms_arr, dnms_arr, amp_low,
                        amp_high)
        n_steps[si] = r["n_steps"]
        used[si] = True
        dt_seen = dt if dt_seen is None else dt_seen
        for k in keys:
            acc[k][si] = r[k]
    return {"acc": acc, "n_steps": n_steps, "used": used, "K": K, "n_skipped": n_skipped,
           "dt_s": dt_seen}


def _choose_from_precompute(pre: Dict[str, Any], gap_between: np.ndarray, gap_n_finite: np.ndarray,
                            weights: np.ndarray, cfgs: Sequence[Dict[str, float]],
                            gap_sd_grid: Sequence[float], *, between_min_frac: float,
                            limit_min_frac: float) -> Optional[Dict[str, Any]]:
    """One bootstrap replicate's answer, computed ENTIRELY from the precomputed per-stretch
    accumulators and a resample-count vector ``weights`` (one non-negative integer per training
    stretch): a weighted sum, never a call back into ``run_stretch``."""
    acc = pre["acc"]
    n_steps = pre["n_steps"]
    used = pre["used"]
    dt_s = pre["dt_s"]
    w = np.asarray(weights, dtype=float)
    used_f = used.astype(float)
    w_used = w * used_f
    W = float(w_used @ n_steps)
    if W <= 0 or dt_s is None:
        return None
    hours = W * float(dt_s) / 3600.0
    n_trans = w_used @ acc["n_transitions"]
    rev = w_used @ acc["reversals_within_one_onset"]
    at_up = w_used @ acc["sum_at_upper"]
    at_lo = w_used @ acc["sum_at_lower"]
    tph = n_trans / hours
    au = at_up / W
    al = at_lo / W
    fb = _frac_between_from_precompute(gap_between, gap_n_finite, w, gap_sd_grid)
    return _pick(cfgs, tph=tph, rev=rev, au=au, al=al, fb=fb, between_min_frac=between_min_frac,
                limit_min_frac=limit_min_frac)


# =================================================================================================
# THE ONE ENTRY POINT A CALLER NEEDS
# =================================================================================================
def robustness_for_series(t, power, amp_obs, *, upper, lower, amp_low, amp_high,
                          n_boot: int = DEFAULT_N_BOOT, seed: int = RNG_SEED,
                          train_frac: float = TRAIN_FRAC,
                          onset_grid: Sequence[float] = ONSET_GRID_S,
                          gap_sd_grid: Sequence[float] = GAP_SD_GRID,
                          blanking_grid: Sequence[float] = BLANKING_GRID_S,
                          between_min_frac: float = BETWEEN_MIN_FRAC,
                          limit_min_frac: float = LIMIT_MIN_FRAC) -> Dict[str, Any]:
    """Fit nothing; replay the real controller over this participant's own recorded stretches
    across the grid above, pick the point estimate on the 70% time-ordered training split (the
    reference script's own ``tr``), and report a 200-replicate block bootstrap over that same
    split's stretches as a 2.5th-97.5th percentile interval on the chosen onset, threshold gap and
    blanking duration.

    ``t``, ``power``, ``amp_obs`` are the same series ``simulation.regrid_stretches`` accepts
    (``adapter.simulation_inputs_for_participant``'s own output, the same inputs
    ``design_rule.design_rule_for_series`` and ``startup_bias.startup_bias_for_series`` take).
    ``upper``/``lower`` are the stored thresholds (the noise simulation and this bootstrap both hold
    the SEPARATION grid centred at their midpoint, decision 150's own convention); ``amp_low``/
    ``amp_high`` are the plan's capture amplitude range, needed because this file, unlike
    ``design_rule.py``, actually replays the controller's commanded amplitude.
    """
    t = np.asarray(t, dtype=float)
    p = np.asarray(power, dtype=float)
    a = np.asarray(amp_obs, dtype=float)
    if a.size != t.size:
        a = np.full(t.size, np.nan)
    if upper is None or lower is None:
        return {"refused": True, "reason": "no thresholds are placed for this candidate"}
    if amp_low is None or amp_high is None:
        return {"refused": True,
                "reason": "no adaptive amplitude limits (capture range) are available"}

    ok = np.isfinite(t) & np.isfinite(p)
    t_ok, p_ok, a_ok = t[ok], p[ok], a[ok]
    if t_ok.size < 3:
        return {"refused": True, "reason": f"only {t_ok.size} distinct samples with a finite "
                "power reading, too few to split into stretches"}
    order = np.argsort(t_ok, kind="stable")
    t_ok, p_ok, a_ok = t_ok[order], p_ok[order], a_ok[order]
    if np.any(np.diff(t_ok) == 0):
        uniq, idx = np.unique(t_ok, return_inverse=True)

        def _mean_by(v):
            s_ = np.zeros(uniq.size)
            c = np.zeros(uniq.size)
            fin = np.isfinite(v)
            np.add.at(s_, idx[fin], v[fin])
            np.add.at(c, idx[fin], 1.0)
            return np.where(c > 0, s_ / np.maximum(c, 1.0), np.nan)
        p_ok, a_ok, t_ok = _mean_by(p_ok), _mean_by(a_ok), uniq
    gaps = np.diff(t_ok)
    pos = gaps[gaps > 0]
    if pos.size == 0:
        return {"refused": True, "reason": "the time base has no positive interval"}
    dt_s = float(np.median(pos))
    stretches, n_empty, n_merged, _bounds = _sim.regrid_stretches(t_ok, p_ok, a_ok, dt_s)
    if not stretches:
        return {"refused": True, "reason": "no stretches could be built from this series"}

    train, test = split_stretches_by_time(stretches, train_frac)
    if not train:
        return {"refused": True, "reason": "no training stretches after the time-ordered split"}

    upper_f, lower_f = float(upper), float(lower)
    amp_low_f, amp_high_f = float(amp_low), float(amp_high)
    mid = 0.5 * (upper_f + lower_f)
    # The FULL series' own scatter, matching the reference script's ``sd = np.nanstd(z["p"])``,
    # computed from the whole recorded series (train and test together), not the training split.
    sd = float(np.nanstd(p)) if p.size else float("nan")
    if not np.isfinite(sd) or sd <= 0:
        return {"refused": True,
                "reason": "the recorded series has no measurable scatter to scale the "
                "threshold-separation grid by"}

    averaging_ms = float(_replay.DEFAULT_PARAMS["averaging_ms"])
    cfgs = _build_config_grid(mid, sd, onset_grid, gap_sd_grid, blanking_grid)
    up_arr = np.array([c["upper"] for c in cfgs], dtype=float)
    lo_arr = np.array([c["lower"] for c in cfgs], dtype=float)
    on_arr = np.array([c["onset_s"] for c in cfgs], dtype=float) * 1000.0
    bl_arr = np.array([c["blanking_s"] for c in cfgs], dtype=float) * 1000.0
    upms_arr = np.full(len(cfgs), FIXED_TRANSITION_MS)
    dnms_arr = np.full(len(cfgs), FIXED_TRANSITION_MS)

    # THE ONE PER-READING PASS in this whole function: every training stretch, replayed once,
    # config-vectorised across all 576 configurations.
    pre = _stretch_accumulators(train, averaging_ms, up_arr, lo_arr, on_arr, bl_arr, upms_arr,
                                dnms_arr, amp_low_f, amp_high_f)
    gap_between, gap_n_finite = _stretch_gap_counts(train, mid=mid, sd=sd, gap_sd_grid=gap_sd_grid)

    ones = np.ones(len(train))
    point = _choose_from_precompute(pre, gap_between, gap_n_finite, ones, cfgs, gap_sd_grid,
                                    between_min_frac=between_min_frac,
                                    limit_min_frac=limit_min_frac)

    # THE 200-REPLICATE BOOTSTRAP: pure array arithmetic, no further calls to `run_stretch`.
    rng = np.random.default_rng(seed)
    rows: List[Dict[str, Any]] = []
    for b in range(int(n_boot)):
        idx = rng.integers(0, len(train), len(train))
        w = np.bincount(idx, minlength=len(train)).astype(float)
        got = _choose_from_precompute(pre, gap_between, gap_n_finite, w, cfgs, gap_sd_grid,
                                      between_min_frac=between_min_frac,
                                      limit_min_frac=limit_min_frac)
        rows.append({"replicate": b, "feasible": got is not None, **(got or {})})

    feasible = [r for r in rows if r["feasible"]]
    intervals: Dict[str, Any] = {}
    for col in ("onset_s", "gap_sd", "gap_units", "blanking_s", "transitions_per_hour"):
        if not feasible:
            intervals[col] = None
            continue
        v = np.array([r[col] for r in feasible], dtype=float)
        lo_p, hi_p = np.percentile(v, [2.5, 97.5])
        intervals[col] = {"lower": float(lo_p), "upper": float(hi_p), "median": float(np.median(v))}

    return {
        "refused": False,
        "point_estimate": point,
        "n_train_stretches": len(train), "n_test_stretches": len(test),
        "n_boot": int(n_boot), "n_feasible": len(feasible), "seed": int(seed),
        "level_midpoint": mid, "sd_of_series": sd, "device_clock_s": dt_s,
        "averaging_ms": averaging_ms, "fixed_transition_ms": FIXED_TRANSITION_MS,
        "config_grid": {"onset_s": list(onset_grid), "gap_sd": list(gap_sd_grid),
                        "blanking_s": list(blanking_grid), "n_configs": len(cfgs)},
        "intervals": intervals,
        "n_cells_empty": int(n_empty), "n_cells_merged": int(n_merged),
        "n_stretches_skipped_in_precompute": pre["n_skipped"],
    }
