"""The averaging and the onset worked out together for each band from its own record (the PI,
2026-10-18, item 3; the onset alone since 2026-10-04, decision 417).

WHY. Until 2026-10-04 the parameter card's timing rows came from one table per participant
(`timing_recommendation.RECORD_DERIVED_TIMING_MS`, decision 150): the same 30 s onset whatever band
was chosen. Decision 417 worked the onset out per band, at 3 s averaging for every band ("for
response time", decision 150). On 2026-10-18 the PI approved choosing the averaging too: the 3 s
streaming readings are nearly independent (lag-1 correlation 0.08-0.19), most of their variance
sits at periods under 10 s, and pain changes over days, so a longer average can cost little
response and remove much scatter.

* averaging: every multiple of 3 s the tablet accepts, 3 to 30 s (`AVERAGING_GRID_S`; the
  simulation works on 3 s pieces, so 3 s is the step);
* onset: at each averaging, every whole number of averaged readings up to the tablet's 30 s
  (`onsets_for`): 3 to 30 s in 3 s steps at 3 s averaging, 9, 18 and 27 s at 9 s, 30 s alone at
  30 s. The device counts the onset in averaged readings, so an onset that is not a whole number of
  them is the next whole number (decision 150) and is not tried twice;
* the ramps, the detection blanking and the start-up delay are values the record cannot decide
  (decision 150), so they stay as the participant's table has them, labelled as the same for every
  band -- except the blanking, which the same table sets equal to the onset, and so follows it.

THE RULE (the PI's choice, 2026-10-04: "fewest switches, none undone"; unchanged, now over both).
For each averaging and onset pair: place the band's thresholds from its own record AT THAT
AVERAGING -- its median reading averaged over that window +- the separation its fitted noise model
requires at that pair (the record pair of decision 180, `design_rule`'s noise-only simulation at one
false crossing an hour) -- replay the band's own recorded power through the controller at that
averaging (`robustness.run_many`, blanking equal to the onset, the card's 30 s ramps, the plan's
current limits) and count the switches undone within one onset. Only pairs whose replay spends at
least `LIMIT_MIN_FRAC` of the time at each current limit are candidates (a pair never crossed
undoes nothing and switches never, and would otherwise win). Among those with none undone, the one
with the fewest switches an hour wins; on a tie, the shorter averaging, then the shorter onset.
When none reaches zero undone, the one with the fewest undone (then the shorter averaging and
onset) is taken and the answer says so. A pair at which the noise model reaches no separation gets
no thresholds and is not a candidate.

History of the onset rule (decision 417): the PI first chose the SHORTEST onset with none undone;
on RCS08 that picked 12 to 24 s onsets whose noise model needs a separation of +-60 to +-120, so the
pair spread across most of the band's range; the fewest-switches pick keeps the pair narrow.

WHAT IT CHANGES. The card's averaging, onset and blanking rows, the record pair placed at that
averaging and onset (it reads this answer's own separations and the median at the chosen
averaging, so the pair and the timing agree), and the simulation's "recommended" regime. Saved per
band (`KIND`), filed under the tiles, the recording set, the band, the side and the current limits;
`RULE_VERSION` moved with the rule, so every older answer is rebuilt rather than served.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from . import design_rule as _dr
from . import robustness as _rb

try:
    from modules.DecodeCommon import device_ranges as _DR
except ImportError:                                              # pragma: no cover
    from DecodeCommon import device_ranges as _DR

KIND = "closed_loop_band_timing"
RULE_VERSION = "v2_averaging_and_onset_together_fewest_switches_zero_undone_record_pair"

#: The length of one recorded piece the simulation works on, and the shortest averaging tried
#: (the only one until 2026-10-18, decision 150, section 3a).
AVERAGING_S = 3.0
#: The averagings tried: every multiple of the 3 s piece the tablet accepts (0 to 30 s).
AVERAGING_GRID_S = tuple(float(a) for a in range(3, 31, 3)
                         if a <= _DR.AVERAGING_RANGE_MS[1] / 1000.0)
#: The onsets tried at 3 s averaging: every multiple of 3 s the tablet accepts on the Dual timers.
ONSET_GRID_S = tuple(float(o) for o in range(3, 31, 3) if o <= _DR.ONSET_RANGE_DUAL_MS[1] / 1000.0)


def onsets_for(averaging_s):
    """The onsets tried at one averaging: every whole number of averaged readings the tablet's
    onset accepts (up to 30 s)."""
    a = float(averaging_s)
    top = _DR.ONSET_RANGE_DUAL_MS[1] / 1000.0
    return tuple(float(a * k) for k in range(1, int(top // a) + 1) if a * k <= top + 1e-9)
#: The card's ramps (decision 150's table: the record cannot decide them), used in the replay.
RAMP_MS = 30000.0
#: A pair counts only when the replayed controller spends at least this share of the time at EACH
#: current limit -- the robustness check's own floor (`robustness.LIMIT_MIN_FRAC`). Without it the
#: fewest-switches pick took a pair so wide it is never crossed (RCS08's committed band on 31.2 h:
#: 24 s at +-300, 518 / -82, no switch at all), because a controller that never acts never switches.
LIMIT_MIN_FRAC = _rb.LIMIT_MIN_FRAC


def stretches_for(t, power, amp_obs):
    """The series cut into continuous stretches, exactly as the robustness check cuts it."""
    stretches, _why, _info = _rb.stretches_from_series(t, power, amp_obs)
    return stretches


def _row_at(rows, onset_s, averaging_s=AVERAGING_S):
    for r in rows or ():
        if abs(float(r.get("averaging_s", -1)) - float(averaging_s)) < 1e-6 \
                and abs(float(r.get("onset_s", -1)) - float(onset_s)) < 1e-6:
            return r
    return None


def choose_timing(stretches, rows: Sequence[Dict[str, Any]], *, medians: Dict[float, float],
                  amp_low: float, amp_high: float) -> Dict[str, Any]:
    """The band's averaging and onset from its separation ``rows`` (``design_rule`` table rows,
    any averagings) and its own ``stretches``, by the rule above. ``medians`` maps each averaging
    to the band's median reading at it; an averaging absent from ``medians`` is not tried. One
    replay over the stretches per averaging, vectorised across that averaging's onsets."""
    table: List[Dict[str, Any]] = []
    for a in AVERAGING_GRID_S:
        if a not in medians:
            continue
        med = float(medians[a])
        for o in onsets_for(a):
            r = _row_at(rows, o, a)
            half = None if r is None else r.get("min_separation")
            table.append({"averaging_s": a, "onset_s": o,
                          "half_separation": None if half is None else float(half),
                          "upper": None if half is None else med + float(half),
                          "lower": None if half is None else med - float(half),
                          "undone": None, "transitions_per_hour": None,
                          "frac_at_upper": None, "frac_at_lower": None, "controls": None})
    live = [r for r in table if r["upper"] is not None]
    if not live:
        return {"available": False, "rows": table,
                "reason": ("the band's noise model reaches no separation at any averaging and "
                           "onset the tablet accepts, so no thresholds can be placed and no "
                           "timing tried")}
    if not stretches:
        return {"available": False, "rows": table, "reason": "no stretches of recording to replay"}
    hours = {}
    for a in sorted({r["averaging_s"] for r in live}):
        grp = [r for r in live if r["averaging_s"] == a]
        ms = np.array([r["onset_s"] for r in grp]) * 1000.0
        res = _rb.run_many(stretches, a * 1000.0, np.array([r["upper"] for r in grp]),
                           np.array([r["lower"] for r in grp]), ms, ms,
                           np.full(len(grp), RAMP_MS), np.full(len(grp), RAMP_MS),
                           float(amp_low), float(amp_high))
        hours[a] = float(res["hours"])
        for i, r in enumerate(grp):
            r["undone"] = int(res["reversals_within_one_onset"][i])
            r["transitions_per_hour"] = float(res["transitions_per_hour"][i])
            r["frac_at_upper"] = float(res["frac_time_at_upper_limit"][i])
            r["frac_at_lower"] = float(res["frac_time_at_lower_limit"][i])
    for r in live:
        r["controls"] = (r["frac_at_upper"] >= LIMIT_MIN_FRAC and r["frac_at_lower"] >= LIMIT_MIN_FRAC)
    hours_replayed = max(hours.values()) if hours else float("nan")
    live = [r for r in live if r["controls"]]
    if not live:
        return {"available": False, "rows": table, "hours_replayed": hours_replayed,
                "reason": (f"at no averaging and onset the tablet accepts does the band's replay "
                           f"spend at least {LIMIT_MIN_FRAC:.0%} of the time at each current "
                           f"limit, so no timing can be chosen from this band's record")}
    zero = [r for r in live if r["undone"] == 0]
    if zero:
        pick, reached = min(zero, key=lambda r: (r["transitions_per_hour"], r["averaging_s"],
                                                 r["onset_s"])), True
    else:
        pick, reached = min(live, key=lambda r: (r["undone"], r["averaging_s"], r["onset_s"])), False
    return {"available": True, "averaging_s": pick["averaging_s"], "onset_s": pick["onset_s"],
            "zero_undone_reached": reached, "pick": dict(pick), "rows": table,
            "ramp_ms": RAMP_MS, "hours_replayed": hours[pick["averaging_s"]],
            "median": float(medians[pick["averaging_s"]]),
            "medians_by_averaging": {f"{a:g}": float(m) for a, m in sorted(medians.items())},
            "rule_version": RULE_VERSION}


def choose_onset(stretches, rows: Sequence[Dict[str, Any]], *, median: float, amp_low: float,
                 amp_high: float) -> Dict[str, Any]:
    """`choose_timing` at 3 s averaging alone (decision 417's search, kept for its callers and
    tests): the onset from ``rows`` at 3 s, with ``median`` the band's 3 s median."""
    return choose_timing(stretches, rows, medians={AVERAGING_S: float(median)},
                         amp_low=amp_low, amp_high=amp_high)


def band_timing_for_series(t, power, amp_obs, *, amp_low, amp_high,
                           averaging_grid: Sequence[float] = AVERAGING_GRID_S) -> Dict[str, Any]:
    """Fit the band's noise model, read its separation at each averaging and onset, and choose.

    At each averaging the median is the band's own reading averaged over that window
    (`threshold_placement.median_level`) and the design rule is asked at that averaging's onsets
    only (`design_rule.design_rule_for_series`, its fitted model kept per series, so the model is
    fitted once). At 3 s the call is exactly decision 417's, so its rows are unchanged."""
    from . import threshold_placement as _tpl
    if amp_low is None or amp_high is None:
        return {"available": False, "reason": "no adaptive current limits to replay with"}
    medians: Dict[float, float] = {}
    rows: List[Dict[str, Any]] = []
    first_design = None
    for a in averaging_grid:
        a = float(a)
        med = _tpl.median_level(t, power, averaging_s=a)
        if not med.get("available"):
            if a == AVERAGING_S:
                return {"available": False, "reason": med.get("reason")}
            continue
        m = float(med["median"])
        design = _dr.design_rule_for_series(t, power, amp_obs, upper=m, lower=m,
                                            averaging_grid=(a,), onset_grid=onsets_for(a))
        if design.get("refused"):
            if a == AVERAGING_S:
                return {"available": False,
                        "reason": f"the noise model was refused: {design.get('reason')}"}
            continue
        if first_design is None:
            first_design = design
        medians[a] = m
        rows.extend(design.get("table") or [])
    if not medians:
        return {"available": False, "reason": "no averaging gave a median reading"}
    out = choose_timing(stretches_for(t, power, amp_obs), rows, medians=medians,
                        amp_low=amp_low, amp_high=amp_high)
    out["model"] = (first_design or {}).get("model")
    out["design_rows"] = rows
    return out
