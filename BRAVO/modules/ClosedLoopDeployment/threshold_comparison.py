"""Programmed now against candidate thresholds, on the home record (the PI, 2026-10-26: "update C7 to
compare the current settings or what was set in clinic with what might be optimal ... consider
possible improvements"). A LABEL ONLY: it changes no threshold, verdict, gate or saved answer.

WHAT IT COMPARES. The two thresholds the device is running now (read from the newest device
export: the active group in `Groups.Final`, its `SensingChannel` entries), and three candidates on
the band of the report:
  (a) the pair this report places from clinic recordings (decision 180, kept by C7, decision 495);
  (b) the manufacturer's guidance: the 25th and 75th percentiles of DAYTIME (07:00-20:00 California)
      home-record power at the band (Busch et al. 2025, "per manufacturer guidance"; decision 503);
  (c) an upper threshold chosen so that the "above" state best separates higher from lower pain on
      the EARLIER 70% of the matched reports only, and then read on the later 30% (never fitted on
      them), with the lower threshold at the 25th percentile as in (b).
Each row is read on the home record (chronic log: the device's own 10-minute averages, the same
scale as the thresholds, decision 503, documented not measured): the share of readings above,
between and below, day and night; the share of time the device would hold the upper current (the
10-minute readings run through the Dual mode's rule: up after a reading above the upper threshold,
down after one below the lower, held between); the noise-only crossings an hour from the stored
design rule, where it applies; and the pain score when power was above, between or below (each
report takes the one 10-minute reading whose average covers it, C5), with the median and its
interval per state and the difference with a rotation test. Raw power only, never log power; one
contact pair, never pooled.

WHICH READINGS. A home reading counts for a band when the device's own sensing frequency at its
time (the chronic schedule's `FreqScheduleHz`, unrounded) is within 0.5 Hz of the band's centre,
the nearest such frequency (C5's rule). The schedule is read unrounded. The band labeller the
other pages use (`representation.snap_freq`) stopped at 26.4 Hz until 2026-10-27, filing 27.34 and
28.32 Hz sensing as 26.4 Hz (found on 2026-10-26); it now runs on the device's 250/256 Hz bins to
125 Hz, so it files the same readings at 27.3 and 28.3 Hz and the two agree.

WHAT IT CANNOT SHOW. The pain reports with a home reading at one band are few and all filed by day;
there is no randomised comparison; a difference on one visit day or one fortnight is not evidence
that a candidate is better. A clinician programs the device; nothing here writes to it.

Neutral `BRAVO_THRESHOLD_COMPARISON=0`: the block is not built and the report is as before.
"""
from __future__ import annotations

import os as _os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

#: The neutral setting (`BRAVO_THRESHOLD_COMPARISON=0`): no block.
ENABLED = _os.environ.get("BRAVO_THRESHOLD_COMPARISON", "1").strip() != "0"
VERSION = "v1_programmed_vs_candidates_home_record"
#: Daytime, California local hours [start, end): the manufacturer guidance's daytime.
DAY_HOURS = (7, 20)
#: The manufacturer guidance's percentiles of daytime home power (Busch et al. 2025).
GUIDANCE_PERCENTILES = (25.0, 75.0)
#: The upper-threshold grid (percentiles of the earlier daytime home power) candidate (c) searches.
FIT_PERCENTILES = tuple(range(50, 95, 5))
#: The share of matched reports, by time, candidate (c) is fitted on (C8's 70% cut).
FIT_SHARE = 0.7
#: Fewest matched reports in each state before a difference is given (above vs the rest).
MIN_PER_STATE = 2
#: Fewest earlier reports on each side of a grid threshold for candidate (c) to consider it.
MIN_FIT_PER_SIDE = 3
#: A frequency counts for a band centre only when it is LESS than this far from it (C5's rule).
MAX_CENTRE_GAP_HZ = 0.5
N_BOOT = 2000
SEED = 20261026
TZ = "America/Los_Angeles"

ROW_PROGRAMMED = "programmed"
ROW_CLINIC = "clinic_recordings"
ROW_GUIDANCE = "manufacturer_guidance"
ROW_FITTED = "fitted_on_earlier_reports"
ROW_LABELS = {
    ROW_PROGRAMMED: "Programmed now",
    ROW_CLINIC: "(a) Clinic recordings",
    ROW_GUIDANCE: "(b) Daytime 25th/75th",
    ROW_FITTED: "(c) Fitted, earlier reports",
}
WHAT = ("The thresholds the device runs now beside three candidates, each read on the home record "
        "(the device's own 10-minute averages at the band): the share of readings above, between and "
        "below, day (07:00-20:00) and night; the share of time the device would hold the upper "
        "current; and the pain score when power was above against the rest. A label only: it changes "
        "no threshold, verdict or gate.")
LIMITS_FIXED = ("No randomised comparison: the reports were not assigned to thresholds. A difference "
                "here over a few days is not evidence that a candidate is better. A clinician programs "
                "the device; nothing here writes to it.")
LABELLER_NOTE = ("Home readings are taken at the device's own sensing frequency; the other pages file "
                 "the same readings by the device's 0.98 Hz bins (27.34 Hz as 27.3, 28.32 Hz as 28.3).")
DUTY_WHAT = ("share of 10-minute readings after which the Dual mode would hold the upper current: up after "
             "a reading above the upper threshold, down after one below the lower, held between; the "
             "device decides on its own averaging (seconds), so this is an estimate")


# ---------------------------------------------------------------------------------------------
# The programmed configuration, from one decoded device export
# ---------------------------------------------------------------------------------------------
_PAIR_WORDS = {"ZERO_AND_THREE": "ZERO_THREE", "ONE_AND_THREE": "ONE_THREE", "ZERO_AND_TWO": "ZERO_TWO",
               "ZERO_AND_ONE": "ZERO_ONE", "TWO_AND_THREE": "TWO_THREE", "ONE_AND_TWO": "ONE_TWO"}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _tail(v):
    s = str(v or "").split(".")[-1]
    return s or None


def programmed_adaptive(export: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The adaptive configuration the device runs, from one decoded export: the ACTIVE group in
    `Groups.Final` (the groups as the device left the session), each side's `SensingChannel` entry.
    Pure; ``{"available": False, ...}`` when there is no active group with sensing.

    Per side: `signal_pair` (the contact pair whose signal drives it, e.g. "ZERO_THREE_LEFT", from
    `SensingSetup.ChannelSignalResult.Channel`, else the entry's own `Channel` on its own lead),
    `ganged_to`, `centre_hz`, `mode`, `status`, the two thresholds in device units, averaging, onsets,
    blanking, startup delay, transitions (ms) and the current limits (mA). Nothing is invented: a
    field the export does not carry is None."""
    out: Dict[str, Any] = {"available": False, "group": None, "session_end": None, "sides": {}}
    if not isinstance(export, dict):
        out["reason"] = "no device export"
        return out
    out["session_end"] = export.get("SessionEndDate") or export.get("SessionDate")
    groups = (export.get("Groups") or {}).get("Final") or []
    for g in groups:
        if not isinstance(g, dict) or not g.get("ActiveGroup"):
            continue
        sens = ((g.get("ProgramSettings") or {}).get("SensingChannel")) or []
        if not sens:
            continue
        out["group"] = _tail(g.get("GroupId"))
        for c in sens:
            if not isinstance(c, dict):
                continue
            side = _tail(c.get("HemisphereLocation"))
            if side not in ("Left", "Right"):
                continue
            setup = c.get("SensingSetup") or {}
            adaptive = c.get("AdaptiveTherapy") or {}
            sig = _tail((setup.get("ChannelSignalResult") or {}).get("Channel"))
            own = _PAIR_WORDS.get(_tail(c.get("Channel")) or "")
            pair = sig if sig else (f"{own}_{side.upper()}" if own else None)
            out["sides"][side] = {
                "signal_pair": pair,
                "ganged_to": _tail(c.get("GangedToHemisphere")),
                "centre_hz": _f(setup.get("FrequencyInHertz")),
                "mode": _tail(c.get("Mode")),
                "status": _tail(c.get("AdaptiveTherapyStatus")),
                "upper": _f(c.get("UpperLfpThreshold")),
                "lower": _f(c.get("LowerLfpThreshold")),
                "averaging_ms": _f(setup.get("AveragingDurationInMilliSeconds")),
                "onset_upper_ms": _f(adaptive.get("UpperThresholdOnsetInMilliSeconds")),
                "onset_lower_ms": _f(adaptive.get("LowerThresholdOnsetInMilliSeconds")),
                "blanking_ms": _f(adaptive.get("DetectionBlankingDurationInMilliSeconds")),
                "startup_delay_ms": _f(adaptive.get("AdaptiveStartupDelayInMilliSeconds")),
                "transition_up_ms": _f(c.get("TransitionUpInMilliSeconds")),
                "transition_down_ms": _f(c.get("TransitionDownInMilliSeconds")),
                "lower_limit_mA": _f(c.get("LowerLimitInMilliAmps")),
                "upper_limit_mA": _f(c.get("UpperLimitInMilliAmps")),
            }
        out["available"] = bool(out["sides"])
        break
    if not out["available"]:
        out["reason"] = "the newest export has no active group with sensing"
    return out


# ---------------------------------------------------------------------------------------------
# Home readings at a band, by the device's own sensing frequency
# ---------------------------------------------------------------------------------------------
def frequency_schedules(chronic_recordings) -> Dict[str, List[Tuple[float, float]]]:
    """Each lead's sensing-frequency schedule, unrounded: the union of the chronic recordings'
    `FreqScheduleHz` change points ([[t, hz], ...]) by the lead named in their channel names. One
    schedule per device is written onto every chronic recording (decision 487), so the union is that
    schedule."""
    out: Dict[str, set] = {"Left": set(), "Right": set()}
    for r in chronic_recordings or []:
        if not isinstance(r, dict):
            continue
        names = [str(n) for n in (r.get("ChannelNames") or [])]
        side = ("Left" if any(n.startswith("LeftHemisphere") for n in names) else
                "Right" if any(n.startswith("RightHemisphere") for n in names) else None)
        if side is None:
            continue
        for item in r.get("FreqScheduleHz") or []:
            try:
                t, hz = float(item[0]), float(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            if np.isfinite(t) and np.isfinite(hz):
                out[side].add((t, round(hz, 4)))
    return {s: sorted(v) for s, v in out.items()}


def frequency_at(times, schedule: Sequence[Tuple[float, float]]) -> np.ndarray:
    """The schedule's frequency at each time: the last change at or before it, else NaN."""
    t = np.asarray(times, dtype=float)
    out = np.full(t.shape, np.nan)
    if not schedule or t.size == 0:
        return out
    st = np.asarray([a for a, _ in schedule], dtype=float)
    hz = np.asarray([b for _, b in schedule], dtype=float)
    k = np.searchsorted(st, t, side="right") - 1
    ok = k >= 0
    out[ok] = hz[k[ok]]
    return out


def side_of_pair(pair) -> Optional[str]:
    u = str(pair or "").upper()
    return "Left" if u.endswith("LEFT") else ("Right" if u.endswith("RIGHT") else None)


def home_at_band(samples_by_pair, schedules, pair, centre_hz):
    """``(t, y, freq_hz)``: the home readings on ``pair`` whose sensing frequency at their time is the
    one nearest ``centre_hz`` (under 0.5 Hz away; on a tie, the one with more readings), in time
    order. Empty arrays when there is none."""
    empty = (np.zeros(0), np.zeros(0), None)
    d = (samples_by_pair or {}).get(str(pair)) if pair is not None else None
    if d is None or centre_hz is None:
        return empty
    t = np.asarray(d.get("t", []), dtype=float)
    y = np.asarray(d.get("y", []), dtype=float)
    side = side_of_pair(pair)
    hz = frequency_at(t, (schedules or {}).get(side) or [])
    best = None
    for f in sorted({float(v) for v in hz[np.isfinite(hz)]}):
        gap = abs(f - float(centre_hz))
        if gap >= MAX_CENTRE_GAP_HZ:
            continue
        n = int(np.sum(hz == f))
        cand = (gap, -n, f)
        if best is None or cand < best:
            best = cand
    if best is None:
        return empty
    m = hz == best[2]
    o = np.argsort(t[m], kind="stable")
    return t[m][o], y[m][o], float(best[2])


# ---------------------------------------------------------------------------------------------
# The pieces of one row
# ---------------------------------------------------------------------------------------------
def local_hours(times_s) -> np.ndarray:
    import pandas as pd
    t = np.asarray(times_s, dtype=float)
    if t.size == 0:
        return np.zeros(0, dtype=int)
    return np.asarray(pd.to_datetime(t, unit="s", utc=True).tz_convert(TZ).hour, dtype=int)


def local_days(times_s) -> np.ndarray:
    import pandas as pd
    t = np.asarray(times_s, dtype=float)
    if t.size == 0:
        return np.zeros(0, dtype=object)
    return np.asarray(pd.to_datetime(t, unit="s", utc=True).tz_convert(TZ).strftime("%Y-%m-%d"),
                      dtype=object)


def is_day(times_s) -> np.ndarray:
    h = local_hours(times_s)
    return (h >= DAY_HOURS[0]) & (h < DAY_HOURS[1])


def state_shares(y, upper, lower) -> Dict[str, Any]:
    """Shares of readings above the upper threshold, below the lower one, and between (the rest),
    so the three add to 1 exactly; None each with no readings."""
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    if y.size == 0 or upper is None or lower is None:
        return {"n": int(y.size), "above": None, "between": None, "below": None,
                "n_above": 0, "n_between": 0, "n_below": 0}
    above = int(np.sum(y > float(upper)))
    below = int(np.sum(y < float(lower)))
    between = int(y.size) - above - below
    n = float(y.size)
    return {"n": int(y.size), "above": above / n, "between": between / n, "below": below / n,
            "n_above": above, "n_between": between, "n_below": below}


def period_shares(t, y, upper, lower) -> Dict[str, Any]:
    d = is_day(t)
    y = np.asarray(y, dtype=float)
    return {"all": state_shares(y, upper, lower), "day": state_shares(y[d], upper, lower),
            "night": state_shares(y[~d], upper, lower)}


def hourly_shares(t, y, upper, lower) -> List[Dict[str, Any]]:
    h = local_hours(t)
    y = np.asarray(y, dtype=float)
    return [dict(state_shares(y[h == k], upper, lower), hour=k) for k in range(24)]


def hysteresis_states(y, upper, lower) -> np.ndarray:
    """+1 after a reading above the upper threshold until one below the lower; -1 the other way; 0
    before the first reading outside the pair."""
    st = np.zeros(len(y), dtype=int)
    s = 0
    for i, v in enumerate(np.asarray(y, dtype=float)):
        if v > upper:
            s = 1
        elif v < lower:
            s = -1
        st[i] = s
    return st


def duty(t, y, upper, lower) -> Dict[str, Any]:
    if upper is None or lower is None or len(y) == 0:
        return {"high": None, "high_day": None, "high_night": None, "what": DUTY_WHAT}
    st = hysteresis_states(y, float(upper), float(lower))
    d = is_day(t)
    return {"high": float(np.mean(st == 1)),
            "high_day": float(np.mean(st[d] == 1)) if d.any() else None,
            "high_night": float(np.mean(st[~d] == 1)) if (~d).any() else None,
            "what": DUTY_WHAT}


def percentile_pair(t, y, percentiles=GUIDANCE_PERCENTILES) -> Dict[str, Any]:
    """The manufacturer guidance: lower and upper thresholds at the 25th and 75th percentiles of
    DAYTIME home power (numpy's default linear interpolation). None without daytime readings."""
    y = np.asarray(y, dtype=float)
    d = is_day(t) & np.isfinite(y)
    if not d.any():
        return {"upper": None, "lower": None, "n_day_readings": 0}
    lo, up = np.percentile(y[d], [float(percentiles[0]), float(percentiles[1])])
    return {"upper": float(up), "lower": float(lo), "n_day_readings": int(d.sum())}


def covering_index(report_t, sample_t, period_s=600.0) -> np.ndarray:
    """For each report, the index of the one reading whose 10 minutes cover it (C5), else -1."""
    rt = np.asarray(report_t, dtype=float)
    st = np.asarray(sample_t, dtype=float)
    out = np.full(rt.size, -1, dtype=int)
    if rt.size == 0 or st.size == 0:
        return out
    order = np.argsort(st, kind="stable")
    ss = st[order]
    k = np.searchsorted(ss, rt, side="right") - 1
    ok = (k >= 0)
    ok[ok] &= rt[ok] < ss[k[ok]] + float(period_s)
    out[ok] = order[k[ok]]
    return out


def _median_interval(v) -> Dict[str, Any]:
    """Median and its distribution-free 95% interval from the order statistics (none under 6)."""
    v = np.sort(np.asarray(v, dtype=float))
    n = int(v.size)
    if n == 0:
        return {"n": 0, "median": None, "low": None, "high": None}
    if n < 6:
        return {"n": n, "median": float(np.median(v)), "low": None, "high": None}
    from scipy.stats import binom
    j = max(int(binom.ppf(0.025, n, 0.5)) - 1, 0)
    k = min(n - 1 - j, n - 1)
    return {"n": n, "median": float(np.median(v)), "low": float(v[j]), "high": float(v[k])}


def _diff_above_rest(s, y):
    a, r = y[s == 1], y[s != 1]
    if a.size < MIN_PER_STATE or r.size < MIN_PER_STATE:
        return None
    return float(np.median(a) - np.median(r))


def rotation_p(states, y, stat=_diff_above_rest):
    """``(value, p, n_shifts)``: the statistic, and its two-sided exact rotation p (the pain series
    slid along the state series by every other shift once, in time order)."""
    s = np.asarray(states)
    y = np.asarray(y, dtype=float)
    v0 = stat(s, y)
    if v0 is None or y.size < 3:
        return v0, None, 0
    vals = [stat(s, np.roll(y, k)) for k in range(1, y.size)]
    vals = np.asarray([v for v in vals if v is not None], dtype=float)
    if vals.size == 0:
        return v0, None, 0
    return v0, float((np.sum(np.abs(vals) >= abs(v0) - 1e-12) + 1) / (vals.size + 1)), int(vals.size)


def day_resampled_interval(states, y, t, stat=_diff_above_rest, n_boot=N_BOOT, seed=SEED):
    """Percentile 95% interval with whole California days resampled (reports of one day move
    together); None when fewer than 2 days or under 100 usable draws."""
    s = np.asarray(states)
    y = np.asarray(y, dtype=float)
    days = local_days(t)
    ud = sorted(set(days.tolist()))
    if len(ud) < 2:
        return None, None
    idx = [np.flatnonzero(days == d) for d in ud]
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(int(n_boot)):
        ii = np.concatenate([idx[j] for j in rng.integers(0, len(ud), len(ud))])
        v = stat(s[ii], y[ii])
        if v is not None:
            vals.append(v)
    if len(vals) < 100:
        return None, None
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def pain_by_state(report_t, report_y, t, y, upper, lower) -> Dict[str, Any]:
    """The pain score by the state of the covering 10-minute reading: n, median and interval per
    state, and the difference (median above minus median of the rest) with its rotation p and its
    day-resampled interval."""
    rt = np.asarray(report_t, dtype=float)
    ry = np.asarray(report_y, dtype=float)
    ok = np.isfinite(rt) & np.isfinite(ry)
    rt, ry = rt[ok], ry[ok]
    o = np.argsort(rt, kind="stable")
    rt, ry = rt[o], ry[o]
    ix = covering_index(rt, t)
    m = ix >= 0
    out: Dict[str, Any] = {"n_reports": int(m.sum()), "n_reports_day": None, "by_state": {},
                           "difference": None, "first_report_s": None, "last_report_s": None}
    if not m.any() or upper is None or lower is None:
        return out
    yy = np.asarray(y, dtype=float)[ix[m]]
    vas, tt = ry[m], rt[m]
    out["n_reports_day"] = int(is_day(tt).sum())
    out["first_report_s"], out["last_report_s"] = float(tt.min()), float(tt.max())
    s = np.where(yy > float(upper), 1, np.where(yy < float(lower), -1, 0))
    for name, v in (("above", 1), ("between", 0), ("below", -1)):
        out["by_state"][name] = _median_interval(vas[s == v])
    d0, p, nk = rotation_p(s, vas)
    lo, hi = day_resampled_interval(s, vas, tt) if d0 is not None else (None, None)
    out["difference"] = {"what": "median pain when power was above the upper threshold minus the "
                                 "median of the rest",
                         "value": d0, "low": lo, "high": hi, "p_rotation": p, "n_rotations": nk,
                         "n_above": int(np.sum(s == 1)), "n_rest": int(np.sum(s != 1))}
    return out


def fit_upper_on_earlier(report_t, report_y, t, y, *, share=FIT_SHARE):
    """Candidate (c): the upper threshold, from the grid of percentiles of the EARLIER daytime home
    power, that gives the largest median pain above minus the rest on the EARLIER reports only
    (at least `MIN_FIT_PER_SIDE` on each side); the lower at the earlier daytime 25th percentile.
    Earlier = reports with a covering reading, up to the report at the ``share`` mark by time; the
    home readings up to that report's time. Nothing after the cut enters the fit. Then the same
    difference on the later reports, with its rotation p."""
    rt = np.asarray(report_t, dtype=float)
    ry = np.asarray(report_y, dtype=float)
    ok = np.isfinite(rt) & np.isfinite(ry)
    rt, ry = rt[ok], ry[ok]
    o = np.argsort(rt, kind="stable")
    rt, ry = rt[o], ry[o]
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ix = covering_index(rt, t)
    m = ix >= 0
    rt, ry, hx = rt[m], ry[m], y[ix[m]]
    out: Dict[str, Any] = {"available": False, "n_reports": int(rt.size), "cut_s": None,
                           "n_fit": 0, "n_held_out": 0, "upper": None, "lower": None,
                           "percentile": None, "fit_difference": None, "held_out": None,
                           "grid": []}
    k = int(np.floor(float(share) * rt.size))
    if k < 1 or k >= rt.size:
        out["reason"] = f"{rt.size} matched reports: too few to split by time"
        return out
    cut = float(rt[k - 1])
    out["cut_s"] = cut
    early = rt <= cut
    out["n_fit"], out["n_held_out"] = int(early.sum()), int((~early).sum())
    fit_y = y[(t <= cut) & is_day(t)]
    if fit_y.size == 0:
        out["reason"] = "no daytime home readings before the cut"
        return out
    best = None
    for q in FIT_PERCENTILES:
        u = float(np.percentile(fit_y, q))
        a = ry[early & (hx > u)]
        r = ry[early & ~(hx > u)]
        dlt = (float(np.median(a) - np.median(r))
               if a.size >= MIN_FIT_PER_SIDE and r.size >= MIN_FIT_PER_SIDE else None)
        out["grid"].append({"percentile": q, "upper": u, "n_above": int(a.size), "n_rest": int(r.size),
                            "difference": dlt})
        if dlt is not None and (best is None or dlt > best[2]):
            best = (q, u, dlt)
    if best is None:
        out["reason"] = (f"fewer than {MIN_FIT_PER_SIDE} earlier reports on one side at every grid "
                         "threshold")
        return out
    out.update({"available": True, "percentile": best[0], "upper": best[1],
                "lower": float(np.percentile(fit_y, GUIDANCE_PERCENTILES[0])), "fit_difference": best[2]})
    late = ~early
    s = np.where(hx[late] > best[1], 1, 0)
    v, p, nk = rotation_p(s, ry[late])
    out["held_out"] = {"value": v, "p_rotation": p, "n_rotations": nk,
                       "n_above": int(np.sum(s == 1)), "n_rest": int(np.sum(s != 1))}
    return out


def design_rate(design_table, upper, lower, *, averaging_ms, onset_ms) -> Dict[str, Any]:
    """Noise-only crossings an hour from the stored design rule (decision 152) for this pair's
    half-gap, at the table row nearest the device's averaging and onset: the rate at the largest
    separation tried that is no wider than the half-gap (rates fall as the gap widens, so the true
    rate is at most this), and whether the half-gap reaches the row's minimum. None when no table."""
    if not design_table or upper is None or lower is None or averaging_ms is None or onset_ms is None:
        return {"applies": False, "reason": "no stored design rule for this band"}
    from . import design_rule as _dr
    row = _dr.lookup_min_separation(list(design_table), averaging_ms=float(averaging_ms),
                                    onset_ms=float(onset_ms))
    if row is None:
        return {"applies": False, "reason": "the design-rule table is empty"}
    half = 0.5 * (float(upper) - float(lower))
    sweep = sorted(row.get("sweep") or [], key=lambda r: r["separation"])
    under = [r for r in sweep if float(r["separation"]) <= half]
    rate = float(under[-1]["total_per_hour"]) if under else None
    need = row.get("min_separation")
    return {"applies": True, "half_gap": half, "averaging_s": float(row["averaging_s"]),
            "onset_s": float(row["onset_s"]), "timing_exact": bool(row.get("exact_match")),
            "crossings_per_hour_at_most": rate,
            "at_separation": float(under[-1]["separation"]) if under else None,
            "min_separation": need,
            "meets_rule": (None if need is None and not sweep else (need is not None and half >= float(need)))}


def flags(upper, lower, t_range) -> List[str]:
    out = []
    if lower is not None and lower < 0:
        out.append("lower threshold below zero")
    if upper is not None and upper < 0:
        out.append("upper threshold below zero")
    if t_range is not None and upper is not None and lower is not None:
        lo_r, hi_r = t_range
        if upper > hi_r or lower < lo_r:
            out.append(f"outside the home range ({lo_r:.0f}-{hi_r:.0f})")
    return out


def evaluate_row(key, upper, lower, *, t, y, report_t, report_y, design_table=None,
                 timing=None, extra=None) -> Dict[str, Any]:
    """One row: the thresholds, the shares, the time held high, the design rule's crossings and the
    pain score by state, on the home readings ``t``/``y`` of one band."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    rng = (float(np.min(y)), float(np.max(y))) if y.size else None
    row: Dict[str, Any] = {"key": key, "label": ROW_LABELS.get(key, key), "upper": upper,
                           "lower": lower, "n_readings": int(y.size),
                           "n_days": int(len(set(local_days(t).tolist()))) if t.size else 0,
                           "home_range": rng, "flags": flags(upper, lower, rng)}
    row["shares"] = period_shares(t, y, upper, lower)
    row["time_high"] = duty(t, y, upper, lower)
    tm = timing or {}
    row["design_rule"] = design_rate(design_table, upper, lower, averaging_ms=tm.get("averaging_ms"),
                                     onset_ms=tm.get("onset_ms"))
    row["pain"] = pain_by_state(report_t, report_y, t, y, upper, lower)
    if extra:
        row.update(extra)
    return row


def limits_text(n_reports, n_day, span_days, pain_label) -> str:
    lead = (f"{n_reports} {pain_label} reports have a home reading at this band"
            + (f", {n_day} of them filed 07:00-20:00" if n_day is not None else "")
            + (f", over {span_days} days" if span_days else "") + ". ")
    few = ("Too few for any difference to mean anything. " if n_reports < 20 else "")
    return lead + few + LIMITS_FIXED


def comparison_block(*, programmed: Dict[str, Any], band: Dict[str, Any], report_pair: Dict[str, Any],
                     samples_by_pair, schedules, lead_currents=None, report_t, report_y,
                     pain_label: str, design_table=None) -> Dict[str, Any]:
    """The `threshold_comparison` block. ``band``: {"pair", "centre_hz", "side"} of the report;
    ``report_pair``: {"upper", "lower", "rule"} the report placed; ``programmed``:
    `programmed_adaptive`'s answer; ``samples_by_pair``: C5's home readings; ``schedules``:
    `frequency_schedules`; ``lead_currents``: each lead's own current series (C5)."""
    out: Dict[str, Any] = {"available": True, "version": VERSION, "what": WHAT,
                           "pain_score": pain_label, "band": dict(band), "rows": [],
                           "programmed": None, "notes": [LABELLER_NOTE],
                           "changes_nothing": True}
    rt = np.asarray(report_t, dtype=float)
    ry = np.asarray(report_y, dtype=float)
    # --- programmed now, on its own band ---------------------------------------------------------
    prog_side = None
    if programmed and programmed.get("available"):
        side = band.get("side")
        sides = programmed.get("sides") or {}
        prog_side = sides.get(side) or next(iter(sides.values()), None)
    timing = None
    if prog_side:
        pp, pc = prog_side.get("signal_pair"), prog_side.get("centre_hz")
        tp, yp, fp = home_at_band(samples_by_pair, schedules, pp, pc)
        same_band = (str(pp) == str(band.get("pair")) and pc is not None and band.get("centre_hz") is not None
                     and abs(float(pc) - float(band["centre_hz"])) < MAX_CENTRE_GAP_HZ)
        timing = {"averaging_ms": prog_side.get("averaging_ms"), "onset_ms": prog_side.get("onset_upper_ms")}
        prow = evaluate_row(ROW_PROGRAMMED, prog_side.get("upper"), prog_side.get("lower"), t=tp, y=yp,
                            report_t=rt, report_y=ry,
                            design_table=design_table if same_band else None, timing=timing,
                            extra={"pair": pp, "centre_hz": pc, "home_freq_hz": fp, "same_band_as_report": same_band})
        # what the device's own current did on this lead over the same readings
        lead = band.get("side") if band.get("side") in ("Left", "Right") else "Left"
        cur = (lead_currents or {}).get(lead)
        # only while THIS lead's own schedule had it sensing at the programmed frequency (the lead is
        # driven by that signal then; before, it may have run on its own signal)
        in_force = np.zeros(len(tp), dtype=bool)
        if pc is not None and len(tp):
            in_force = np.abs(frequency_at(tp, (schedules or {}).get(lead) or []) - float(pc)) < 0.01
        if cur is not None and in_force.any():
            try:
                from Biomarkers.routines import chronic_band_choice as _cbc  # noqa: PLC0415
            except ImportError:                           # pragma: no cover - the other spelling
                from modules.Biomarkers.routines import chronic_band_choice as _cbc  # noqa: PLC0415
            tf, yf = tp[in_force], yp[in_force]
            c, _n2 = _cbc.current_at_times(tf, cur)
            okc = np.isfinite(c)
            if okc.any():
                cc = c[okc]
                st = np.where(yf[okc] > prog_side["upper"], 1, np.where(yf[okc] < prog_side["lower"], -1, 0))
                prow["device_current"] = {
                    "lead": lead, "n": int(okc.sum()), "since_s": float(tf[okc].min()),
                    "median_mA": float(np.median(cc)),
                    "p10_mA": float(np.percentile(cc, 10)), "p90_mA": float(np.percentile(cc, 90)),
                    "median_mA_when": {k: (float(np.median(cc[st == v])) if (st == v).any() else None)
                                       for k, v in (("above", 1), ("between", 0), ("below", -1))},
                    "lower_limit_mA": prog_side.get("lower_limit_mA"),
                    "upper_limit_mA": prog_side.get("upper_limit_mA")}
        prow["hourly_shares"] = hourly_shares(tp, yp, prog_side.get("upper"), prog_side.get("lower"))
        out["rows"].append(prow)
        out["programmed"] = {"group": programmed.get("group"), "session_end": programmed.get("session_end"),
                             "side": dict(prog_side), "same_band_as_report": same_band}
        if not same_band:
            out["notes"].append(
                f"The device runs {_pair_words(pp)} {pc:g} Hz; this report's band is "
                f"{_pair_words(band.get('pair'))} {float(band.get('centre_hz')):g} Hz, so the candidates "
                "below are read at the report's band and the programmed row at its own.")
    else:
        out["programmed"] = {"available": False, "reason": (programmed or {}).get("reason")}
    # --- candidates, on the report's band --------------------------------------------------------
    tb, yb, fb = home_at_band(samples_by_pair, schedules, band.get("pair"), band.get("centre_hz"))
    out["band"]["home_freq_hz"] = fb
    out["band"]["n_home_readings"] = int(tb.size)
    if tb.size == 0:
        out["notes"].append("No home record at this band: the candidates cannot be read at home.")
    ext = {"pair": band.get("pair"), "centre_hz": band.get("centre_hz"), "home_freq_hz": fb}
    if report_pair and report_pair.get("upper") is not None:
        out["rows"].append(evaluate_row(ROW_CLINIC, report_pair["upper"], report_pair["lower"], t=tb, y=yb,
                                        report_t=rt, report_y=ry, design_table=design_table, timing=timing,
                                        extra=dict(ext, rule=report_pair.get("rule"))))
    if tb.size:
        g = percentile_pair(tb, yb)
        out["rows"].append(evaluate_row(ROW_GUIDANCE, g["upper"], g["lower"], t=tb, y=yb, report_t=rt,
                                        report_y=ry, design_table=design_table, timing=timing,
                                        extra=dict(ext, n_day_readings=g["n_day_readings"])))
        fit = fit_upper_on_earlier(rt, ry, tb, yb)
        if fit.get("available"):
            out["rows"].append(evaluate_row(ROW_FITTED, fit["upper"], fit["lower"], t=tb, y=yb, report_t=rt,
                                            report_y=ry, design_table=design_table, timing=timing,
                                            extra=dict(ext, fit=fit)))
        else:
            out["notes"].append(f"(c) not fitted: {fit.get('reason')}.")
        out["fit"] = fit
    # --- limits -----------------------------------------------------------------------------------
    cand_pain = next((r["pain"] for r in out["rows"] if r["key"] != ROW_PROGRAMMED), None) or \
        (out["rows"][0]["pain"] if out["rows"] else {"n_reports": 0})
    n_rep = int(cand_pain.get("n_reports") or 0)
    span = None
    if cand_pain.get("first_report_s") is not None:
        span = int(round((cand_pain["last_report_s"] - cand_pain["first_report_s"]) / 86400.0)) + 1
    out["n_reports"] = n_rep
    out["limits"] = limits_text(n_rep, cand_pain.get("n_reports_day"), span, pain_label)
    out["too_few_reports"] = n_rep < 20
    return out


def _pair_words(pair) -> str:
    """"ZERO_THREE_LEFT" -> "L 0-3"."""
    u = str(pair or "").upper()
    nums = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3"}
    parts = u.split("_")
    side = "L" if u.endswith("LEFT") else ("R" if u.endswith("RIGHT") else "?")
    digits = [nums[p] for p in parts if p in nums]
    return f"{side} {'-'.join(digits)}" if digits else str(pair)
