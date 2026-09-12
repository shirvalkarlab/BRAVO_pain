"""The closed-loop simulation: the device's Dual Threshold controller run over this participant's
own recorded band power, WITH the band's response to the amplitude the controller commands fed
back in (redesign plan Phase 8, decisions 15-21; design in
artifacts/design_2026-09-11_closed_loop_simulation_module.md).

WHAT THE REPLAY LACKS AND THIS ADDS. `replay.dual_threshold` runs the control law over a power
series recorded while the amplitude followed the participant's actual programming, and says in
every result that it assumes the same power would have occurred under closed-loop control. That is
false exactly when the band responds to amplitude, which is the premise of deploying it. Here the
controller's commanded amplitude moves the power it is watching:

    p_sim[i] = p_obs[i] + delta[i]
    delta[i] = delta[i-1] + (g(a_sim[i]) - g(a_obs[i]) - delta[i-1]) * (1 - exp(-dt / tau))

`g` is the fitted response curve (`StimOptimizer.routines.amplitude_response.ResponseCurve`),
`a_obs` the amplitude the device was delivering when `p_obs` was recorded, `tau` the settling time.
The offset formulation is the reason M0 is exact: with the zero curve the target is always zero,
delta never leaves zero, and `p_sim == p_obs` to the last bit, so the coupled loop reproduces the
replay's arithmetic rather than approximating it (test 1 of the design).

THE MODELS, one loop, run side by side as replicates of a vectorised controller:
  M0  the zero curve -- the replay as it is, kept as the reference;
  M1  the pooled straight line of the stored row (decision 103), the default today;
  M2  the fitted quadratic with the post-peak line, only when the stored row has an established
      bend (`curves`) -- decision 11's pivot, "not assessable" on RCS08 today;
  M3  the active model rerun with the curve refitted on runs resampled WITH REPLACEMENT (runs,
      never points: six settings on one visit are not six visits), giving an interval on every
      number.

WHAT IT REFUSES, exactly as the replay does: a series whose sample interval cannot resolve the
device's ramp (chronic snapshots minutes apart), too few steps, a plan with no thresholds or no
capture range. Amplitude limits are HELD to the capture range (decision 16). The wrong-side-of-
the-peak time is a number with a warning line and gates nothing (decision 17).

It gates nothing. `gates_nothing` is on every payload and no verdict on the page reads it.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from StimOptimizer.routines import percept_adaptive
from StimOptimizer.routines import within_visit as _wv
from StimOptimizer.routines.amplitude_response import ResponseCurve, NONE, LINEAR, QUADRATIC

from . import replay as _replay

KIND = "closed_loop_simulation"
#: Bumped whenever the numbers a stored entry holds would change: v2 put the pieces on the device
#: clock before the loop (regrid_stretches), which admitted 114 stretches where v1 ran 16.
RULE_VERSION = "v4_simulation_candidate_tag"   # v4: the sidecar names the candidate; untagged entries are unreadable

#: The settling time when no run supports a measured one (decision 15): the settled window the
#: three-source comparison already trusts (`within_visit.PRE_CHANGE_WINDOW_S`, 30 s).
DEFAULT_TAU_S = 30.0

#: How many run-resampled replicates M3 runs (decision 18: on every page load, if cheap). Each
#: replicate is one column of the vectorised controller, so the cost is one loop over the series.
DEFAULT_N_RESAMPLE = 200

#: Below this many distinct runs, resampling runs cannot give an interval worth the name.
MIN_RUNS_FOR_RESAMPLE = 3

#: Points kept per drawn trajectory. The page draws the longest contiguous stretch; a 3 s series
#: over ten minutes is 200 controller steps, so this is rarely reached.
MAX_TRAJECTORY_POINTS = 800

_ABOVE, _BETWEEN, _BELOW, _NONE = 1, 0, -1, 2

CAVEAT = ("The model of how this band's power responds to amplitude is a curve fitted to N settled "
          "points across V runs of rising current on this contact; it has not been observed under "
          "closed-loop control. The amplitude trajectory is what the device's control law does to "
          "that model, not a prediction of what the device would deliver.")


# --------------------------------------------------------------------------------------------
# The curves as arrays, so K replicates evaluate in one numpy call
# --------------------------------------------------------------------------------------------
def _bank(curves: Sequence[ResponseCurve]) -> Dict[str, np.ndarray]:
    K = len(curves)
    kind = np.array([{NONE: 0, LINEAR: 1, QUADRATIC: 2}[c.kind] for c in curves], dtype=int)
    f = lambda name: np.array([float(getattr(c, name)) for c in curves], dtype=float)  # noqa: E731
    return {"K": K, "kind": kind, "slope": np.nan_to_num(f("slope_per_mA")),
            "a": np.nan_to_num(f("quad_per_mA2")), "b": np.nan_to_num(f("quad_lin_per_mA")),
            "peak": f("peak_mA"), "post": f("post_peak_slope_per_mA")}


def _bank_g(bank, x):
    """g(x) per replicate; `x` is a (K,) vector or a scalar broadcast to K."""
    x = np.broadcast_to(np.asarray(x, dtype=float), (bank["K"],))
    lin = bank["slope"] * x
    quad = bank["a"] * x * x + bank["b"] * x
    has_post = np.isfinite(bank["peak"]) & np.isfinite(bank["post"])
    peak = np.where(has_post, bank["peak"], 0.0)
    gp = bank["a"] * peak * peak + bank["b"] * peak
    post = gp + np.where(has_post, bank["post"], 0.0) * (x - peak)
    quad = np.where(has_post & (x > peak), post, quad)
    return np.where(bank["kind"] == 0, 0.0, np.where(bank["kind"] == 1, lin, quad))


def _bank_dg(bank, x):
    x = np.broadcast_to(np.asarray(x, dtype=float), (bank["K"],))
    d_quad = 2.0 * bank["a"] * x + bank["b"]
    has_post = np.isfinite(bank["peak"]) & np.isfinite(bank["post"])
    d_quad = np.where(has_post & (x > np.where(has_post, bank["peak"], 0.0)),
                      np.where(has_post, bank["post"], 0.0), d_quad)
    return np.where(bank["kind"] == 0, 0.0, np.where(bank["kind"] == 1, bank["slope"], d_quad))


# --------------------------------------------------------------------------------------------
# One contiguous series, K replicates in lockstep
# --------------------------------------------------------------------------------------------
def _grid_like(a, n_per):
    """Average `a` onto the same non-overlapping windows `replay._average_to_device_grid` used."""
    a = np.asarray(a, dtype=float)
    if n_per <= 1:
        return a
    n_win = a.size // n_per
    return np.nanmean(a[:n_win * n_per].reshape(n_win, n_per), axis=1)


def simulate_series(t_s, power, amp_obs, plan, curves: Sequence[ResponseCurve], *, tau_s,
                    params=None) -> Dict[str, Any]:
    """Run the controller over ONE uniformly sampled series for every curve in `curves` at once.

    Mirrors `replay.dual_threshold` step for step -- the device grid, the onset confirmation, the
    detection blanking, the ramp rate from the transition durations, the hold on a missing
    estimate -- with the plant inserted between the recorded power and the threshold test. With
    `curves[k]` the zero curve, column k IS the replay.

    Returns per-replicate arrays (shape (K,) or (K, n)) and the controller grid.
    """
    p_in = dict(_replay.DEFAULT_PARAMS)
    if params:
        unknown = set(params) - set(_replay.DEFAULT_PARAMS) - {"dt_s"}
        if unknown:
            raise ValueError(f"unknown params {sorted(unknown)}")
        p_in.update(params)

    upper, lower = plan.upper, plan.lower
    if upper is None or lower is None or not (float(upper) > float(lower)):
        raise ValueError(f"the ThresholdPlan has no usable thresholds (upper={upper!r}, lower={lower!r})")
    upper, lower = float(upper), float(lower)
    amp_low = plan.capture_amp_low if p_in["amp_low_mA"] is None else p_in["amp_low_mA"]
    amp_high = plan.capture_amp_high if p_in["amp_high_mA"] is None else p_in["amp_high_mA"]
    if amp_low is None or amp_high is None or not (float(amp_high) > float(amp_low)):
        raise ValueError(f"no usable amplitude limits (low={amp_low!r}, high={amp_high!r})")
    amp_low, amp_high = float(amp_low), float(amp_high)
    action = p_in["high_power_action"]
    if action not in _replay.HIGH_POWER_ACTIONS:
        raise ValueError(f"high_power_action must be one of {_replay.HIGH_POWER_ACTIONS}")
    amp_init = p_in["amp_init_mA"]
    amp_init = 0.5 * (amp_low + amp_high) if amp_init is None else float(amp_init)
    amp_init = min(max(amp_init, amp_low), amp_high)

    t_raw, p_raw, dt_raw = _replay._coerce_series({"t_s": t_s, "power": power}, p_in.get("dt_s"))
    a_raw = np.asarray(amp_obs, dtype=float).ravel()
    if a_raw.size != p_raw.size:
        raise ValueError(f"amp_obs has {a_raw.size} samples but power has {p_raw.size}")
    averaging_s = float(p_in["averaging_ms"]) / 1000.0
    t, p, dt, n_per = _replay._average_to_device_grid(t_raw, p_raw, dt_raw, averaging_s)
    a_obs = _grid_like(a_raw, n_per)[:p.size]

    onset_steps = max(1, int(math.ceil(float(p_in["onset_ms"]) / 1000.0 / dt - 1e-9)))
    blank_steps = max(0, int(math.ceil(float(p_in["detection_blanking_ms"]) / 1000.0 / dt - 1e-9)))
    up_s = float(p_in["transition_up_ms"]) / 1000.0
    down_s = float(p_in["transition_down_ms"]) / 1000.0
    span = amp_high - amp_low
    rate_up, rate_down = span / up_s, span / down_s

    bank = _bank(curves)
    K, n = bank["K"], int(p.size)
    tau = np.broadcast_to(np.asarray(tau_s, dtype=float), (K,)).astype(float)
    alpha = np.where(tau > 0, 1.0 - np.exp(-dt / np.where(tau > 0, tau, 1.0)), 1.0)

    amp = np.full(K, amp_init)
    delta = np.zeros(K)
    adopted = np.full(K, _BETWEEN, dtype=int)
    pending = np.full(K, _NONE, dtype=int)
    pending_run = np.zeros(K, dtype=int)
    blank_left = np.zeros(K, dtype=int)
    n_trans = np.zeros(K, dtype=int)
    n_onset_supp = np.zeros(K, dtype=int)
    n_blank_supp = np.zeros(K, dtype=int)
    wrong_side_steps = np.zeros(K, dtype=int)
    n_missing = 0

    amp_out = np.empty((K, n))
    p_out = np.empty((K, n))
    state_out = np.empty((K, n), dtype=int)
    target_hi = amp_high if action == "increase" else amp_low
    target_lo = amp_low if action == "increase" else amp_high

    for i in range(n):
        pi = p[i]
        if math.isnan(pi):
            # A missing estimate is not a crossing: hold, as the replay does, and hold delta too.
            n_missing += 1
            pending[:] = _NONE
            pending_run[:] = 0
            blank_left = np.maximum(blank_left - 1, 0)
            state_out[:, i] = adopted
            amp_out[:, i] = amp
            p_out[:, i] = np.nan
            continue

        ao = a_obs[i] if np.isfinite(a_obs[i]) else amp
        target_delta = _bank_g(bank, amp) - _bank_g(bank, ao)
        delta = delta + (target_delta - delta) * alpha
        p_sim = pi + delta
        raw = np.where(p_sim > upper, _ABOVE, np.where(p_sim < lower, _BELOW, _BETWEEN))

        same = raw == adopted
        pending = np.where(same, _NONE, pending)
        pending_run = np.where(same, 0, pending_run)
        cont = (~same) & (pending == raw)
        pending_run = np.where(cont, pending_run + 1, pending_run)
        fresh = (~same) & (~cont)
        pending = np.where(fresh, raw, pending)
        pending_run = np.where(fresh, 1, pending_run)
        ready = (~same) & (pending_run >= onset_steps)
        blocked = ready & (blank_left > 0)
        adopt = ready & ~blocked
        n_blank_supp += blocked.astype(int)
        n_onset_supp += ((~same) & (~ready)).astype(int)
        adopted = np.where(adopt, raw, adopted)
        n_trans += adopt.astype(int)
        blank_left = np.where(adopt, blank_steps, blank_left)
        pending = np.where(adopt, _NONE, pending)
        pending_run = np.where(adopt, 0, pending_run)
        blank_left = np.maximum(blank_left - 1, 0)

        target = np.where(adopted == _ABOVE, target_hi, np.where(adopted == _BELOW, target_lo, amp))
        step = np.clip(target - amp, -rate_down * dt, rate_up * dt)
        amp = np.clip(amp + step, amp_low, amp_high)

        wrong_side_steps += (_bank_dg(bank, amp) > 0).astype(int)
        state_out[:, i] = adopted
        amp_out[:, i] = amp
        p_out[:, i] = p_sim

    tol = float(p_in["amp_at_limit_tol_mA"])
    at_high = np.mean(np.abs(amp_out - amp_high) <= tol, axis=1)
    at_low = np.mean(np.abs(amp_out - amp_low) <= tol, axis=1)
    return {
        "K": K, "n_steps": n, "dt_s": float(dt), "t_s": t, "p_obs": p, "a_obs": a_obs,
        "amp": amp_out, "p_sim": p_out, "state": state_out,
        "frac_at_upper": at_high, "frac_at_lower": at_low,
        "longest_at_upper_s": np.array([_replay._longest_run_at_level_s(amp_out[k], dt, amp_high) or 0.0
                                        for k in range(K)]),
        "longest_at_lower_s": np.array([_replay._longest_run_at_level_s(amp_out[k], dt, amp_low) or 0.0
                                        for k in range(K)]),
        "n_transitions": n_trans, "n_onset_suppressed": n_onset_supp,
        "n_blank_suppressed": n_blank_supp,
        "frac_above": np.mean(state_out == _ABOVE, axis=1),
        "frac_between": np.mean(state_out == _BETWEEN, axis=1),
        "frac_below": np.mean(state_out == _BELOW, axis=1),
        "frac_wrong_side": wrong_side_steps / float(max(n, 1)),
        "mean_amp": np.mean(amp_out, axis=1),
        "saturated": (at_high + at_low) >= float(p_in["saturation_frac"]),
        "n_missing": int(n_missing),
        "params": {"upper": upper, "lower": lower, "amp_low_mA": amp_low, "amp_high_mA": amp_high,
                   "amp_init_mA": amp_init, "high_power_action": action, "dt_input_s": float(dt_raw),
                   "dt_controller_s": float(dt), "samples_per_averaging_window": int(n_per),
                   "onset_steps": int(onset_steps), "blanking_steps": int(blank_steps),
                   "ramp_up_mA_per_s": rate_up, "ramp_down_mA_per_s": rate_down,
                   "tau_s": float(tau[0]) if K else None},
    }


# --------------------------------------------------------------------------------------------
# A gappy record: the replay's own segmentation, aggregated per replicate
# --------------------------------------------------------------------------------------------
def _downsample(t, ys, max_points=MAX_TRAJECTORY_POINTS):
    n = int(np.asarray(t).size)
    if n <= max_points:
        idx = np.arange(n)
    else:
        idx = np.unique(np.linspace(0, n - 1, max_points).astype(int))
    return idx


def regrid_stretches(t, p, a, med, *, gap_factor=_replay.SEGMENT_GAP_FACTOR):
    """Split at gaps larger than `gap_factor` times the median interval, then put each stretch's
    pieces on a uniform grid of that interval. Returns (stretches, n_cells_empty, n_cells_merged,
    bounds), each stretch as (t_grid, power, amp).

    THE PIECES ARE PUT ON THE DEVICE'S OWN CLOCK BEFORE THE LOOP RUNS. Measured on RCS08
    (2026-09-11): inside one streaming recording the 3 s pieces are not exactly 3 s apart --
    2.5 s, 1.75 s, 7 s between neighbours -- and `replay.dual_threshold` refuses anything more
    than 5 % off the median interval, so 33 of 43 stretches, the five longest among them, were
    refused outright. Each stretch is therefore regridded to the median interval: a cell holding
    several pieces averages them, and a cell holding none is a MISSING estimate the controller
    holds across, which is the replay's own documented handling of a dropped estimate. The
    controller loop itself is unchanged and still refuses a non-uniform series; this only makes
    the series it is given the series the device would have formed. Counts are reported.

    Each piece's cell is the previous piece's cell plus its gap in whole intervals -- 0 when two
    pieces sit inside one interval (merged), 2 or more across a hole (empty cells). The gaps are
    rounded one at a time, so an interval of 2.98 s rather than 3.00 s cannot accumulate into a
    drift that skips cells down a long stretch.
    """
    gaps = np.diff(t)
    cut = np.flatnonzero(gaps > gap_factor * med) + 1
    bounds = np.concatenate([[0], cut, [t.size]])
    n_cells_empty = n_cells_merged = 0
    regridded = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        seg_t = t[lo:hi]
        inc = np.rint(np.diff(seg_t) / med).astype(int) if hi - lo > 1 else np.zeros(0, dtype=int)
        cell = np.concatenate([[0], np.cumsum(inc)])
        n_cells = int(cell[-1]) + 1
        counts = np.bincount(cell, minlength=n_cells).astype(float)

        def _cell_mean(v):
            fin = np.isfinite(v)
            s_ = np.bincount(cell[fin], weights=v[fin], minlength=n_cells)
            c = np.bincount(cell[fin], minlength=n_cells).astype(float)
            return np.where(c > 0, s_ / np.maximum(c, 1.0), np.nan)
        n_cells_empty += int((counts == 0).sum())
        n_cells_merged += int((counts > 1).sum())
        regridded.append((seg_t[0] + np.arange(n_cells) * med, _cell_mean(p[lo:hi]), _cell_mean(a[lo:hi])))
    return regridded, n_cells_empty, n_cells_merged, bounds


def simulate_segments(t_s, power, amp_obs, plan, curves: Sequence[ResponseCurve], *, tau_s,
                      params=None, min_segment_steps=_replay.MIN_SEGMENT_STEPS,
                      gap_factor=_replay.SEGMENT_GAP_FACTOR, keep_longest=1) -> Dict[str, Any]:
    """Run every curve over each contiguous stretch of a gappy record and aggregate, the way
    `replay.dual_threshold_segments` does: split at gaps larger than `gap_factor` times the median
    interval, regrid each stretch (`regrid_stretches`), skip stretches shorter than
    `min_segment_steps`, weight by controller steps, take the MAXIMUM excursion across stretches
    (an excursion never spans a gap), and REFUSE a record whose median interval cannot resolve
    the ramp.

    Returns the per-replicate aggregates, the record's segmentation counts, and the drawn
    trajectories of the `keep_longest` longest stretches.
    """
    t = np.asarray(t_s, float).ravel()
    p = np.asarray(power, float).ravel()
    a = np.asarray(amp_obs, float).ravel()
    if not (t.size == p.size == a.size):
        raise ValueError(f"time, power and amplitude differ in length: {t.size}, {p.size}, {a.size}")
    ok = np.isfinite(t)
    t, p, a = t[ok], p[ok], a[ok]
    order = np.argsort(t, kind="stable")
    t, p, a = t[order], p[order], a[order]
    if t.size and np.any(np.diff(t) == 0):
        uniq, idx = np.unique(t, return_inverse=True)

        def _mean_by(v):
            s_ = np.zeros(uniq.size); c = np.zeros(uniq.size)
            fin = np.isfinite(v)
            np.add.at(s_, idx[fin], v[fin]); np.add.at(c, idx[fin], 1.0)
            return np.where(c > 0, s_ / np.maximum(c, 1.0), np.nan)
        p, a, t = _mean_by(p), _mean_by(a), uniq

    K = len(curves)
    refused = {"refused": True, "K": K, "n_segments": 0, "n_segments_used": 0}
    if t.size < min_segment_steps:
        return dict(refused, reason=(f"only {t.size} distinct samples, fewer than the {min_segment_steps} "
                                     "steps a segment must contain to exercise the control law"))
    gaps = np.diff(t)
    med = float(np.median(gaps[gaps > 0])) if np.any(gaps > 0) else None
    if med is None or not (med > 0):
        return dict(refused, reason="the time base has no positive interval")
    p_in = dict(_replay.DEFAULT_PARAMS)
    if params:
        p_in.update({k: v for k, v in params.items() if k in _replay.DEFAULT_PARAMS})
    ramp_up_s = float(p_in["transition_up_ms"]) / 1000.0
    if med >= ramp_up_s:
        return dict(refused, median_interval_s=med, transition_up_s=ramp_up_s, ramp_resolvable=False,
                    reason=(f"the ramp is not resolvable at this sampling cadence: samples arrive every "
                            f"{med:.0f} s while the transition-up duration is {ramp_up_s:.0f} s, so one "
                            "step would carry the amplitude across the whole range"))

    regridded, n_cells_empty, n_cells_merged, bounds = regrid_stretches(t, p, a, med, gap_factor=gap_factor)
    seg_lengths = np.array([g[0].size for g in regridded])
    keep_idx = set(np.argsort(-seg_lengths, kind="stable")[:max(0, int(keep_longest))].tolist())

    W = 0.0
    acc = {k: np.zeros(K) for k in ("frac_at_upper", "frac_at_lower", "frac_above", "frac_between",
                                   "frac_below", "frac_wrong_side", "mean_amp")}
    longest_up = np.zeros(K); longest_lo = np.zeros(K)
    n_trans = np.zeros(K, dtype=int); n_sat = np.zeros(K, dtype=int)
    n_used = skipped = 0; n_missing = 0
    hist_edges = None; hist = None
    drawn = []
    seg_params = None
    for si, (gt, gp, ga) in enumerate(regridded):
        if gt.size < min_segment_steps:
            skipped += 1
            continue
        try:
            r = simulate_series(gt - gt[0], gp, ga, plan, curves, tau_s=tau_s, params=params)
        except Exception:                               # noqa: BLE001 -- counted, never fatal
            skipped += 1
            continue
        w = float(r["n_steps"])
        for k in acc:
            acc[k] += w * r[k]
        longest_up = np.maximum(longest_up, r["longest_at_upper_s"])
        longest_lo = np.maximum(longest_lo, r["longest_at_lower_s"])
        n_trans += r["n_transitions"]; n_sat += r["saturated"].astype(int)
        n_missing += r["n_missing"]
        W += w; n_used += 1
        seg_params = r["params"]
        if hist_edges is None:
            hist_edges = np.linspace(r["params"]["amp_low_mA"], r["params"]["amp_high_mA"], 21)
            hist = np.zeros((K, 20))
        for k in range(K):
            hist[k] += np.histogram(np.clip(r["amp"][k], hist_edges[0], hist_edges[-1]), bins=hist_edges)[0]
        if si in keep_idx:
            idx = _downsample(r["t_s"], None)
            drawn.append({"segment_index": int(si), "start_epoch_s": float(gt[0]),
                          "n_steps": int(r["n_steps"]), "dt_s": r["dt_s"],
                          "t_s": r["t_s"][idx].tolist(),
                          "p_obs": r["p_obs"][idx].tolist(), "a_obs": r["a_obs"][idx].tolist(),
                          "amp": r["amp"][:, idx], "p_sim": r["p_sim"][:, idx], "state": r["state"][:, idx]})
    if not W:
        return dict(refused, n_segments=int(bounds.size - 1), n_segments_skipped=int(skipped),
                    median_interval_s=med,
                    reason=(f"the record splits into {bounds.size - 1} contiguous segments and none holds "
                            f"the {min_segment_steps} steps a replay needs"))
    span = float(t[-1] - t[0])
    return {
        "refused": False, "K": K,
        **{k: v / W for k, v in acc.items()},
        "longest_at_upper_s": longest_up, "longest_at_lower_s": longest_lo,
        "n_transitions": n_trans, "transitions_per_hour": n_trans / (W * med / 3600.0),
        "n_segments_saturated": n_sat, "n_missing_steps": int(n_missing),
        "amp_hist_edges_mA": hist_edges.tolist(), "amp_hist": hist,
        "n_segments": int(bounds.size - 1), "n_segments_used": int(n_used),
        "n_segments_skipped": int(skipped), "steps_used": int(W), "median_interval_s": med,
        "n_pieces": int(t.size), "n_cells_without_a_piece": int(n_cells_empty),
        "n_cells_merging_pieces": int(n_cells_merged),
        "span_s": span, "hours_of_signal": W * med / 3600.0,
        "coverage_frac": (W * med / span) if span > 0 else None, "ramp_resolvable": True,
        "params": seg_params, "drawn": drawn,
    }


# --------------------------------------------------------------------------------------------
# The settling time (decision 15) and the run-resampled curves (M3)
# --------------------------------------------------------------------------------------------
def measured_settling_time(t_s, power, amp_obs, run_windows) -> Dict[str, Any]:
    """tau from the record itself: `percept_adaptive.estimate_response_latency` on each run of
    rising current (time to 63.2 % of the change after the largest amplitude step), the median
    across the runs that yield one. None when no run supports it, with the count."""
    t = np.asarray(t_s, float); p = np.asarray(power, float); a = np.asarray(amp_obs, float)
    taus = []
    for lo, hi in (run_windows or []):
        m = (t >= float(lo)) & (t <= float(hi)) & np.isfinite(p) & np.isfinite(a)
        if m.sum() < 4:
            continue
        try:
            v = percept_adaptive.estimate_response_latency(t[m], p[m], a[m])
        except Exception:                               # noqa: BLE001
            v = None
        if v is not None and np.isfinite(v) and v > 0:
            taus.append(float(v))
    return {"tau_s": (float(np.median(taus)) if taus else None), "n_runs_measured": len(taus),
            "n_runs_offered": len(run_windows or []), "per_run_s": taus}


def resampled_curves(points_x, points_y, run_labels, *, n_resample=DEFAULT_N_RESAMPLE, seed=0,
                     use_bend=False, min_points=None) -> Dict[str, Any]:
    """Refit the pooled curve on runs drawn with replacement (the pooled model's own grouping).

    Each draw relabels its copies so a run drawn twice contributes two baselines, which is what
    'with replacement' means for a grouped fit. Returns the curves and how many draws fitted."""
    x = np.asarray(points_x, float); y = np.asarray(points_y, float)
    lab = np.asarray([str(r) for r in run_labels])
    runs = sorted(set(lab.tolist()))
    if len(runs) < MIN_RUNS_FOR_RESAMPLE:
        return {"curves": [], "n_runs": len(runs), "n_fitted": 0,
                "reason": f"only {len(runs)} run(s) of rising current on this contact; at least "
                          f"{MIN_RUNS_FOR_RESAMPLE} are needed to resample runs"}
    rng = np.random.default_rng(seed)
    curves, n_fitted = [], 0
    kw = {} if min_points is None else {"min_points": int(min_points)}
    for b in range(int(n_resample)):
        draw = rng.choice(runs, size=len(runs), replace=True)
        xs, ys, vs = [], [], []
        for j, r in enumerate(draw):
            m = lab == r
            xs.append(x[m]); ys.append(y[m]); vs.append(np.full(int(m.sum()), f"{r}#{j}"))
        try:
            row = _wv.amplitude_response_shape_pooled(np.concatenate(xs), np.concatenate(ys),
                                                      np.concatenate(vs), **kw)
        except Exception:                               # noqa: BLE001
            row = None
        pp = (row or {}).get("post_peak") or {}
        if row:
            row = dict(row, post_peak_slope_per_mA=pp.get("slope_per_mA", float("nan")))
        c = ResponseCurve.from_pooled_row(row, use_bend=use_bend,
                                          lo_mA=float(x.min()), hi_mA=float(x.max()))
        if c.kind != NONE:
            n_fitted += 1
        curves.append(c)
    return {"curves": curves, "n_runs": len(runs), "n_fitted": n_fitted, "n_resample": int(n_resample)}


# --------------------------------------------------------------------------------------------
# The whole answer
# --------------------------------------------------------------------------------------------
def _interval(values, lo=2.5, hi=97.5):
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    if v.size < 3:
        return None
    return [float(np.percentile(v, lo)), float(np.percentile(v, hi))]


def _summary(res, k) -> Dict[str, Any]:
    return {
        "frac_time_at_upper": float(res["frac_at_upper"][k]),
        "frac_time_at_lower": float(res["frac_at_lower"][k]),
        "longest_run_at_upper_s": float(res["longest_at_upper_s"][k]),
        "longest_run_at_lower_s": float(res["longest_at_lower_s"][k]),
        "n_transitions": int(res["n_transitions"][k]),
        "transitions_per_hour": float(res["transitions_per_hour"][k]),
        "frac_time_above": float(res["frac_above"][k]),
        "frac_time_between": float(res["frac_between"][k]),
        "frac_time_below": float(res["frac_below"][k]),
        "frac_time_wrong_side": float(res["frac_wrong_side"][k]),
        "mean_amplitude_mA": float(res["mean_amp"][k]),
        "amp_hist": [int(v) for v in res["amp_hist"][k]],
    }


_INTERVAL_FIELDS = ("frac_time_at_upper", "frac_time_at_lower", "longest_run_at_upper_s",
                    "longest_run_at_lower_s", "transitions_per_hour", "frac_time_above",
                    "frac_time_between", "frac_time_below", "frac_time_wrong_side", "mean_amplitude_mA")


def run_models(t_s, power, amp_obs, plan, pooled_row, *, run_points=None, run_windows=None,
               tau_s=None, n_resample=DEFAULT_N_RESAMPLE, seed=0, params=None,
               min_points_resample=None) -> Dict[str, Any]:
    """M0, M1, M2 (when a bend is established) and M3, over one record, in one vectorised pass.

    `run_points` is `(x_mA, y_power, run_labels)` from the stored per-run points (decision 125),
    the material M3 resamples; `run_windows` the (start, end) epoch seconds of each run, for the
    measured settling time (decision 15). `tau_s` overrides both when given.
    """
    out: Dict[str, Any] = {"gates_nothing": True, "rule_version": RULE_VERSION, "models": {},
                           "caveat": CAVEAT}
    t = np.asarray(t_s, float); p = np.asarray(power, float); a = np.asarray(amp_obs, float)
    lo_mA = float(np.nanmin(a)) if a.size and np.isfinite(a).any() else float("nan")
    hi_mA = float(np.nanmax(a)) if a.size and np.isfinite(a).any() else float("nan")

    # --- the settling time --------------------------------------------------------------------
    if tau_s is not None:
        tau = {"tau_s": float(tau_s), "source": "given"}
    else:
        m = measured_settling_time(t, p, a, run_windows)
        if m["tau_s"] is not None:
            gaps = np.diff(np.sort(t[np.isfinite(t)])); cad = float(np.median(gaps[gaps > 0])) if np.any(gaps > 0) else None
            at_floor = cad is not None and m["tau_s"] <= cad + 1e-9
            tau = {"tau_s": m["tau_s"], "source": (f"measured: the median time to 63.2 % of the change "
                                                    f"after the largest amplitude step, across "
                                                    f"{m['n_runs_measured']} of {m['n_runs_offered']} runs"
                                                    + (f"; at the resolution floor of the {cad:g} s pieces, "
                                                       "so the band settles within one piece" if at_floor else "")),
                   "per_run_s": m["per_run_s"], "at_resolution_floor": bool(at_floor)}
        else:
            tau = {"tau_s": DEFAULT_TAU_S, "source": (f"default: the {DEFAULT_TAU_S:.0f} s settled window; "
                                                      f"no run of {m['n_runs_offered']} yielded a measured "
                                                      "latency")}
    out["settling"] = tau

    # --- the curves -----------------------------------------------------------------------------
    m0 = ResponseCurve.zero()
    m1 = ResponseCurve.from_pooled_row(pooled_row, use_bend=False, lo_mA=lo_mA, hi_mA=hi_mA)
    m2 = ResponseCurve.from_pooled_row(pooled_row, use_bend=True, lo_mA=lo_mA, hi_mA=hi_mA)
    has_bend = m2.kind == QUADRATIC
    active_name = "M2" if has_bend else "M1"
    curves: List[ResponseCurve] = [m0, m1] + ([m2] if has_bend else [])
    names = ["M0", "M1"] + (["M2"] if has_bend else [])
    out["curves"] = {"M0": m0.to_dict(), "M1": m1.to_dict(),
                     "M2": (m2.to_dict() if has_bend else None)}
    out["m2_absent_reason"] = (None if has_bend else
                               "not assessable: no bend in the amplitude response is established on "
                               "this contact and band (the pooled quadratic term is not significant), "
                               "so the peaked model has nothing to fit")
    out["active_model"] = active_name

    # --- M3 -----------------------------------------------------------------------------------
    rs = {"curves": [], "n_runs": 0, "n_fitted": 0, "reason": "no per-run points were supplied"}
    if run_points is not None and m1.kind != NONE:
        px, py, pl = run_points
        rs = resampled_curves(px, py, pl, n_resample=n_resample, seed=seed, use_bend=has_bend,
                              min_points=min_points_resample)
    k_m3 = len(curves)
    curves += rs["curves"]
    out["resampling"] = {"n_runs": rs["n_runs"], "n_fitted": rs["n_fitted"],
                         "n_resample": rs.get("n_resample", 0), "reason": rs.get("reason")}

    # --- one pass -------------------------------------------------------------------------------
    res = simulate_segments(t, p, a, plan, curves, tau_s=tau["tau_s"], params=params)
    if res.get("refused"):
        out.update({"refused": True, "absent_reason": res.get("reason"),
                    "median_interval_s": res.get("median_interval_s"),
                    "ramp_resolvable": res.get("ramp_resolvable")})
        return out
    out["refused"] = False
    for k, name in enumerate(names):
        out["models"][name] = _summary(res, k)
    if rs["curves"]:
        vals = {f: [] for f in _INTERVAL_FIELDS}
        for k in range(k_m3, len(curves)):
            if curves[k].kind == NONE:
                continue
            s = _summary(res, k)
            for f in _INTERVAL_FIELDS:
                vals[f].append(s[f])
        out["models"]["M3"] = {"interval_of": active_name,
                               "n_replicates": len(vals["frac_time_at_upper"]),
                               "intervals": {f: _interval(v) for f, v in vals.items()},
                               "slope_interval_per_mA": _interval([c.slope_per_mA for c in curves[k_m3:]
                                                                   if c.kind != NONE])}
    act = out["models"][active_name]
    base = out["models"]["M0"]
    out["closed_loop_difference"] = {f: (act[f] - base[f]) for f in _INTERVAL_FIELDS}

    # --- the wrong side of the peak (decision 17: a number and a warning, no gate) --------------
    pr = res["params"]
    active_curve = m2 if has_bend else m1
    ws = active_curve.positive_feedback_range(pr["amp_low_mA"], pr["amp_high_mA"])
    out["wrong_side"] = {
        "range_mA": list(ws) if ws else None,
        "frac_time": act["frac_time_wrong_side"],
        "warning": (None if ws is None else
                    (f"between {ws[0]:.2f} and {ws[1]:.2f} mA this band's power RISES with current, so "
                     "the device's law (raise current when power is high) is positive feedback there; "
                     f"the active model spends {100 * act['frac_time_wrong_side']:.1f} % of its steps in "
                     "that range")),
        "gates_nothing": True}
    out["extrapolates_beyond_fitted_range"] = active_curve.extrapolates(pr["amp_low_mA"], pr["amp_high_mA"])

    # --- the record and the drawings ------------------------------------------------------------
    out["record"] = {k: res[k] for k in ("n_segments", "n_segments_used", "n_segments_skipped", "steps_used",
                                         "median_interval_s", "span_s", "hours_of_signal", "coverage_frac",
                                         "ramp_resolvable", "n_missing_steps", "n_pieces",
                                         "n_cells_without_a_piece", "n_cells_merging_pieces")}
    out["params"] = pr
    out["amp_hist_edges_mA"] = res["amp_hist_edges_mA"]
    out["drawn"] = []
    for d in res["drawn"]:
        out["drawn"].append({
            "segment_index": d["segment_index"], "start_epoch_s": d["start_epoch_s"],
            "n_steps": d["n_steps"], "dt_s": d["dt_s"], "t_s": d["t_s"], "p_obs": d["p_obs"],
            "a_obs": d["a_obs"],
            "models": {name: {"amp": d["amp"][k].tolist(),
                              "p_sim": [None if not np.isfinite(v) else float(v) for v in d["p_sim"][k]],
                              "state": d["state"][k].tolist()}
                       for k, name in enumerate(names)},
            # the M3 envelope of the amplitude, per drawn step
            "m3_amp_band": ([np.percentile(d["amp"][k_m3:], 2.5, axis=0).tolist(),
                             np.percentile(d["amp"][k_m3:], 97.5, axis=0).tolist()]
                            if len(curves) - k_m3 >= 3 else None),
        })
    out["n_points_in_curve"] = int(m1.n_points)
    out["n_runs_in_curve"] = int(m1.n_runs)
    out["caveat"] = CAVEAT.replace("N settled", f"{m1.n_points} settled").replace("V runs", f"{m1.n_runs} runs")
    return out
