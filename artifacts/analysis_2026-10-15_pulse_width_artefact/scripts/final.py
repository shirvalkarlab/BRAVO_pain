"""Pulse width against stimulation artefact, from the held-current steps (steps4.*).

Line size: for every folded multiple (1st..8th) of the stimulation rate inside 2-123 Hz, the power
in the three bins at the landing above the local background (uV^2). Each sensing pair's own
stimulation-off steps (both sides 0 mA) give the baseline for the same landing set, which removes
the fixed device peaks at 55.5 and 111 Hz. Amplitude = sqrt(net power), uV. All linear; no log.
"""
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd
from steps import F, landings
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 300)
rng = np.random.default_rng(0)
d = pd.read_csv("steps4.csv"); P = np.load("steps4_psd.npy")
d["grp"] = np.where(d.pw <= 60, "<=60", np.where(d.pw > 120, ">120", "61-120"))
TONES = (55.5, 111.0)


def excess(p, lands, lo=2.0, hi=123.0):
    near = np.zeros_like(F, bool)
    for g in list(lands) + list(TONES):
        near |= np.abs(F - g) <= 1.0
    tot = 0.0
    for f in lands:
        if not lo <= f <= hi:
            continue
        i = int(np.argmin(np.abs(F - f)))
        ring = (np.abs(F - f) >= 1.5) & (np.abs(F - f) <= 4.0) & ~near & (F >= 1)
        if ring.sum() < 3:
            continue
        tot += np.clip(p[i - 1:i + 2] - np.median(p[ring]), 0, None).sum() * 0.5
    return tot


off = (d.ma == 0) & (d.ma_other_max == 0)
_cache = {}


def off_vals(ch, rate, lo, hi):
    k = (ch, rate, lo, hi)
    if k not in _cache:
        o = np.where(off & (d.channel == ch))[0]
        _cache[k] = np.array([excess(P[j], landings(rate), lo, hi) for j in o])
    return _cache[k]


for tag, lo, hi in (("all", 2.0, 123.0), ("band", 5.0, 32.5)):
    E = np.array([excess(P[i], landings(r), lo, hi) for i, r in enumerate(d.rate)])
    base = np.zeros(len(d))
    for i, r in enumerate(d.itertuples()):
        v = off_vals(r.channel, r.rate, lo, hi)
        base[i] = np.median(v) if len(v) else np.nan
    d[f"E_{tag}"] = E; d[f"B_{tag}"] = base
    d[f"A_{tag}"] = np.sqrt(np.clip(E - base, 0, None))          # uV
    # detection: above the 95th percentile of the pair's own stimulation-off values
    q = np.zeros(len(d))
    for i, r in enumerate(d.itertuples()):
        v = off_vals(r.channel, r.rate, lo, hi)
        q[i] = np.percentile(v, 95) if len(v) >= 5 else np.nan
    d[f"det_{tag}"] = np.where(np.isnan(q), np.nan, (E > q).astype(float))
print("stimulation-off steps per pair:", d[off].groupby("channel").size().to_dict())
d.to_pickle("steps4_scored.pkl")

on = d[d.ma > 0]


def slope0(x, y):
    """Least-squares slope through the origin (no current, no artefact)."""
    return float((x * y).sum() / (x * x).sum())


def boot_ratio(a, b, col, n=4000):
    """Ratio of slopes, resampling whole recordings in each group."""
    ka, kb = a.key.unique(), b.key.unique()
    ga, gb = {k: a[a.key == k] for k in ka}, {k: b[b.key == k] for k in kb}
    out = []
    for _ in range(n):
        aa = pd.concat([ga[k] for k in rng.choice(ka, len(ka))]); bb = pd.concat([gb[k] for k in rng.choice(kb, len(kb))])
        sa = slope0(aa.ma, aa[col]); sb = slope0(bb.ma, bb[col])
        out.append(sb / sa if sa > 0 else np.inf)
    return np.percentile(out, [2.5, 97.5])


print("\nMATCHED COMPARISONS: same sensing pair and rate, both groups with current on")
rows = []
for (ch, rate), g in on.groupby(["channel", "rate"]):
    lo, hi = g[g.grp == "<=60"], g[g.grp == ">120"]
    if lo.empty or hi.empty:
        continue
    cap = min(lo.ma.max(), hi.ma.max())                         # compare only over shared currents
    for name, sub in (("<=60", lo), ("61-120", g[g.grp == "61-120"]), (">120", hi)):
        if sub.empty:
            continue
        s = sub[sub.ma <= cap + 1e-9]
        rows.append(dict(channel=ch, rate=rate, grp=name, pws="/".join(map(str, sorted(sub.pw.unique()))),
                         recs=sub.key.nunique(), days=sub.session.nunique(), steps=len(sub),
                         mA=f"{sub.ma.min():g}-{sub.ma.max():g}", shared_cap=cap, steps_shared=len(s),
                         det_all=round(s.det_all.mean(), 2), A_all_med=round(s.A_all.median(), 3),
                         slope_all=round(slope0(s.ma, s.A_all), 3) if len(s) else np.nan,
                         det_band=round(s.det_band.mean(), 2), A_band_med=round(s.A_band.median(), 3),
                         slope_band=round(slope0(s.ma, s.A_band), 3) if len(s) else np.nan,
                         lfp_med=s.lfp_med.median(), p999=round(s.td_p999.median(), 1)))
    a, b = lo[lo.ma <= cap + 1e-9], hi[hi.ma <= cap + 1e-9]
    if a.empty or b.empty:
        print(f"{ch} {rate} Hz: no shared current range"); continue
    for col in ("A_all", "A_band"):
        sa, sb = slope0(a.ma, a[col]), slope0(b.ma, b[col])
        ci = boot_ratio(a, b, col) if a.key.nunique() > 1 and b.key.nunique() > 1 else (np.nan, np.nan)
        print(f"{ch} {rate} Hz {col}: slope <=60 {sa:.3f}, >120 {sb:.3f} uV/mA; ratio {sb / sa if sa > 0 else np.inf:.2f} "
              f"(95% interval over recordings {ci[0]:.2f} to {ci[1]:.2f}); charge model predicts {b.pw.mean() / a.pw.mean():.2f}")
m = pd.DataFrame(rows)
print(m.to_string(index=False))
m.to_csv("matched.csv", index=False)

print("\nALL CURRENT-ON STEPS, by pair and group (descriptive)")
on = d[d.ma > 0].copy(); on["mAbin"] = pd.cut(on.ma, [0, 1, 2, 3, 4, 6])
desc = on.groupby(["channel", "grp", "mAbin"], observed=True).agg(
    recs=("key", "nunique"), days=("session", "nunique"), steps=("key", "size"),
    det_all=("det_all", "mean"), A_all_med=("A_all", "median"), A_all_p90=("A_all", lambda s: s.quantile(.9)),
    det_band=("det_band", "mean"), A_band_med=("A_band", "median"), A_band_max=("A_band", "max"),
    bb=("bb_5_32", "median"), p999=("td_p999", "median"), absmax=("td_absmax", "max"),
    lfp=("lfp_med", "median"), spikes=("lfp_n_spike", "sum"), lfp_n=("lfp_n", "sum")).round(3)
print(desc.to_string())
desc.to_csv("descriptive.csv")
