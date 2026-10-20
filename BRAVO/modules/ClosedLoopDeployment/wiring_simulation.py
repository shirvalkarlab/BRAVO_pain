"""The three sense-to-control wirings compared by simulation (the PI, 2026-10-08 and 2026-10-14:
"plan out how you might simulate this to arrive at a recommendation for the control law wiring";
"yes go ahead simulate"; decision 472). On screen: Closed-Loop page, the "Sense-to-control algorithm
wiring" card, a "Recommended" mark on one button and the scores in a fold below, closed.

THE QUESTION. Percept runs Adaptive Therapy per stimulator, and each stimulator reads the band power
of one side: its own (ipsilateral) or, on a two-lead implant, the other side's (contralateral, D39).
Three wirings follow: "2 independent controllers" (each side its own band), "Left sensing drives
both", "Right sensing drives both". Which one would have delivered current that best follows pain?

WHAT IS RUN, over ONE record for all three, so they are scored on the same pain ratings: the time
both sides' voltage traces were recorded at once (3 s pieces, both chosen bands, the device's own
per-sample current on each side). Each stretch is put on the device's averaging grid, and two
Dual Threshold controllers run on it in one loop, one per stimulator, each with the thresholds and
current limits of ITS OWN deployment report (the band driving it, on that stimulator) and the
participant's one timing (the same for all three wirings, so timing cannot decide the comparison).

THE SIGNAL MOVES WITH THE CURRENT, on both sides. A replay of recorded power cannot show the
controller's own current moving the power it reads, so each sensed band's power is shifted as in
`simulation.py` (decision 15's offset formulation, the same settling time):

    target_s = sum over stimulators c of  k[s][c] * (a_sim_c - a_obs_c)
    delta_s += (target_s - delta_s) * (1 - exp(-dt / tau))

`k[s][c]` is the change in band s's power per mA of stimulator c, a straight line (model M1 of
`simulation.py`): on the band's own side the stored pooled row (decision 103); on the OTHER side,
measured here with the same pooled estimator (`within_visit.amplitude_response_shape_pooled`) on the
runs where only stimulator c's current was stepped (decision 197's runs), from the settled last 30 s
of each setting on band s's contact. Too few points: taken as zero, and said.

THE SCORE. For every pain rating within 60 s of a grid cell where both sides were recorded (past
each stretch's opening, the onset time and a full ramp up, since both controllers start mid-range), each
stimulator's simulated current, as a share of its own range (0 at its lowest limit, 1 at its
highest). Those ratings are split into thirds as the Biomarkers page splits a band's own
reports; a stimulator's score is the
AUC of that share between high and low pain (0.5 = no relationship; above 0.5 = more current at
high pain). A wiring's score is the mean of its two stimulators'. Intervals: whole visit days
resampled (1000 draws). Also per wiring: controller switches per hour and each stimulator's share
of time at its highest current and mean current (a battery proxy).

THE RECOMMENDATION, from the scores alone and stated with its reason. Only a wiring whose current
rose with pain can be named (its score's whole interval above 0.5); when none did, none is. Among
those, the best-scoring wiring when
its lead over the runner-up holds in the day resampling (the 95% interval of the difference lies
above zero); otherwise "2 independent controllers" when it is among the tied (Medtronic's ordinary
case, no contralateral fallback), else the higher point estimate, said to be not clearly better.
Wirings the device refuses today are named; the recommendation is among the allowed ones when any
is allowed, and otherwise says that none is.

It gates nothing. A replay of past data, not a test of closed loop.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from . import replay as _replay

KIND = "wiring_comparison"
RULE_VERSION = "v1_two_controllers_joint_record"

SIDES = ("Left", "Right")
WIRINGS = {
    "independent": {"Left": "Left", "Right": "Right"},
    "left_both": {"Left": "Left", "Right": "Left"},
    "right_both": {"Left": "Right", "Right": "Right"},
}
WIRING_LABELS = {"independent": "2 independent controllers: Ipsilateral wiring",
                 "left_both": "Left sensing drives both", "right_both": "Right sensing drives both"}

#: A rating counts when a grid cell with both sides recorded lies within this many seconds.
RATING_TOL_S = 60.0
#: Whole visit days resampled for every interval.
N_BOOT = 1000
#: Fewer ratings than this in the high or the low third: no score.
MIN_PER_GROUP = 5
#: The settled window of a setting, as the three-source comparison takes it.
SETTLED_S = 30.0
#: A cross-side line needs this many settled points over at least two runs, else it is taken as zero.
MIN_CROSS_POINTS = 6
DEFAULT_TAU_S = 30.0

_ABOVE, _BETWEEN, _BELOW, _NONE = 1, 0, -1, 2


# --------------------------------------------------------------------------------------------
# The change in power per mA, own side and other side
# --------------------------------------------------------------------------------------------
def settled_points(runs, stepped_side, tile_t, tile_p, tile_ok=None, *, settled_s=SETTLED_S):
    """(current, settled power, run label) for every setting of every run on which `stepped_side`
    alone moved: the median of the band's 3 s pieces in the last `settled_s` of the setting."""
    t = np.asarray(tile_t, float)
    p = np.asarray(tile_p, float)
    ok = np.isfinite(p) & np.isfinite(t)
    if tile_ok is not None:
        ok &= np.asarray(tile_ok, bool)
    xs, ys, labels = [], [], []
    for run in runs or []:
        if run.get("side") != stepped_side:
            continue
        steps = run["steps"]
        for _i, st in steps.iterrows():
            t_end = float(st["t_end"]) if np.isfinite(st["t_end"]) else float(st["t0"])
            lo = max(float(st["t0"]), t_end - float(settled_s))
            m = ok & (t >= lo) & (t <= t_end)
            if m.sum() < 2:
                continue
            xs.append(float(st["current_mA"]))
            ys.append(float(np.median(p[m])))
            labels.append(str(st["block"]))
    return np.asarray(xs), np.asarray(ys), np.asarray(labels)


def cross_slope(xs, ys, labels, *, min_points=MIN_CROSS_POINTS):
    """The pooled straight line of power on current with each run its own baseline, or zero (with
    the reason) when there are too few points or runs."""
    n_runs = int(np.unique(labels).size) if len(labels) else 0
    if len(xs) < min_points or n_runs < 2:
        return {"slope_per_mA": 0.0, "stderr": None, "n": int(len(xs)), "n_runs": n_runs,
                "measured": False,
                "source": (f"not measured: {len(xs)} settled points over {n_runs} run"
                           f"{'s' if n_runs != 1 else ''} (at least {min_points} over two runs "
                           "needed); taken as zero")}
    from StimOptimizer.routines import within_visit
    out = within_visit.amplitude_response_shape_pooled(xs, ys, labels, min_points=min_points)
    s = out.get("pooled_slope_per_mA")
    if s is None or not np.isfinite(s):
        return {"slope_per_mA": 0.0, "stderr": None, "n": int(len(xs)), "n_runs": n_runs,
                "measured": False, "source": "the pooled line could not be fitted; taken as zero"}
    se = out.get("pooled_slope_stderr")
    return {"slope_per_mA": float(s), "stderr": (float(se) if se is not None and np.isfinite(se) else None),
            "n": int(len(xs)), "n_runs": n_runs, "measured": True,
            "source": (f"measured here: pooled line over {len(xs)} settled points in {n_runs} runs "
                       "of the other side's stepped current")}


# --------------------------------------------------------------------------------------------
# One record for all three wirings: the time both sides were recorded
# --------------------------------------------------------------------------------------------
def joint_stretches(left, right, *, gap_factor=_replay.SEGMENT_GAP_FACTOR):
    """`left`/`right`: {"t", "power", "amp_Left", "amp_Right"} on each band's own pieces. Returns
    (stretches, median interval): each stretch {"t", "p": {side: power}, "a": {side: current}} on a
    uniform grid of the median interval, kept only where both bands have a piece; a cell inside a
    stretch without a piece on both sides is missing (the controllers hold across it)."""
    tl = np.asarray(left["t"], float)
    tr = np.asarray(right["t"], float)
    if tl.size < 2 or tr.size < 2:
        return [], None
    med = float(np.median(np.concatenate([np.diff(np.sort(tl)), np.diff(np.sort(tr))])))
    if not (med > 0):
        return [], None

    def cells(src):
        k = np.rint(np.asarray(src["t"], float) / med).astype(np.int64)
        out = {}
        for name in ("power", "amp_Left", "amp_Right"):
            v = np.asarray(src[name], float)
            fin = np.isfinite(v)
            uniq, inv = np.unique(k, return_inverse=True)
            s = np.bincount(inv[fin], weights=v[fin], minlength=uniq.size)
            c = np.bincount(inv[fin], minlength=uniq.size).astype(float)
            out[name] = dict(zip(uniq.tolist(), np.where(c > 0, s / np.maximum(c, 1), np.nan).tolist()))
        return out

    L, R = cells(left), cells(right)
    common = np.array(sorted(set(L["power"]) & set(R["power"])), dtype=np.int64)
    if common.size < 2:
        return [], med
    cut = np.flatnonzero(np.diff(common) > gap_factor) + 1
    stretches = []
    for seg in np.split(common, cut):
        ks = np.arange(seg[0], seg[-1] + 1, dtype=np.int64)
        have = set(seg.tolist())
        pick = lambda d, name: np.array([d[name].get(int(k), np.nan) if int(k) in have else np.nan  # noqa: E731
                                         for k in ks])
        aL = np.array([L["amp_Left"].get(int(k), R["amp_Left"].get(int(k), np.nan)) for k in ks])
        aR = np.array([R["amp_Right"].get(int(k), L["amp_Right"].get(int(k), np.nan)) for k in ks])
        stretches.append({"t": ks.astype(float) * med,
                          "p": {"Left": pick(L, "power"), "Right": pick(R, "power")},
                          "a": {"Left": aL, "Right": aR}})
    return stretches, med


def _to_device_grid(stretch, med, averaging_s):
    """The stretch on the device's averaging windows (`replay._average_to_device_grid`, every
    series alike), or None when it holds fewer than two windows."""
    try:
        t, pl, dt, n_per = _replay._average_to_device_grid(stretch["t"], stretch["p"]["Left"], med, averaging_s)
        _t, pr, _dt, _n = _replay._average_to_device_grid(stretch["t"], stretch["p"]["Right"], med, averaging_s)
        _t, al, _dt, _n = _replay._average_to_device_grid(stretch["t"], stretch["a"]["Left"], med, averaging_s)
        _t, ar, _dt, _n = _replay._average_to_device_grid(stretch["t"], stretch["a"]["Right"], med, averaging_s)
    except ValueError:
        return None
    return {"t": t, "p": {"Left": pl, "Right": pr}, "a": {"Left": al, "Right": ar}, "dt": dt}


# --------------------------------------------------------------------------------------------
# Two controllers in one loop
# --------------------------------------------------------------------------------------------
def controller_params(ctrl, timing):
    """One stimulator's controller: its thresholds and limits (from its report) and the timing."""
    p_in = dict(_replay.DEFAULT_PARAMS)
    p_in.update({k: v for k, v in (timing or {}).items() if k in _replay.DEFAULT_PARAMS and v is not None})
    lo, hi = float(ctrl["amp_low_mA"]), float(ctrl["amp_high_mA"])
    if not (hi > lo):
        raise ValueError(f"no usable current limits ({lo!r} to {hi!r} mA)")
    up, low = float(ctrl["upper"]), float(ctrl["lower"])
    if not (up > low):
        raise ValueError(f"no usable thresholds (upper {up!r}, lower {low!r})")
    return {"upper": up, "lower": low, "amp_low": lo, "amp_high": hi,
            "action": p_in["high_power_action"], "onset_s": float(p_in["onset_ms"]) / 1000.0,
            "blank_s": float(p_in["detection_blanking_ms"]) / 1000.0,
            "up_s": float(p_in["transition_up_ms"]) / 1000.0,
            "down_s": float(p_in["transition_down_ms"]) / 1000.0,
            "averaging_s": float(p_in["averaging_ms"]) / 1000.0,
            "tol": float(p_in["amp_at_limit_tol_mA"])}


def run_stretch(g, drives, ctrls, k, *, tau_s=DEFAULT_TAU_S):
    """Both stimulators' controllers over one stretch on the device grid. `drives[stim]` is the side
    whose band it reads; `k[s][c]` the change in band s's power per mA of stimulator c. Returns the
    simulated current and adopted state per stimulator, and the switch count."""
    dt = float(g["dt"])
    n = int(g["t"].size)
    alpha = 1.0 - math.exp(-dt / tau_s) if tau_s > 0 else 1.0
    sensed = sorted(set(drives.values()))
    st = {}
    for c in SIDES:
        q = ctrls[c]
        span = q["amp_high"] - q["amp_low"]
        st[c] = {"amp": 0.5 * (q["amp_low"] + q["amp_high"]), "adopted": _BETWEEN, "pending": _NONE,
                 "run": 0, "blank": 0, "n_trans": 0,
                 "onset": max(1, int(math.ceil(q["onset_s"] / dt - 1e-9))),
                 "blank_steps": max(0, int(math.ceil(q["blank_s"] / dt - 1e-9))),
                 "rate_up": span / q["up_s"], "rate_down": span / q["down_s"],
                 "hi_t": q["amp_high"] if q["action"] == "increase" else q["amp_low"],
                 "lo_t": q["amp_low"] if q["action"] == "increase" else q["amp_high"],
                 "amp_out": np.empty(n), "state_out": np.empty(n, dtype=int)}
    delta = {s: 0.0 for s in sensed}
    for i in range(n):
        # the plant: every stimulator's current moves every sensed band, by its own line
        for s in sensed:
            if not np.isfinite(g["p"][s][i]):
                continue
            tgt = 0.0
            for c in SIDES:
                ao = g["a"][c][i]
                if np.isfinite(ao):
                    tgt += float(k[s][c]) * (st[c]["amp"] - ao)
            delta[s] += (tgt - delta[s]) * alpha
        for c in SIDES:
            x = st[c]
            q = ctrls[c]
            ps = g["p"][drives[c]][i]
            if not np.isfinite(ps):
                # a missing estimate is not a crossing: hold, as the replay does
                x["pending"], x["run"] = _NONE, 0
                x["blank"] = max(x["blank"] - 1, 0)
                x["amp_out"][i], x["state_out"][i] = x["amp"], x["adopted"]
                continue
            p_sim = ps + delta[drives[c]]
            raw = _ABOVE if p_sim > q["upper"] else (_BELOW if p_sim < q["lower"] else _BETWEEN)
            if raw == x["adopted"]:
                x["pending"], x["run"] = _NONE, 0
            else:
                if x["pending"] == raw:
                    x["run"] += 1
                else:
                    x["pending"], x["run"] = raw, 1
                if x["run"] >= x["onset"]:
                    if x["blank"] > 0:
                        pass
                    else:
                        x["adopted"] = raw
                        x["n_trans"] += 1
                        x["blank"] = x["blank_steps"]
                        x["pending"], x["run"] = _NONE, 0
            x["blank"] = max(x["blank"] - 1, 0)
            target = x["hi_t"] if x["adopted"] == _ABOVE else (x["lo_t"] if x["adopted"] == _BELOW else x["amp"])
            step = min(max(target - x["amp"], -x["rate_down"] * dt), x["rate_up"] * dt)
            x["amp"] = min(max(x["amp"] + step, q["amp_low"]), q["amp_high"])
            x["amp_out"][i], x["state_out"][i] = x["amp"], x["adopted"]
    return {c: {"amp": st[c]["amp_out"], "state": st[c]["state_out"], "n_trans": st[c]["n_trans"]}
            for c in SIDES}


# --------------------------------------------------------------------------------------------
# Scoring against pain
# --------------------------------------------------------------------------------------------
def auc(score, y01):
    """Mann-Whitney AUC of `score` between y01 == 1 (high pain) and 0 (low pain), ties half."""
    s = np.asarray(score, float)
    y = np.asarray(y01, float)
    m = np.isfinite(s) & np.isfinite(y)
    pos, neg = s[m & (y == 1)], s[m & (y == 0)]
    if pos.size < MIN_PER_GROUP or neg.size < MIN_PER_GROUP:
        return None
    from scipy.stats import rankdata
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[:pos.size].sum() - pos.size * (pos.size + 1) / 2.0) / (pos.size * neg.size))


def pain_thirds(y):
    """1 for high pain, 0 for low, NaN between: the Biomarkers page's own split
    (`analytics._pain_split`, tertiles, one score per report)."""
    from Biomarkers.routines import analytics as _an
    lab, why, lo, hi = _an._pain_split(np.asarray(y, float), strategy="tertile")
    return np.asarray(lab, float), why, lo, hi


def score_wiring(drive_at_ratings, y01, day_of_rating, *, n_boot=N_BOOT, seed=0):
    """Per stimulator AUC and the wiring's mean, with day-resampled draws (`n_boot` x 3 array of
    Left, Right, mean; NaN where a draw has too few in a third)."""
    days = np.asarray(day_of_rating)
    uniq = np.unique(days)
    per = {c: auc(drive_at_ratings[c], y01) for c in SIDES}
    mean = (None if any(v is None for v in per.values()) else float(np.mean([per[c] for c in SIDES])))
    rng = np.random.default_rng(seed)
    idx_by_day = {d: np.flatnonzero(days == d) for d in uniq}
    draws = np.full((n_boot, 3), np.nan)
    for b in range(n_boot):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        ii = np.concatenate([idx_by_day[d] for d in pick]) if pick.size else np.empty(0, int)
        vals = [auc(np.asarray(drive_at_ratings[c])[ii], np.asarray(y01)[ii]) for c in SIDES]
        draws[b, :2] = [np.nan if v is None else v for v in vals]
        if all(v is not None for v in vals):
            draws[b, 2] = float(np.mean(vals))
    return {"auc": per, "score": mean, "draws": draws}


def _interval(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if v.size < 20:
        return None
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def recommend(scores, draws, allowed):
    """The recommendation and its reason, from the wirings' scores and their paired day draws.
    `allowed[w]` is True / False / None (the device's verdict on both stimulators of wiring w)."""
    have = [w for w in WIRINGS if scores.get(w) is not None]
    if not have:
        return {"wiring": None, "reason": "no wiring could be scored on these pain ratings", "basis": "none"}
    # ONLY A WIRING WHOSE CURRENT ROSE WITH PAIN CAN BE RECOMMENDED: its whole interval above 0.5
    # A tie rule by itself cannot establish that a wiring follows pain.
    follows = [w for w in have if (_interval(draws[w]) or [0.0])[0] > 0.5]
    if not follows:
        return {"wiring": None, "basis": "none_follows_pain",
                "reason": ("in none of the three wirings did the simulated current rise with pain: no "
                           "score's 95% interval lies above 0.5, so none is recommended")}
    have = follows
    pool = [w for w in have if allowed.get(w) is True]
    none_allowed = not pool
    if none_allowed:
        pool = have
    ranked = sorted(pool, key=lambda w: -scores[w])
    best = ranked[0]
    tail = (" The device refuses every wiring today, so this is the simulation's answer alone."
            if none_allowed else "")
    if len(ranked) == 1:
        return {"wiring": best, "basis": "only_one", "none_allowed": none_allowed,
                "reason": f"the only wiring that could be compared.{tail}"}
    tied = [best]
    for w in ranked[1:]:
        d = draws[best] - draws[w]
        ci = _interval(d)
        if ci is None or ci[0] <= 0:
            tied.append(w)
    if len(tied) == 1:
        return {"wiring": best, "basis": "clearly_best", "none_allowed": none_allowed,
                "reason": (f"its score is higher than every other wiring's in at least 97.5% of the "
                           f"resampled sets of visit days.{tail}")}
    if "independent" in tied:
        return {"wiring": "independent", "basis": "tie_default", "none_allowed": none_allowed,
                "tied_with": [w for w in tied if w != "independent"],
                "reason": ("no wiring scores clearly better once visit days are resampled, so the "
                           "device's ordinary case is recommended: each side drives its own "
                           f"stimulator, with no contralateral sensing.{tail}")}
    return {"wiring": best, "basis": "not_clearly_best", "none_allowed": none_allowed,
            "tied_with": [w for w in tied if w != best],
            "reason": ("the highest score, but not clearly better than "
                       + " or ".join(WIRING_LABELS[w] for w in tied if w != best)
                       + f" once visit days are resampled.{tail}")}


def compare(stretches, med, ctrls_by_pairing, k, ratings_t, ratings_y, rating_day, *, timing=None,
            allowed=None, tau_s=DEFAULT_TAU_S, n_boot=N_BOOT, seed=0) -> Dict[str, Any]:
    """Run and score the three wirings on one record. `ctrls_by_pairing[(band_side, stim_side)]` is
    that pairing's controller ({"upper", "lower", "amp_low_mA", "amp_high_mA"}) or None when its
    report placed none."""
    allowed = allowed or {}
    out = {"gates_nothing": True, "rule_version": RULE_VERSION, "wirings": {}, "rating_tol_s": RATING_TOL_S,
           "tau_s": tau_s, "n_boot": n_boot}
    if not stretches:
        out["refused"] = True
        out["reason"] = "the two chosen bands were never recorded at the same time"
        return out
    rt = np.asarray(ratings_t, float)
    ry = np.asarray(ratings_y, float)
    rday = np.asarray(rating_day)

    params_by_wiring, drawn = {}, {}
    for w, drives in WIRINGS.items():
        missing = [f"{c} stimulator from the {drives[c].lower()} band" for c in SIDES
                   if ctrls_by_pairing.get((drives[c], c)) is None]
        if missing:
            out["wirings"][w] = {"label": WIRING_LABELS[w], "scored": False,
                                 "reason": "no thresholds were placed for the " + " and the ".join(missing)}
            continue
        ctrls = {c: controller_params(ctrls_by_pairing[(drives[c], c)], timing) for c in SIDES}
        params_by_wiring[w] = (drives, ctrls)

    if not params_by_wiring:
        out["refused"] = True
        out["reason"] = "no wiring had thresholds placed for both of its stimulators"
        return out

    # The device grid is the same for every wiring: one timing.
    averaging_s = next(iter(params_by_wiring.values()))[1]["Left"]["averaging_s"]
    grids = [g for g in (_to_device_grid(s, med, averaging_s) for s in stretches) if g is not None]
    if not grids:
        out["refused"] = True
        out["reason"] = "no stretch recorded on both sides is long enough for two averaging windows"
        return out
    gt = np.concatenate([g["t"] for g in grids])
    both = np.concatenate([np.isfinite(g["p"]["Left"]) & np.isfinite(g["p"]["Right"]) for g in grids])
    dt = float(grids[0]["dt"])
    hours = float(both.sum() * dt / 3600.0)
    # THE OPENING OF EVERY STRETCH IS LEFT OUT OF THE SCORE. Each stretch starts both controllers at
    # the middle of their ranges, so a rating given before a controller could have moved reads that
    # starting point, the same for every wiring. A cell counts only once the onset time and a
    # full ramp up have passed since its stretch began.
    first = next(iter(params_by_wiring.values()))[1]["Left"]
    warm_s = first["onset_s"] + first["up_s"]
    since = np.concatenate([g["t"] - g["t"][0] for g in grids])
    settled = since >= warm_s
    # each rating's nearest grid cell with both sides recorded, within the tolerance
    cand = np.flatnonzero(both)
    order = np.argsort(gt[cand])
    ct = gt[cand][order]
    pos = np.searchsorted(ct, rt)
    best_i = np.full(rt.size, -1)
    best_d = np.full(rt.size, np.inf)
    for off in (-1, 0):
        j = pos + off
        okj = (j >= 0) & (j < ct.size)
        d = np.where(okj, np.abs(ct[np.clip(j, 0, max(ct.size - 1, 0))] - rt), np.inf)
        better = d < best_d
        best_d = np.where(better, d, best_d)
        best_i = np.where(better, cand[order][np.clip(j, 0, max(ct.size - 1, 0))], best_i)
    # THE THIRDS ARE CUT ON THE RATINGS SCORED, the ones inside the record, as a band's AUC is cut
    # on its own matched reports: cut on every rating ever given, the record's few could all fall in
    # one third, so use the matched reports for the cut.
    near = (best_d <= RATING_TOL_S) & np.isfinite(ry)
    in_rec = near & settled[np.clip(best_i, 0, None)]
    y01 = np.full(rt.size, np.nan)
    if in_rec.any():
        lab, split_why, lo_cut, hi_cut = pain_thirds(ry[in_rec])
        y01[in_rec] = lab
    else:
        split_why, lo_cut, hi_cut = "no pain rating fell inside the record", None, None
    out["pain_split"] = {"why": split_why, "low_cut": lo_cut, "high_cut": hi_cut}
    use = in_rec & np.isfinite(y01)
    out["record"] = {"hours_both_sides": hours, "n_stretches": len(grids), "dt_s": dt,
                     "n_ratings_in_record": int(near.sum()),
                     "n_ratings_in_opening": int((near & ~in_rec).sum()), "opening_s": warm_s,
                     "n_ratings_high": int((use & (y01 == 1)).sum()),
                     "n_ratings_low": int((use & (y01 == 0)).sum()),
                     "n_days": int(np.unique(rday[use]).size) if use.any() else 0}

    scored, draws_by = {}, {}
    for w, (drives, ctrls) in params_by_wiring.items():
        amps = {c: [] for c in SIDES}
        n_trans = 0
        for g in grids:
            r = run_stretch(g, drives, ctrls, k, tau_s=tau_s)
            for c in SIDES:
                amps[c].append(r[c]["amp"])
            n_trans += sum(r[c]["n_trans"] for c in SIDES)
        amp = {c: np.concatenate(amps[c]) for c in SIDES}
        drive = {c: (amp[c] - ctrls[c]["amp_low"]) / (ctrls[c]["amp_high"] - ctrls[c]["amp_low"]) for c in SIDES}
        at = {c: drive[c][best_i[use]] for c in SIDES}
        sc = score_wiring(at, y01[use], rday[use], n_boot=n_boot, seed=seed)
        scored[w] = sc["score"]
        draws_by[w] = sc["draws"][:, 2]
        hours_all = float(gt.size * dt / 3600.0)
        out["wirings"][w] = {
            "label": WIRING_LABELS[w], "scored": sc["score"] is not None,
            "score": sc["score"], "score_interval": _interval(sc["draws"][:, 2]),
            "auc": sc["auc"],
            "auc_interval": {c: _interval(sc["draws"][:, i]) for i, c in enumerate(SIDES)},
            "switches_per_hour": (n_trans / hours_all) if hours_all > 0 else None,
            "share_at_highest": {c: float(np.mean(np.abs(amp[c] - ctrls[c]["amp_high"]) <= ctrls[c]["tol"]))
                                 for c in SIDES},
            "mean_current_mA": {c: float(np.mean(amp[c])) for c in SIDES},
            "limits_mA": {c: [ctrls[c]["amp_low"], ctrls[c]["amp_high"]] for c in SIDES},
            "drives": dict(drives), "device_allows": allowed.get(w),
        }
        if sc["score"] is None:
            out["wirings"][w]["reason"] = (f"fewer than {MIN_PER_GROUP} pain ratings in the high or the "
                                           "low third inside the record")
    out["recommendation"] = recommend(scored, draws_by, allowed)
    return out
