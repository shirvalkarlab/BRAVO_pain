"""Does band power follow the clock or the weekend, and does pain? (decision 246's check, moved here
from `_agent_bridge/step9_time_of_day_diagnostic.py` on 2026-09-24 so the saved control analysis and
the one-off script read one copy).

Band power per recording and band, raw (decision 202), against a once-a-day cycle on the California
clock (the multiple correlation R of a cosine-and-sine fit, with the hour it peaks and the value 200
shuffles of the hours reach 95% of the time) and against the weekend (the correlation with
"Saturday or Sunday"); intervals from a block bootstrap over recordings in time order. Pain against
the weekend within each week, which cancels slow drift. Time enters no model anywhere (193-196): a
cycle found here is a fact to weigh, not an input.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

try:
    from modules.Biomarkers.routines import stats_utils as SU
except ImportError:                                            # host spelling
    from Biomarkers.routines import stats_utils as SU

CENTRES_HZ = [8.5 + i for i in range(22)]
BAND_WIDTH_HZ = 5.0
CA = ZoneInfo("America/Los_Angeles")
N_BOOT = 1000
N_SHUFFLE = 200


def band_power(X, f_set, centre, width=BAND_WIDTH_HZ):
    f = np.asarray(f_set, dtype=float)
    m = (f >= centre - width / 2) & (f <= centre + width / 2)
    if not m.any():
        return np.full(np.asarray(X).shape[0], np.nan)
    with np.errstate(invalid="ignore"):
        return np.nanmean(np.asarray(X, dtype=float)[:, m], axis=1)


def cycle_r(power, hour):
    """Multiple correlation of power with a once-a-day cycle, and the hour the cycle peaks at."""
    a = 2 * np.pi * np.asarray(hour, float) / 24.0
    A = np.column_stack([np.ones_like(a), np.cos(a), np.sin(a)])
    beta, *_ = np.linalg.lstsq(A, power, rcond=None)
    fit = A @ beta
    ss_tot = float(np.sum((power - power.mean()) ** 2))
    if ss_tot <= 0:
        return np.nan, np.nan
    r2 = max(0.0, 1.0 - float(np.sum((power - fit) ** 2)) / ss_tot)
    peak = (np.degrees(np.arctan2(beta[2], beta[1])) % 360.0) / 15.0
    return float(np.sqrt(r2)), float(peak)


def weekend_r(power, weekend):
    w = np.asarray(weekend, float)
    if np.std(w) == 0 or np.std(power) == 0:
        return np.nan
    return float(np.corrcoef(power, w)[0, 1])


def one_band(power, hour, weekend, rng, *, n_boot=N_BOOT, n_shuffle=N_SHUFFLE):
    ok = np.isfinite(power) & np.isfinite(hour)
    p, h, w = power[ok], hour[ok], weekend[ok]
    n = int(p.size)
    if n < 20:
        return {"n": n, "why": "fewer than 20 recordings carry this band"}
    block = int(SU.block_length_for(p, n))
    picks = SU.block_bootstrap_picks(n, block, n_boot, rng)
    R, peak = cycle_r(p, h)
    r_w = weekend_r(p, w)
    Rb = np.array([cycle_r(p[i], h[i])[0] for i in picks])
    wb = np.array([weekend_r(p[i], w[i]) for i in picks])
    Rnull = np.array([cycle_r(p, rng.permutation(h))[0] for _ in range(n_shuffle)])
    q = lambda v: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5)))
    return {"n": n, "block": block, "R_daily": R, "R_daily_ci": q(Rb), "R_daily_peak_hour": peak,
            "R_daily_shuffle_p95": float(np.nanpercentile(Rnull, 95)),
            "r_weekend": r_w, "r_weekend_ci": q(wb), "why": None}


def _clock(t):
    local = [datetime.fromtimestamp(float(v), tz=timezone.utc).astimezone(CA) for v in t]
    return (np.array([d.hour + d.minute / 60.0 for d in local]),
            np.array([1.0 if d.weekday() >= 5 else 0.0 for d in local]), local)


def rows_for(X, t, channel, f_set, *, rng, n_boot=N_BOOT, n_shuffle=N_SHUFFLE):
    t = np.asarray(t, float)
    hour, weekend, _ = _clock(t)
    order = np.argsort(t)
    rows = []
    for ch in sorted(set(np.asarray(channel, str))):
        idx = order[np.asarray(channel, str)[order] == ch]
        for c in CENTRES_HZ:
            bp = band_power(np.asarray(X)[idx], f_set, c)
            rows.append({"channel": ch, "centre_hz": c,
                         **one_band(bp, hour[idx], weekend[idx], rng, n_boot=n_boot, n_shuffle=n_shuffle)})
    return rows


def weekend_pain(t, v, *, rng, n_boot=5000):
    """Weekend minus weekday pain within each Monday-to-Sunday week holding both, averaged over
    weeks: the mean, a 95% interval resampling weeks, and a sign-flip p; with the reports counted."""
    t, v = np.asarray(t, float), np.asarray(v, float)
    _h, wk, local = _clock(t)
    wk = wk.astype(bool)
    iso = np.array(["%d-%02d" % d.isocalendar()[:2] for d in local])
    diffs = np.array([v[(iso == w) & wk].mean() - v[(iso == w) & ~wk].mean()
                      for w in np.unique(iso) if ((iso == w) & wk).any() and ((iso == w) & ~wk).any()])
    out = {"n_weekend": int(wk.sum()), "n_weekday": int((~wk).sum()), "n_weeks": int(diffs.size)}
    if diffs.size < 4:
        return {**out, "why": "fewer than 4 weeks hold both weekend and weekday reports"}
    within = float(diffs.mean())
    wb = [rng.choice(diffs, size=diffs.size).mean() for _ in range(n_boot)]
    flips = np.abs((rng.choice([-1.0, 1.0], size=(n_boot, diffs.size)) * diffs).mean(axis=1))
    return {**out, "within_week": within, "ci": [float(x) for x in np.percentile(wb, [2.5, 97.5])],
            "p": float((np.sum(flips >= abs(within)) + 1) / (n_boot + 1)), "why": None}
