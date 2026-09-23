"""Does the chronic band power step when the left-side settings change? A one-off report
(panel B item 3, 2026-09-22; built 2026-09-23 in the order agreed with the PI).

WHAT IT MEASURES. The device keeps its own chronic log: one band-power reading every 10 minutes per
side, in its own units (LSB), at the band centre and on the sensing contacts it is scheduled to use,
with the current it delivered beside each reading. The left-side settings (the current, pulse
width, rate and stimulating contacts, read from the device's own dated settings, the raw store kind
`therapy_settings`) are cut into runs of one unchanged setting, and every pair of consecutive runs
each HELD 7 DAYS OR LONGER is one transition; it compares the left chronic log's level during the
first with its level during the second:

  * a clinic visit steps through settings that last minutes to hours (on RCS08 the setting before a
    held one was often in force for under an hour), so those brief runs belong to neither stretch
    and are left out -- the first version of this compared against them, and read almost nothing;
  * the level on each side is the median of the California-day medians (decision 142: the chronic
    log joins on the California calendar day), the stretch before being the last 30 days of the
    first held run and the stretch after the first 30 days of the second;
  * the shift is after minus before, in device units, with a 95% interval from a moving-block
    bootstrap over the days of each side (block length from the daily series' own lag-1
    decorrelation, `stats_utils.block_length_for`);
  * its size is also given against the band's own day-to-day scatter before the change, the 10th to
    90th percentile range of the daily medians.

A change counts only when both stretches have at least 7 California days of readings AT THE SAME
band centre and the same sensing contacts: the device moves its band and contacts on its own
schedule, and a step at a change that coincides with one of those is not a step at the change.

WHAT IT IS NOT. No drift term and no calendar-time covariate: decisions 193-196 hold (time is
modelled nowhere). A shift found here is a fact to weigh -- the band's level moved when the setting
moved -- not a cause established and not an input to anything: it writes no store entry, enters no
key, no model and no page. Raw power throughout (decision 202).

HOW TO RUN IT (the container, through the bridge):
    python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 600 --wait 600 \\
        "python3 _agent_bridge/stepB3_chronic_level_shift.py"
It prints the table and writes `_agent_bridge/_stepB3_chronic_level_shift.csv` (scratch).
`--selftest` runs it on constructed data first: a series with a planted step at one change and none
at another must return the one and not the other.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, "/usr/src/BRAVO")                   # the container's root, for the shared helpers
CA = ZoneInfo("America/Los_Angeles")
MIN_HOLD_DAYS = 7.0
MIN_DAYS_EACH_SIDE = 7
MAX_STRETCH_DAYS = 30.0
N_BOOT = 2000
SETTING_FIELDS = ("amp", "pw", "rate", "cathode")
CAVEAT = "no drift term, no calendar-time covariate (decisions 193-196)"


def _ca_day(t_s):
    return np.array([datetime.fromtimestamp(float(t), tz=timezone.utc).astimezone(CA).date().toordinal()
                     for t in np.atleast_1d(t_s)], dtype=int)


def daily_medians(t_s, y):
    """California day -> median reading, as two aligned arrays in day order."""
    t_s, y = np.asarray(t_s, float), np.asarray(y, float)
    ok = np.isfinite(t_s) & np.isfinite(y)
    days = _ca_day(t_s[ok])
    yy = y[ok]
    out_d, out_m = [], []
    for d in np.unique(days):
        out_d.append(int(d))
        out_m.append(float(np.median(yy[days == d])))
    return np.asarray(out_d, int), np.asarray(out_m, float)


def _block_length(x):
    try:
        from modules.Biomarkers.routines import stats_utils as SU
    except ImportError:                                          # pragma: no cover
        from Biomarkers.routines import stats_utils as SU
    return max(1, int(SU.block_length_for(np.asarray(x, float))))


def _block_resample_median(x, rng, block):
    n = len(x)
    if n == 0:
        return np.nan
    idx = []
    while len(idx) < n:
        start = int(rng.integers(0, n))
        idx.extend(((start + np.arange(block)) % n).tolist())
    return float(np.median(x[np.asarray(idx[:n])]))


def level_shift(pre_days_y, post_days_y, *, n_boot=N_BOOT, seed=0):
    """After-minus-before level of two daily-median series, with a block-bootstrap interval and the
    before side's 10th-90th percentile day-to-day scatter."""
    pre, post = np.asarray(pre_days_y, float), np.asarray(post_days_y, float)
    shift = float(np.median(post) - np.median(pre))
    rng = np.random.default_rng(seed)
    bpre, bpost = _block_length(pre), _block_length(post)
    boots = np.array([_block_resample_median(post, rng, bpost) - _block_resample_median(pre, rng, bpre)
                      for _ in range(int(n_boot))])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    scatter = float(np.percentile(pre, 90) - np.percentile(pre, 10))
    return dict(level_before=float(np.median(pre)), level_after=float(np.median(post)),
                shift=shift, ci_low=float(lo), ci_high=float(hi),
                scatter_10_90_before=scatter,
                shift_in_scatter=(shift / scatter if scatter > 0 else np.nan),
                n_days_before=int(len(pre)), n_days_after=int(len(post)),
                interval_excludes_zero=bool(lo > 0 or hi < 0))


def setting_runs(rows, *, hemi="Left"):
    """One side's settings cut into runs of one unchanged setting: ``start``, ``end`` (the next
    run's start; the last run has no end) and ``setting``. ``rows``: dicts with ``t`` (epoch s),
    ``hemi`` and the SETTING_FIELDS, any order."""
    side = sorted((r for r in rows if r.get("hemi") == hemi), key=lambda r: float(r["t"]))
    runs = []
    for r in side:
        key = tuple(r.get(f) for f in SETTING_FIELDS)
        if not runs or key != runs[-1]["key"]:
            runs.append(dict(start=float(r["t"]), key=key))
    for i, run in enumerate(runs):
        run["end"] = runs[i + 1]["start"] if i + 1 < len(runs) else np.inf
        run["setting"] = dict(zip(SETTING_FIELDS, run["key"]))
        run["days"] = (run["end"] - run["start"]) / 86400.0
    return runs


def held_transitions(rows, *, hemi="Left", min_hold_days=MIN_HOLD_DAYS):
    """Consecutive runs each held ``min_hold_days`` or longer, with whatever brief runs lay between
    them (a clinic visit's steps) counted and left out. Each transition: ``t`` (the second run's
    start), ``before``/``after`` (the two settings), the two runs' spans and ``n_brief_between``."""
    runs = setting_runs(rows, hemi=hemi)
    held = [r for r in runs if r["days"] >= float(min_hold_days)]
    out = []
    for a, b in zip(held, held[1:]):
        brief = [r for r in runs if r["start"] >= a["end"] and r["end"] <= b["start"]]
        out.append(dict(t=b["start"], before=a["setting"], after=b["setting"],
                        before_span=(a["start"], a["end"]), after_span=(b["start"], b["end"]),
                        held_days_before=a["days"], held_days=b["days"],
                        n_brief_between=len(brief),
                        hours_between=(b["start"] - a["end"]) / 3600.0))
    return out


def chronic_readings(chronic_list, *, hemi="Left"):
    """The side's chronic log as aligned arrays: time, band power, delivered current, and the band
    centre and sensing contacts in force at each reading (from the recording's own schedules)."""
    T, Y, A, C, K = [], [], [], [], []
    for r in chronic_list:
        names = [str(n) for n in (r.get("ChannelNames") or [])]
        if not names or not names[0].startswith(f"{hemi}Hemisphere"):
            continue
        t = np.asarray(r["Time"], float)
        d = np.asarray(r["Data"], float)
        if d.ndim != 2 or d.shape[0] != len(t):
            continue
        fs = sorted((float(a), float(b)) for a, b in (r.get("FreqScheduleHz") or []))
        cs = sorted((float(a), str(b)) for a, b in (r.get("ContactSchedule") or []))

        def _at(sched, tt, default):
            v = default
            for ts, val in sched:
                if ts <= tt:
                    v = val
            return v
        for i, tt in enumerate(t):
            T.append(tt); Y.append(d[i, 0]); A.append(d[i, 1] if d.shape[1] > 1 else np.nan)
            C.append(_at(fs, tt, float(r.get("CenterFrequencyHz") or np.nan)))
            K.append(_at(cs, tt, ""))
    o = np.argsort(T)
    return (np.asarray(T)[o], np.asarray(Y)[o], np.asarray(A)[o],
            np.asarray(C, float)[o], np.asarray(K, object)[o])


def shift_at_change(change, readings, *, max_stretch_days=MAX_STRETCH_DAYS,
                    min_days=MIN_DAYS_EACH_SIDE, n_boot=N_BOOT, seed=0):
    """One change: the level shift, or the reason it cannot be read."""
    t, y, _a, cen, con = readings
    a0, a1 = change["before_span"]
    b0, b1 = change["after_span"]
    before = (t >= max(a0, a1 - max_stretch_days * 86400.0)) & (t < a1)
    after = (t >= b0) & (t < min(b1, b0 + max_stretch_days * 86400.0))
    if not after.any() or not before.any():
        return dict(readable=False, reason="no chronic readings on one side of the change")
    # the band and contacts in force just after the change; both sides are held to them
    j = int(np.argmax(after))
    c0, k0 = cen[j], con[j]
    same = np.isclose(cen, c0) & (con == k0)
    db, yb = daily_medians(t[before & same], y[before & same])
    da, ya = daily_medians(t[after & same], y[after & same])
    out = dict(band_centre_hz=float(c0), contacts=str(k0))
    if len(yb) < min_days or len(ya) < min_days:
        dropped = int((before | after).sum() - ((before | after) & same).sum())
        out.update(readable=False,
                   reason=(f"{len(yb)} days before and {len(ya)} after at {c0:g} Hz on {k0} "
                           f"(fewer than {min_days}); {dropped} readings at another band or contacts"))
        return out
    out.update(readable=True, reason=None, **level_shift(yb, ya, n_boot=n_boot, seed=seed))
    return out


# ---------------------------------------------------------------------------------------------
def _selftest():
    """A constructed left log over 60 days, one reading every 10 minutes, with day-to-day wander;
    a +40 LSB step planted at the change on day 20 and no step at the change on day 40."""
    rng = np.random.default_rng(1)
    t0 = datetime(2026, 1, 1, 8, tzinfo=timezone.utc).timestamp()
    t = t0 + np.arange(60 * 144) * 600.0
    day = (t - t0) // 86400
    wander = np.repeat(rng.normal(0, 8, 60), 144)
    y = 300 + wander + rng.normal(0, 25, len(t)) + np.where(day >= 20, 40.0, 0.0)
    rec = dict(ChannelNames=["LeftHemisphere LFP", "LeftHemisphere Amplitude"], Time=t,
               Data=np.c_[y, np.full(len(t), 2.0)], CenterFrequencyHz=23.44,
               FreqScheduleHz=[[t0 - 1, 23.44]], ContactSchedule=[[t0 - 1, "0-2"]])
    # a one-hour visit step just before the planted step: brief, so it belongs to neither stretch
    rows = [dict(t=t0 - 5 * 86400, hemi="Left", amp=2.0, pw=60, rate=130, cathode="1"),
            dict(t=t0 + 20 * 86400 - 3600, hemi="Left", amp=4.0, pw=60, rate=130, cathode="1"),
            dict(t=t0 + 20 * 86400, hemi="Left", amp=2.5, pw=60, rate=130, cathode="1"),
            dict(t=t0 + 40 * 86400, hemi="Left", amp=3.0, pw=60, rate=130, cathode="1"),
            dict(t=t0 + 70 * 86400, hemi="Left", amp=3.5, pw=60, rate=130, cathode="1")]
    ch = held_transitions(rows)
    # three: the last setting is still in force, so it counts as held; the log ends before it
    assert len(ch) == 3 and ch[0]["n_brief_between"] == 1, ch
    got = [shift_at_change(c, chronic_readings([rec]), n_boot=500) for c in ch]
    planted, none = got[0], got[1]
    assert got[2]["readable"] is False, got[2]
    print(f"self-test: planted +40 -> {planted['shift']:+.1f} [{planted['ci_low']:+.1f}, "
          f"{planted['ci_high']:+.1f}] excludes 0 = {planted['interval_excludes_zero']}; "
          f"no step -> {none['shift']:+.1f} [{none['ci_low']:+.1f}, {none['ci_high']:+.1f}] "
          f"excludes 0 = {none['interval_excludes_zero']}")
    assert planted["interval_excludes_zero"] and 25 < planted["shift"] < 55, planted
    assert not none["interval_excludes_zero"], none
    # a change where the device also moved its band is refused, not read
    rec2 = dict(rec, FreqScheduleHz=[[t0 - 1, 23.44], [t0 + 20 * 86400, 8.79]])
    moved = shift_at_change(ch[0], chronic_readings([rec2]), n_boot=100)
    assert moved["readable"] is False and "another band" in moved["reason"], moved
    print("self-test: passed (the planted step found, the absent one not, a moved band refused)")


def main():
    if "--selftest" in sys.argv:
        _selftest()
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    import pandas as pd
    from modules.Biomarkers import bravo_service as B
    from modules.CacheStore import store as S
    uid = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
        else "2e3c75c00d7f4f37b53a048d195f11da"
    _selftest()
    settings, _stamp = S.load_newest("therapy_settings", uid, consumer="closed_loop")
    frame = pd.DataFrame(settings)
    rows = [dict(t=pd.Timestamp(r["t"]).timestamp(), hemi=r["hemi"],
                 **{f: (None if pd.isna(r[f]) else r[f]) for f in SETTING_FIELDS})
            for _, r in frame.iterrows()]
    runs = setting_runs(rows)
    held = held_transitions(rows)
    readings = chronic_readings(B._chronic_list_for(uid), hemi="Left")
    print(f"\nleft chronic log: {len(readings[0])} readings on "
          f"{len(np.unique(_ca_day(readings[0])))} California days")
    print(f"left-side settings: {len(runs)} runs of one setting, "
          f"{sum(1 for r in runs if r['days'] >= MIN_HOLD_DAYS)} held {MIN_HOLD_DAYS:g} days or longer, "
          f"{len(held)} transitions between consecutive held runs")
    print(f"level shift of the LEFT chronic band power at each held change -- {CAVEAT}\n")
    out = []
    for i, c in enumerate(held):
        r = shift_at_change(c, readings, seed=i)
        when = datetime.fromtimestamp(c["t"], tz=timezone.utc).astimezone(CA).strftime("%Y-%m-%d")
        what = ", ".join(f"{f} {c['before'][f]}->{c['after'][f]}" for f in SETTING_FIELDS
                         if c["before"][f] != c["after"][f])
        row = dict(date=when, change=what, held_days=round(float(c["held_days"]), 1),
                   held_days_before=round(float(c["held_days_before"]), 1),
                   brief_settings_between=c["n_brief_between"],
                   hours_between=round(float(c["hours_between"]), 1), **r)
        out.append(row)
        if r.get("readable"):
            print(f"{when}  {what:<34} held {c['held_days']:5.1f} d  {r['band_centre_hz']:g} Hz {r['contacts']:<5}"
                  f"  {r['level_before']:7.1f} -> {r['level_after']:7.1f}  shift {r['shift']:+7.1f} "
                  f"[{r['ci_low']:+.1f}, {r['ci_high']:+.1f}]  = {r['shift_in_scatter']:+.2f} x scatter "
                  f"({r['scatter_10_90_before']:.1f})  days {r['n_days_before']}/{r['n_days_after']}")
        else:
            print(f"{when}  {what:<34} held {c['held_days']:5.1f} d  not read: {r['reason']}")
    pd.DataFrame(out).to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "_stepB3_chronic_level_shift.csv"), index=False)
    n_read = sum(1 for r in out if r.get("readable"))
    n_step = sum(1 for r in out if r.get("readable") and r.get("interval_excludes_zero"))
    print(f"\n{n_read} of {len(out)} held changes readable; {n_step} with an interval excluding zero "
          f"(uncorrected for {n_read} changes tested) -- {CAVEAT}")


if __name__ == "__main__":
    main()
