"""Does band power follow the clock? A one-off diagnostic, run once and published in the decision log
(panel A item 9, 2026-09-22; step 9 of the research panels' build order).

WHAT IT MEASURES. For every sensing contact and every one of the heat maps' 22 band centres (8.5 to
29.5 Hz, 5 Hz wide), the band power of each stored recording, in RAW power (decision 202: no log
anywhere), against two things about WHEN the recording was made:

  * time of day, on the California clock (decision 2): how much of the band power's scatter a
    smooth once-a-day cycle explains (a least-squares fit on the cosine and sine of the hour), given
    as the multiple correlation R (0 = no daily cycle, 1 = power is the cycle) with the hour the
    cycle peaks at;
  * day of week: the correlation between band power and "the recording was made on a Saturday or
    Sunday" (positive = more power at weekends).

Each with a 95% interval from a BLOCK bootstrap over the recordings in time order (the block length
from the series' own lag-1 decorrelation, `stats_utils.block_length_for`), so a run of recordings
from one afternoon counts as the near-one observation it is. R is never below zero, so its interval
is read against the value a series with no cycle reaches by chance, which is printed beside it (the
95th percentile of R over 200 shuffles of the hours, keeping the power series as it is).

WHAT IT IS NOT. Nothing ships and nothing reads it: it writes no store entry, enters no key, no
model, no verdict. Decisions 193-196 hold -- time is modelled nowhere -- and a daily cycle found here
would be a fact to weigh, not an input to add. It reads the stored assembled matrix as the
Biomarkers module's own consumer and changes nothing.

HOW TO RUN IT (the container, through the bridge):
    python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 600 --wait 600 \\
        "python3 _agent_bridge/step9_time_of_day_diagnostic.py"
It prints the table and writes `_agent_bridge/_step9_time_of_day.csv` (scratch, gitignored).
`--selftest` runs it on constructed data with a planted daily cycle and no weekday effect, which is
how it was checked before it ever touched the record.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # /usr/src/BRAVO or <repo>/BRAVO
for p in (ROOT, os.path.join(ROOT, "modules")):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from modules.Biomarkers.routines import stats_utils as SU
except ImportError:                                            # host spelling
    from Biomarkers.routines import stats_utils as SU

UID = "2e3c75c00d7f4f37b53a048d195f11da"                       # RCS08, de-identified
CENTRES_HZ = [8.5 + i for i in range(22)]                      # the heat maps' 22 centres
BAND_WIDTH_HZ = 5.0
CA = ZoneInfo("America/Los_Angeles")
N_BOOT = 1000
N_SHUFFLE = 200


def band_power(X, f_set, centre, width=BAND_WIDTH_HZ):
    f = np.asarray(f_set, dtype=float)
    m = (f >= centre - width / 2) & (f <= centre + width / 2)
    if not m.any():
        return np.full(X.shape[0], np.nan)
    with np.errstate(invalid="ignore"):
        return np.nanmean(np.asarray(X, dtype=float)[:, m], axis=1)


def _cycle_r(power, hour):
    """Multiple correlation of power with a once-a-day cycle (cos and sin of the hour), and the hour
    the fitted cycle peaks at."""
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


def _pb_r(power, weekend):
    w = np.asarray(weekend, float)
    if np.std(w) == 0 or np.std(power) == 0:
        return np.nan
    return float(np.corrcoef(power, w)[0, 1])


def one_band(power, hour, weekend, rng):
    """R for the daily cycle and r for weekend, each with a block-bootstrap interval, over the
    recordings in time order; and the shuffle reference for R."""
    ok = np.isfinite(power) & np.isfinite(hour)
    p, h, w = power[ok], hour[ok], weekend[ok]
    n = int(p.size)
    if n < 20:
        return {"n": n, "why": "fewer than 20 recordings carry this band"}
    block = int(SU.block_length_for(p, n))
    picks = SU.block_bootstrap_picks(n, block, N_BOOT, rng)
    R, peak = _cycle_r(p, h)
    r_w = _pb_r(p, w)
    Rb = np.array([_cycle_r(p[i], h[i])[0] for i in picks])
    wb = np.array([_pb_r(p[i], w[i]) for i in picks])
    Rnull = np.array([_cycle_r(p, rng.permutation(h))[0] for _ in range(N_SHUFFLE)])
    q = lambda v: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5)))
    return {"n": n, "block": block, "R_daily": R, "R_daily_ci": q(Rb), "R_daily_peak_hour": peak,
            "R_daily_shuffle_p95": float(np.nanpercentile(Rnull, 95)),
            "r_weekend": r_w, "r_weekend_ci": q(wb), "why": None}


def run(X, t, channel, f_set, *, rng):
    t = np.asarray(t, float)
    local = [datetime.fromtimestamp(v, tz=timezone.utc).astimezone(CA) for v in t]
    hour = np.array([d.hour + d.minute / 60.0 for d in local])
    weekend = np.array([1.0 if d.weekday() >= 5 else 0.0 for d in local])
    order = np.argsort(t)
    rows = []
    for ch in sorted(set(np.asarray(channel, str))):
        m = np.asarray(channel, str)[order] == ch
        idx = order[m]
        for c in CENTRES_HZ:
            bp = band_power(np.asarray(X)[idx], f_set, c)
            res = one_band(bp, hour[idx], weekend[idx], rng)
            rows.append({"channel": ch, "centre_hz": c, **res})
    return rows


def print_table(rows):
    print(f"{'contact':<18}{'Hz':>6}{'n':>6}  {'daily R (95% interval)':<26}{'shuffle 95th':>13}"
          f"{'peak h':>8}  {'weekend r (95% interval)':<28}")
    for r in rows:
        if r.get("why"):
            print(f"{r['channel']:<18}{r['centre_hz']:>6.1f}{r['n']:>6}  {r['why']}")
            continue
        lo, hi = r["R_daily_ci"]
        wl, wh = r["r_weekend_ci"]
        flag = " *" if lo > r["R_daily_shuffle_p95"] else ""
        print(f"{r['channel']:<18}{r['centre_hz']:>6.1f}{r['n']:>6}  "
              f"{r['R_daily']:.3f} ({lo:.3f} to {hi:.3f}){flag:<3}{r['R_daily_shuffle_p95']:>10.3f}"
              f"{r['R_daily_peak_hour']:>8.1f}  {r['r_weekend']:+.3f} ({wl:+.3f} to {wh:+.3f})")
    print("* the daily R's whole interval lies above what shuffled hours reach 95% of the time")


def selftest():
    """A planted daily cycle on one band and none on another; no weekend effect anywhere."""
    rng = np.random.default_rng(0)
    n = 600
    t0 = datetime(2026, 1, 5, tzinfo=CA).timestamp()
    t = np.sort(t0 + rng.uniform(0, 60 * 86400, n))
    local = [datetime.fromtimestamp(v, tz=timezone.utc).astimezone(CA) for v in t]
    hour = np.array([d.hour + d.minute / 60.0 for d in local])
    f_set = np.arange(5.0, 35.0, 1.0)
    X = rng.normal(100, 10, (n, f_set.size))
    cyc = 30 * np.cos(2 * np.pi * (hour - 15.0) / 24.0)              # peaks at 15:00
    X[:, (f_set >= 18) & (f_set <= 22)] += cyc[:, None]
    rows = run(X, t, ["ONE_THREE_LEFT"] * n, f_set, rng=np.random.default_rng(1))
    b = {r["centre_hz"]: r for r in rows}
    assert b[20.5]["R_daily_ci"][0] > b[20.5]["R_daily_shuffle_p95"], b[20.5]
    assert abs(b[20.5]["R_daily_peak_hour"] - 15.0) < 1.0, b[20.5]
    assert b[10.5]["R_daily_ci"][0] <= b[10.5]["R_daily_shuffle_p95"], b[10.5]
    assert b[20.5]["r_weekend_ci"][0] < 0 < b[20.5]["r_weekend_ci"][1], b[20.5]
    print_table([b[10.5], b[20.5]])
    print("selftest passed: the planted 15:00 cycle is found at 20.5 Hz and nowhere it was not planted")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    try:
        from modules.CacheStore import store as ST
    except ImportError:
        from CacheStore import store as ST
    payload, stamp = ST.load_newest("biomarker_psd_matrix", UID, consumer="biomarkers")
    if payload is None:
        print("no stored biomarker_psd_matrix for RCS08; open the Biomarkers page once to build it")
        return
    print(f"matrix written {(stamp or {}).get('written_utc')}: {np.asarray(payload['X']).shape[0]} "
          f"recording-contact rows, {len(set(np.asarray(payload['channel'], str)))} contacts")
    rows = run(payload["X"], payload["t"], payload["channel"], payload["f_set"],
               rng=np.random.default_rng(20260923))
    print_table(rows)
    out = os.path.join(HERE, "_step9_time_of_day.csv")
    import csv
    keys = ["channel", "centre_hz", "n", "block", "R_daily", "R_daily_ci", "R_daily_shuffle_p95",
            "R_daily_peak_hour", "r_weekend", "r_weekend_ci", "why"]
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"written {out}")


if __name__ == "__main__":
    main()
