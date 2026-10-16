"""The onset worked out for each band from its own record (the PI, 2026-10-04, decision 417).

WHY. Until now the parameter card's timing rows came from one table per participant
(`timing_recommendation.RECORD_DERIVED_TIMING_MS`, decision 150): the same 30 s onset whatever band
was chosen. The PI: the timing should be per band. Only the onset can honestly differ by band:

* the averaging stays 3 s for every band -- the nearest device value to the validated feature's
  4.1 s window (decision 150, section 3a);
* the ramps, the detection blanking and the start-up delay are values the record cannot decide
  (decision 150), so they stay as the participant's table has them, labelled as the same for every
  band -- except the blanking, which the same table sets equal to the onset, and so follows it.

THE RULE (the PI's choice, 2026-10-04: "fewest switches, none undone"). At 3 s averaging, for each onset the tablet
accepts (3 to 30 s in 3 s steps): place the band's thresholds from its own record -- its median
3 s averaged reading +- the separation its fitted noise model requires at that onset (the record
pair of decision 180, `design_rule`'s noise-only simulation at one false crossing an hour) --
replay the band's own recorded power through the controller (`robustness.run_many`, blanking equal
to the onset, the card's 30 s ramps, the plan's current limits) and count the switches undone
within one onset. Among the onsets with none undone, the one with the fewest switches an hour is
the band's onset (the shorter on a tie). The PI first chose the SHORTEST onset with none undone;
on RCS08 that picked 12 to 24 s onsets whose noise model needs a separation of +-60 to +-120, so
the pair spread across most of the band's range (the committed band 276/116 against 206/186 at
30 s), and on the committed band the undone count was not monotone in the onset (0 at 15 and 18 s,
1 at 21 s) on 1.8 h of recording; the fewest-switches pick keeps the pair narrow and does not rest
on one onset's count. An onset at which the noise model reaches no separation gets no pair and is
not a candidate. When no onset reaches zero undone, the one with the fewest undone is taken (the
shorter on a tie) and the answer says so. Only onsets whose replay spends at least
`LIMIT_MIN_FRAC` of the time at each current limit are candidates: a pair that is never crossed
undoes nothing and switches never, and would otherwise win.

WHAT IT CHANGES. The card's onset and blanking rows, the record pair placed at that onset (it reads
this answer's own separations, so the pair and the onset agree), and the simulation's
"recommended" regime. Saved per band (`KIND`), filed under the tiles, the recording set, the band,
the side and the current limits.
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
RULE_VERSION = "v1_fewest_switches_zero_undone_record_pair_3s_averaging"

#: The averaging every band is read at (decision 150, section 3a).
AVERAGING_S = 3.0
#: The onsets tried: every multiple of the averaging the tablet accepts on the Dual timers.
ONSET_GRID_S = tuple(float(o) for o in range(3, 31, 3) if o <= _DR.ONSET_RANGE_DUAL_MS[1] / 1000.0)
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


def _row_at(rows, onset_s):
    for r in rows or ():
        if abs(float(r.get("averaging_s", -1)) - AVERAGING_S) < 1e-6 \
                and abs(float(r.get("onset_s", -1)) - float(onset_s)) < 1e-6:
            return r
    return None


def choose_onset(stretches, rows: Sequence[Dict[str, Any]], *, median: float, amp_low: float,
                 amp_high: float) -> Dict[str, Any]:
    """The band's onset from its separation ``rows`` (``design_rule`` table rows) and its own
    ``stretches``, by the rule above. One replay over the stretches, vectorised across onsets."""
    table: List[Dict[str, Any]] = []
    for o in ONSET_GRID_S:
        r = _row_at(rows, o)
        half = None if r is None else r.get("min_separation")
        table.append({"onset_s": o, "half_separation": None if half is None else float(half),
                      "upper": None if half is None else float(median) + float(half),
                      "lower": None if half is None else float(median) - float(half),
                      "undone": None, "transitions_per_hour": None,
                      "frac_at_upper": None, "frac_at_lower": None, "controls": None})
    live = [r for r in table if r["upper"] is not None]
    if not live:
        return {"available": False, "rows": table,
                "reason": ("the band's noise model reaches no separation at any onset the tablet "
                           "accepts, so no thresholds can be placed and no onset tried")}
    if not stretches:
        return {"available": False, "rows": table, "reason": "no stretches of recording to replay"}
    ms = np.array([r["onset_s"] for r in live]) * 1000.0
    res = _rb.run_many(stretches, AVERAGING_S * 1000.0, np.array([r["upper"] for r in live]),
                       np.array([r["lower"] for r in live]), ms, ms,
                       np.full(len(live), RAMP_MS), np.full(len(live), RAMP_MS),
                       float(amp_low), float(amp_high))
    for i, r in enumerate(live):
        r["undone"] = int(res["reversals_within_one_onset"][i])
        r["transitions_per_hour"] = float(res["transitions_per_hour"][i])
        r["frac_at_upper"] = float(res["frac_time_at_upper_limit"][i])
        r["frac_at_lower"] = float(res["frac_time_at_lower_limit"][i])
    for r in live:
        r["controls"] = (r["frac_at_upper"] >= LIMIT_MIN_FRAC and r["frac_at_lower"] >= LIMIT_MIN_FRAC)
    live = [r for r in live if r["controls"]]
    if not live:
        return {"available": False, "rows": table, "hours_replayed": float(res["hours"]),
                "reason": (f"at no onset the tablet accepts does the band's replay spend at least "
                           f"{LIMIT_MIN_FRAC:.0%} of the time at each current limit, so no onset "
                           f"can be chosen from this band's record")}
    zero = [r for r in live if r["undone"] == 0]
    if zero:
        pick, reached = min(zero, key=lambda r: (r["transitions_per_hour"], r["onset_s"])), True
    else:
        pick, reached = min(live, key=lambda r: (r["undone"], r["onset_s"])), False
    return {"available": True, "onset_s": pick["onset_s"], "zero_undone_reached": reached,
            "pick": dict(pick), "rows": table, "averaging_s": AVERAGING_S, "ramp_ms": RAMP_MS,
            "hours_replayed": float(res["hours"]), "median": float(median),
            "rule_version": RULE_VERSION}


def band_timing_for_series(t, power, amp_obs, *, amp_low, amp_high) -> Dict[str, Any]:
    """Fit the band's noise model, read its separation at each onset, and choose the onset."""
    from . import threshold_placement as _tpl
    if amp_low is None or amp_high is None:
        return {"available": False, "reason": "no adaptive current limits to replay with"}
    med = _tpl.median_level(t, power, averaging_s=AVERAGING_S)
    if not med.get("available"):
        return {"available": False, "reason": med.get("reason")}
    m = float(med["median"])
    design = _dr.design_rule_for_series(t, power, amp_obs, upper=m, lower=m,
                                        averaging_grid=(AVERAGING_S,), onset_grid=ONSET_GRID_S)
    if design.get("refused"):
        return {"available": False, "reason": f"the noise model was refused: {design.get('reason')}"}
    out = choose_onset(stretches_for(t, power, amp_obs), design.get("table") or [], median=m,
                       amp_low=amp_low, amp_high=amp_high)
    out["model"] = design.get("model")
    out["design_rows"] = design.get("table") or []
    return out
