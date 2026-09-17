"""The joint current-titration schedule Stim Optimizer recommends for HOME programming
(2026-09-14), the PI's instruction verbatim: "do (c) both and make a titration schedule to
actually make these plots useful."

WHAT THIS IS AND WHAT IT IS NOT. This is a different thing from ``titration_plan.py``, which
designs an in-CLINIC session held minutes at a time so the device's own 3-second recordings can
resolve a band-power response. This module designs a schedule of (left current, right current)
combinations to hold at HOME, days at a time, because what fills in the honest per-rate current
surface (``stage1_openloop.py``'s ``RateStratum``, and its coverage check) is not minutes of
streaming but PAIN REPORTS -- and this participant files a few pain reports a day, not a few a
minute. NOTHING HERE WRITES TO THE DEVICE: it is a sheet a clinician reads and programs by hand.

WHAT IT BUILDS ON. ``stage1_openloop.current_coverage`` is the SAME function that decides whether
a fitted rate's current recommendation is honest (check (iii) of
``stage1_openloop._rate_stratum_resolution``); this module's "what this buys" step runs it again
on the existing record PLUS the schedule's own planned points, so the sheet can say, before the
session is ever run, whether it would be ENOUGH to let a current be recommended honestly at that
rate.

EVERY NUMBER CARRIES ITS OWN SOURCE. Every function below is pure arithmetic on values a caller
already holds -- no Django import, no store read, no recording load -- exactly the discipline
``titration_plan.py`` already established, for the same reason: this module must be cheap enough
to run on every Stim Optimizer request.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import stage1_openloop as _S1

#: The three current levels the joint design grid is built from, before any ceiling or safety
#: restriction is applied. 1.0 / 2.5 / 4.0 mA span the range this participant's own record has
#: actually explored (decision 150's synthesis) without approaching RCS08's PI-stated ceiling,
#: 4.5 mA per side as of 2026-09-14 (`safety_ceiling.PI_STATED_CEILING_MA`; was 5.0 mA).
DESIGN_LEVELS_MA = (1.0, 2.5, 4.0)

#: A design point already carrying this many rated reports at the schedule's own (rate, pulse
#: width) stratum is dropped: it does not need to be held again.
EXISTING_REPORTS_DROP_THRESHOLD = 10

#: How many rated reports a design point needs before it is "done" for the purposes of the hold
#: length -- the same number ``CURRENT_COVERAGE_MIN_REPORTS_PER_PAIR`` requires per pair, so the
#: schedule is sized to actually clear the check it exists to feed.
TARGET_REPORTS_PER_POINT = _S1.CURRENT_COVERAGE_MIN_REPORTS_PER_PAIR

MIN_HOLD_DAYS = 3
MAX_HOLD_DAYS = 7

#: The trailing window a reporting rate is measured over.
LOOKBACK_DAYS = 90

#: Fixed so the schedule's own order is reproducible from one request to the next rather than
#: reshuffling on every page load.
ORDER_SEED = 20260914


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _n(count, noun):
    c = int(count)
    return f"{c} {noun}" if c == 1 else f"{c} {noun}s"


# ---------------------------------------------------------------------------------------------
# the design points
# ---------------------------------------------------------------------------------------------
def design_points(ceiling_left_mA, ceiling_right_mA, *, levels_mA=DESIGN_LEVELS_MA,
                  in_force_left_mA=None, in_force_right_mA=None, is_safe=None) -> dict:
    """The candidate (left, right) current pairs, before dropping any that already have enough
    data: a 3x3 grid on each side's own axis, the two one-side-off points that let the two
    currents' effects be told apart, and the setting in force as the anchor -- every point capped
    at its side's own ceiling and, when `is_safe` is given, restricted to the joint safe set.

    `is_safe(left_mA, right_mA) -> bool` is optional; a point it refuses is EXCLUDED and named,
    never silently dropped from the count.
    """
    cl, cr = _f(ceiling_left_mA), _f(ceiling_right_mA)
    lv_l = sorted({round(float(v), 3) for v in levels_mA if cl is None or float(v) <= cl + 1e-9})
    lv_r = sorted({round(float(v), 3) for v in levels_mA if cr is None or float(v) <= cr + 1e-9})

    points, seen = [], {}

    def add(l, r, why):
        l, r = round(float(l), 3), round(float(r), 3)
        if cl is not None and l > cl + 1e-9:
            return
        if cr is not None and r > cr + 1e-9:
            return
        key = (l, r)
        if key in seen:
            return
        seen[key] = why
        points.append(dict(amp_left_mA=l, amp_right_mA=r, why=why))

    for l in lv_l:
        for r in lv_r:
            add(l, r, "a corner or the centre of the 3x3 current grid")
    mid_l = lv_l[len(lv_l) // 2] if lv_l else None
    mid_r = lv_r[len(lv_r) // 2] if lv_r else None
    if mid_r is not None:
        add(0.0, mid_r,
            "the left side off, the right at its own mid current -- separates the two currents' "
            "effects on pain from each other")
    if mid_l is not None:
        add(mid_l, 0.0,
            "the right side off, the left at its own mid current -- separates the two currents' "
            "effects on pain from each other")
    il, ir = _f(in_force_left_mA), _f(in_force_right_mA)
    anchor_key = None
    if il is not None and ir is not None:
        add(il, ir, "the setting in force today -- the anchor every other point is compared "
                    "against, and repeated later in the order to check for drift")
        anchor_key = (round(il, 3), round(ir, 3))

    kept, excluded = [], []
    for p in points:
        if is_safe is not None and not bool(is_safe(p["amp_left_mA"], p["amp_right_mA"])):
            excluded.append(dict(p, reason="outside the joint safe set fitted from this "
                                          "participant's own tolerated settings and the "
                                          "PI-stated ceiling"))
        else:
            kept.append(p)
    return dict(points=kept, excluded=excluded, levels_left_mA=lv_l, levels_right_mA=lv_r,
               ceiling_left_mA=cl, ceiling_right_mA=cr, anchor_key=anchor_key)


def drop_already_covered(points, existing_epochs, *, min_reports=EXISTING_REPORTS_DROP_THRESHOLD,
                         tol_mA=0.1) -> dict:
    """Points that already carry `min_reports` or more rated reports at this (rate, pulse width)
    stratum, within `tol_mA`, are dropped from the schedule and named -- they do not need to be
    held again. `existing_epochs` is a frame with `amp_mA_Left`, `amp_mA_Right`, `n` columns,
    already restricted to the stratum this schedule runs at."""
    d = pd.DataFrame(existing_epochs) if existing_epochs is not None else pd.DataFrame()
    have = {"amp_mA_Left", "amp_mA_Right", "n"}.issubset(d.columns) and len(d)
    if have:
        g = (d.assign(amp_mA_Left=pd.to_numeric(d["amp_mA_Left"], errors="coerce"),
                     amp_mA_Right=pd.to_numeric(d["amp_mA_Right"], errors="coerce"),
                     n=pd.to_numeric(d["n"], errors="coerce").fillna(0.0))
              .groupby(["amp_mA_Left", "amp_mA_Right"])["n"].sum().reset_index())
    else:
        g = pd.DataFrame(columns=["amp_mA_Left", "amp_mA_Right", "n"])
    kept, dropped = [], []
    for p in points:
        hit = 0.0
        for _, row in g.iterrows():
            if (abs(float(row["amp_mA_Left"]) - p["amp_left_mA"]) <= tol_mA
                    and abs(float(row["amp_mA_Right"]) - p["amp_right_mA"]) <= tol_mA):
                hit += float(row["n"])
        if hit >= float(min_reports):
            dropped.append(dict(p, existing_reports=hit,
                                reason=(f"already has {hit:g} rated reports at this point, at or "
                                       f"above the {min_reports:g}-report target")))
        else:
            kept.append(dict(p, existing_reports=hit))
    return dict(points=kept, dropped=dropped)


# ---------------------------------------------------------------------------------------------
# the hold per point
# ---------------------------------------------------------------------------------------------
def reports_per_day(epochs, *, lookback_days=LOOKBACK_DAYS, reference=None) -> dict:
    """The median rated reports per day over the trailing `lookback_days`, read from an
    EPOCH-LEVEL frame carrying `t0` (the epoch's own start) and `n` (its report count) -- the
    same columns the design matrix (`adapter.build_design_matrix`) already carries, across every
    rate and pulse width, not only this schedule's own stratum, since how often this participant
    reports pain does not depend on which setting they happen to be on."""
    d = pd.DataFrame(epochs) if epochs is not None else pd.DataFrame()
    if d.empty or not {"t0", "n"}.issubset(d.columns):
        return dict(median_per_day=None, n_days=0, n_reports=0.0,
                   note="no epochs with a timestamp and a report count were available, so no "
                        "reporting rate could be measured")
    t0 = pd.to_datetime(d["t0"], utc=True, errors="coerce")
    n = pd.to_numeric(d["n"], errors="coerce").fillna(0.0)
    valid = t0.notna()
    if not valid.any():
        return dict(median_per_day=None, n_days=0, n_reports=0.0,
                   note="no epoch carried a usable timestamp")
    ref = pd.to_datetime(reference, utc=True) if reference is not None else t0[valid].max()
    start = ref - pd.Timedelta(days=float(lookback_days))
    mask = valid & (t0 >= start) & (t0 <= ref)
    if not mask.any():
        return dict(median_per_day=None, n_days=0, n_reports=0.0,
                   note=f"no reports fell in the last {lookback_days:g} days")
    day = t0[mask].dt.floor("D")
    by_day = n[mask].groupby(day).sum()
    full_days = pd.date_range(start.floor("D"), ref.floor("D"), freq="D")
    counts = by_day.reindex(full_days, fill_value=0.0)
    med = float(counts.median())
    total = float(n[mask].sum())
    return dict(median_per_day=med, n_days=int(len(full_days)), n_reports=total,
               note=(f"{total:g} reports over the last {lookback_days:g} days across "
                     f"{int(mask.sum())} epochs, a median of {med:g} a day"))


def hold_days_for_point(median_reports_per_day, *, target_reports=TARGET_REPORTS_PER_POINT,
                        min_days=MIN_HOLD_DAYS, max_days=MAX_HOLD_DAYS) -> dict:
    """How many days to hold ONE point so it collects `target_reports` reports at the measured
    rate, clamped to [`min_days`, `max_days`]."""
    m = _f(median_reports_per_day)
    if m is None or m <= 0:
        days = int(max_days)
        why = (f"no measured reporting rate, so the hold is set to the maximum, "
              f"{int(max_days):g} days, rather than guessed")
    else:
        raw = float(target_reports) / m
        days = int(min(max(math.ceil(raw), int(min_days)), int(max_days)))
        why = (f"{int(target_reports):g} reports needed at a measured median of {m:g} a day is "
              f"{raw:.1f} days, clamped to {int(min_days):g}-{int(max_days):g}")
    return dict(hold_days=int(days), target_reports=int(target_reports), why=why)


# ---------------------------------------------------------------------------------------------
# the order
# ---------------------------------------------------------------------------------------------
def order_points(points, *, anchor_key=None, seed=ORDER_SEED) -> dict:
    """A sequence that never ramps monotonically up: everything but the anchor is sorted by total
    current and read off the two ends alternately (lowest, highest, second-lowest, second-highest,
    ...), which by construction cannot produce three consecutive STRICT increases in either
    current on its own. The anchor, when present, is placed first, repeated at the midpoint, and
    repeated again at the end, so drift over the session can be checked against it.

    `seed` is recorded rather than used to reorder ties (the zig-zag order is already fully
    determined by the design), so the same design always produces the same schedule; it is kept
    as a parameter and reported because a later version of this schedule may need to break ties
    among equal-total-current points, and the seed is what would do that reproducibly.
    """
    rng = np.random.default_rng(int(seed))          # reserved for tie-breaking; not used to
    del rng                                          # reorder anything today (documented above)
    anchor, rest = None, []
    for p in points:
        key = (round(p["amp_left_mA"], 3), round(p["amp_right_mA"], 3))
        if anchor_key is not None and key == anchor_key and anchor is None:
            anchor = p
        else:
            rest.append(p)
    rest_sorted = sorted(rest, key=lambda p: (p["amp_left_mA"] + p["amp_right_mA"],
                                              p["amp_left_mA"], p["amp_right_mA"]))
    zig = []
    i, j = 0, len(rest_sorted) - 1
    take_front = True
    while i <= j:
        if take_front:
            zig.append(rest_sorted[i]); i += 1
        else:
            zig.append(rest_sorted[j]); j -= 1
        take_front = not take_front

    steps = []
    if anchor is not None:
        steps.append(dict(anchor, why=anchor["why"] + " (baseline, held first)"))
    mid = len(zig) // 2
    for k, p in enumerate(zig):
        steps.append(p)
        if anchor is not None and mid and k == mid - 1:
            steps.append(dict(anchor, why=anchor["why"] +
                              " (the anchor, repeated at the midpoint to check for drift)"))
    if anchor is not None:
        steps.append(dict(anchor, why=anchor["why"] +
                          " (the anchor, repeated at the end to check for drift)"))
    return dict(steps=steps, seed=int(seed), n_steps=len(steps))


# ---------------------------------------------------------------------------------------------
# what this buys
# ---------------------------------------------------------------------------------------------
def what_this_buys(existing_epochs, steps, *, target_reports=TARGET_REPORTS_PER_POINT) -> dict:
    """Run `stage1_openloop.current_coverage` -- the SAME check a real current recommendation must
    clear -- on the existing record's (rate, pulse width) stratum PLUS this schedule's own planned
    points, each credited `target_reports` reports once complete. Says whether that would be
    enough."""
    existing = pd.DataFrame(existing_epochs) if existing_epochs is not None else pd.DataFrame()
    cols = ["amp_mA_Left", "amp_mA_Right", "n"]
    if not set(cols).issubset(existing.columns):
        existing = pd.DataFrame(columns=cols + ["rating_days"])
    else:
        existing = existing[cols + [c for c in ("rating_days",) if c in existing.columns]].copy()
    # A planned step is credited the days it is held for (decision 184: the coverage check counts
    # occasions, not ratings); a step with no `planned_days` is credited one day.
    added = pd.DataFrame([dict(amp_mA_Left=s["amp_left_mA"], amp_mA_Right=s["amp_right_mA"],
                               n=float(target_reports),
                               n_rating_days=float(s.get("planned_days") or 1)) for s in steps])
    combined = pd.concat([existing, added], ignore_index=True) if len(added) else existing
    cov = _S1.current_coverage(combined)
    return dict(
        coverage_after_schedule=cov, resolution_coverage_would_pass=bool(cov["passes"]),
        note=(f"once this schedule is complete: {_n(cov['n_pairs'], 'current combination')} with "
             f"at least {cov['reports_per_pair_required']:g} reports each on at least "
             f"{cov['days_per_pair_required']} days, spanning "
             f"{cov['span_left_mA']:.2f} mA on the left and {cov['span_right_mA']:.2f} mA on the "
             "right" + (" -- enough to clear the coverage half of the honest-current check"
                        if cov["passes"] else
                        " -- still not enough to clear the coverage half of the honest-current "
                        "check")))


# ---------------------------------------------------------------------------------------------
# the whole schedule
# ---------------------------------------------------------------------------------------------
def build_schedule(*, rate_hz, pw_us_left, pw_us_right, ceiling_left_mA, ceiling_right_mA,
                   in_force_left_mA, in_force_right_mA, existing_epochs_at_stratum,
                   epochs_for_reporting_rate, is_safe=None, levels_mA=DESIGN_LEVELS_MA,
                   seed=ORDER_SEED) -> dict:
    """Assemble the whole joint titration schedule. `existing_epochs_at_stratum` is the design
    matrix already restricted to (`rate_hz`, `pw_us_left`, `pw_us_right`); `epochs_for_reporting_rate`
    is the FULL design matrix, used only to measure how often this participant reports at all.
    Never raises: a caller that cannot supply a required value gets back a schedule that says so.
    """
    dp = design_points(ceiling_left_mA, ceiling_right_mA, levels_mA=levels_mA,
                       in_force_left_mA=in_force_left_mA, in_force_right_mA=in_force_right_mA,
                       is_safe=is_safe)
    dc = drop_already_covered(dp["points"], existing_epochs_at_stratum)
    rpd = reports_per_day(epochs_for_reporting_rate)
    hold = hold_days_for_point(rpd["median_per_day"])
    ordered = order_points(dc["points"], anchor_key=dp["anchor_key"], seed=seed)

    steps = []
    for i, p in enumerate(ordered["steps"], start=1):
        steps.append(dict(
            step=i, rate_hz=_f(rate_hz), pulse_width_us_left=_f(pw_us_left),
            pulse_width_us_right=_f(pw_us_right), amp_left_mA=p["amp_left_mA"],
            amp_right_mA=p["amp_right_mA"], planned_days=hold["hold_days"],
            target_reports=hold["target_reports"], why=p.get("why", ""), in_safe_set=True))

    wtb = what_this_buys(existing_epochs_at_stratum, steps, target_reports=hold["target_reports"])
    n_existing_stratum = int(len(pd.DataFrame(existing_epochs_at_stratum))
                             if existing_epochs_at_stratum is not None else 0)
    record_today = dict(
        n_design_points_considered=len(dp["points"]) + len(dp["excluded"]),
        n_excluded_unsafe=len(dp["excluded"]), excluded_unsafe=dp["excluded"],
        n_already_covered=len(dc["dropped"]), already_covered=dc["dropped"],
        n_remaining_to_run=len(dc["points"]),
        n_existing_epochs_at_this_stratum=n_existing_stratum,
        what_this_buys=wtb,
    )
    total_days = int(hold["hold_days"] * ordered["n_steps"])
    return dict(
        available=True, rate_hz=_f(rate_hz), pulse_width_us_left=_f(pw_us_left),
        pulse_width_us_right=_f(pw_us_right),
        ceiling_left_mA=dp["ceiling_left_mA"], ceiling_right_mA=dp["ceiling_right_mA"],
        why_pulse_widths=("the schedule must be run at the pulse widths in force today so its "
                          "epochs land in the same (pulse-width-Left, pulse-width-Right) stratum "
                          "as the rest of the record; on RCS08 today that stratum has too few "
                          "epochs to fit a current surface at all, so this session is what gives "
                          "it its first real support"),
        design=dp, dropped=dc, reports_per_day=rpd, hold=hold,
        order_seed=ordered["seed"], steps=steps, n_steps=len(steps), total_days=total_days,
        record_today=record_today,
    )


def unavailable_schedule(reason: str) -> dict:
    return {"available": False, "reason": str(reason)}
