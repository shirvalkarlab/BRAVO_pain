"""One row per held-current step of every streaming recording.

A step is a run of 2 Hz band-power samples in which both sides' current stays fixed. The first
3 s and last 1 s are dropped (the device's band power averages backwards in time). Power from the
voltage trace (TD) is computed by Welch (2 s Hann windows, 50 % overlap, 0.5 Hz bins), linear
units (uV^2/Hz), only inside gap-free stretches. No log anywhere.
"""
import glob, os, sys
import numpy as np, pandas as pd
from scipy.signal import welch
from multiprocessing import Pool

FS = 250.0
SRC = sys.argv[1] if len(sys.argv) > 1 else "td2"
IDX = pd.read_csv(os.path.join(SRC, "_index.csv")).set_index("key")


def landings(rate, kmax=40):
    """Where k * rate lands in 0..125 Hz after sampling at 250 Hz."""
    out = []
    for k in range(1, kmax + 1):
        f = (k * rate) % FS
        f = FS - f if f > FS / 2 else f
        out.append(round(f, 3))
    return sorted(set(f for f in out if 2.0 <= f <= 123.0))


def td_times(tk, ps):
    t = np.empty(ps.sum())
    i = 0
    for T, n in zip(tk, ps):
        t[i:i + n] = T - (n - 1 - np.arange(n)) * 4.0
        i += n
    return t


def psd_in(x, t, a, b):
    m = (t >= a) & (t <= b)
    xs, ts = x[m], t[m]
    if len(xs) < 500:
        return None, 0
    br = np.where(np.diff(ts) > 8.5)[0] + 1
    acc, nseg = None, 0
    for seg in np.split(xs, br):
        if len(seg) < 500:
            continue
        f, p = welch(seg, fs=FS, window="hann", nperseg=500, noverlap=250, detrend="constant",
                     scaling="density")
        k = 1 + (len(seg) - 500) // 250
        acc = p * k if acc is None else acc + p * k
        nseg += k
    if acc is None:
        return None, 0
    return acc / nseg, nseg


F = np.arange(0, 125.5, 0.5)


def line_metrics(p, lands):
    """Per landing: peak (max of bins within +-0.5 Hz) over local background (median of bins
    1.5-4 Hz either side, at least 1 Hz from any landing). Returns ratio and excess power (uV^2)."""
    near = np.zeros_like(F, bool)
    for f in lands:
        near |= np.abs(F - f) <= 1.0
    res = []
    for f in lands:
        pk = p[np.abs(F - f) <= 0.5].max()
        ring = (np.abs(F - f) >= 1.5) & (np.abs(F - f) <= 4.0) & ~near & (F >= 1.0)
        if ring.sum() < 3:
            continue
        bg = np.median(p[ring])
        res.append((f, pk / bg, max(pk - bg, 0.0) * 0.5 * 1.5))  # ~1.5 Hz Hann main lobe
    return res


def one(key):
    z = np.load(os.path.join(SRC, key + ".npz"))
    meta = IDX.loc[key]
    x, tk, ps = z["x"], z["tk"], z["ps"]
    t = td_times(tk, ps)
    bt, ma, mo, lfp = z["bt"], z["ma"], z["ma_o"], z["lfp"]
    rows = []
    if len(bt) < 10 or not np.isfinite(meta.rate):
        return rows
    lands = landings(float(meta.rate))
    band = [l for l in lands if 5.0 <= l <= 32.5]
    sense = float(meta.sense_hz) if np.isfinite(meta.sense_hz) else np.nan
    # runs of constant (ma, mo)
    chg = np.r_[True, (np.diff(ma) != 0) | (np.diff(mo) != 0)]
    starts = np.where(chg)[0]
    ends = np.r_[starts[1:] - 1, len(bt) - 1]
    for s, e in zip(starts, ends):
        a, b = bt[s] + 3000.0, bt[e] - 1000.0
        if b - a < 10000 or not np.isfinite(ma[s]):
            continue
        p, nseg = psd_in(x, t, a, b)
        if p is None or nseg < 5:
            continue
        lm = line_metrics(p, lands)
        notnear = np.ones_like(F, bool)
        for f in lands:
            notnear &= np.abs(F - f) > 1.0
        bb = (F >= 5) & (F <= 32.5) & notnear
        hi = (F >= 60) & (F <= 120) & notnear
        sb = (np.abs(F - sense) <= 2.5) if np.isfinite(sense) else np.zeros_like(F, bool)
        m = (t >= a) & (t <= b)
        xs = x[m]
        lseg = lfp[s:e + 1][bt[s:e + 1] >= a]
        inband = [r for r in lm if 5.0 <= r[0] <= 32.5]
        insense = [r for r in lm if np.isfinite(sense) and abs(r[0] - sense) <= 3.0]
        rows.append(dict(
            key=key, side=meta.side, channel=meta.channel, pw=meta.pw, rate=meta.rate,
            contacts=meta.contacts, other_pw=meta.other_pw, session=str(meta.session)[:10],
            sense_hz=sense, blank_us=meta.blank_us, ma=float(ma[s]), ma_other=float(mo[s]),
            dur_s=(b - a) / 1000.0, nseg=nseg,
            charge_nC=float(ma[s]) * float(meta.pw),  # mA * us = nC per phase
            line_ratio_max=max([r[1] for r in lm], default=np.nan),
            line_ratio_max_f=(max(lm, key=lambda r: r[1])[0] if lm else np.nan),
            line_ratio_band_max=max([r[1] for r in inband], default=np.nan),
            line_excess_total=sum(r[2] for r in lm),
            line_excess_band=sum(r[2] for r in inband),
            line_excess_sense=sum(r[2] for r in insense),
            line_ratio_at_rate=next((r[1] for r in lm if abs(r[0] - (meta.rate if meta.rate <= 125 else FS - meta.rate)) < 0.01), np.nan),
            n_lines_ratio5=sum(r[1] >= 5 for r in lm),
            bb_5_32=float(p[bb].mean()), bb_60_120=float(p[hi].mean()),
            td_sense=float(p[sb].mean()) if sb.any() else np.nan,
            td_rms=float(np.sqrt(np.mean((xs - xs.mean()) ** 2))),
            td_absmax=float(np.abs(xs).max()),
            td_p999=float(np.percentile(np.abs(xs - np.median(xs)), 99.9)),
            lfp_med=float(np.median(lseg)) if len(lseg) else np.nan,
            lfp_max=float(np.max(lseg)) if len(lseg) else np.nan,
            lfp_n=len(lseg),
            lfp_n_spike=int(np.sum(lseg > 10 * max(np.median(lseg), 1.0))) if len(lseg) else 0,
        ))
    return rows


if __name__ == "__main__":
    keys = list(IDX.index)
    out = []
    with Pool(12) as pool:
        for r in pool.imap_unordered(one, keys, chunksize=4):
            out.extend(r)
    d = pd.DataFrame(out)
    d.to_csv("steps.csv", index=False)
    print("steps", len(d), "recordings with >=1 step", d.key.nunique(), "of", len(keys))
