import json, numpy as np, datetime as dt, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
d = json.load(open('BRAVO/_review_export_rcs08.json'))

BIN = {"high": "#D55E00", "low": "#0072B2", "excluded": "#5A6066"}
DIM = "#AEB4BB"
HEMI_COLOR = {"LEFT": "#9C8BC4", "RIGHT": "#C4A48B"}
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
                     "font.size": 9, "axes.linewidth": 0.8})

def pain_series(key):
    m = [x for x in d['pain_metrics'] if x['key'] == key][0]
    t, y = [], []
    for p in m['points']:
        ts = dt.datetime.fromisoformat(p['t']).replace(tzinfo=dt.timezone.utc).timestamp()
        t.append(ts); y.append(p['v'])
    return np.array(t), np.array(y), m.get('label', key)

ts, ys, lbl = pain_series('nrs')
order = np.argsort(ts); tss, yss = ts[order], ys[order]
idx = d['psd_scan_index']
it = np.array([e['t'] for e in idx])
ich = np.array([e['channel'] for e in idx])

def match(tol):
    tol_s = tol * 60
    pos = np.searchsorted(tss, it)
    best = np.full(len(it), np.nan)
    for kk, p in enumerate(pos):
        cand = []
        for j in (p - 1, p):
            if 0 <= j < len(tss):
                dd = abs(tss[j] - it[kk])
                if dd <= tol_s: cand.append((dd, yss[j]))
        if cand: best[kk] = min(cand)[1]
    return best

def binarize(best):
    # Mutually-exclusive, low-wins-on-ties — matches binarizationModel.js classify():
    #   v <= lowCut -> low ; elif v >= highCut -> high ; else excluded.
    fin = np.isfinite(best); ref = best[fin]
    lo, hi = np.percentile(ref, 33.3333), np.percentile(ref, 66.6667)
    lab = np.full(len(best), "unmatched", dtype=object)
    is_low = fin & (best <= lo)
    is_high = fin & ~is_low & (best >= hi)
    lab[is_low] = "low"
    lab[is_high] = "high"
    lab[fin & ~is_low & ~is_high] = "excluded"
    return lab, lo, hi

PAIR_ORDER = ["ZERO_THREE", "ONE_THREE", "ZERO_TWO"]
HEMIS = ["LEFT", "RIGHT"]
CHS = [f"{p}_{h}" for p in PAIR_ORDER for h in HEMIS]
span = d['span']; t0, t1 = span[0], span[1]
def xf(tep): return (tep - t0) / (t1 - t0)

def recs(ch, dtype):
    return [r for r in d['records'] if str(r['channel']).upper() == ch and r['dtype'] == dtype]

def draw_timeline(ax, bin_mode, tol=15):
    if bin_mode:
        best = match(tol); lab, lo, hi = binarize(best)
        binmap = {}
        for e, l in zip(idx, lab):
            binmap[(e['channel'], round(e['t']))] = l
    n = len(CHS)
    for i, ch in enumerate(CHS):
        yb = 1 - (i + 1) / (n + 1)
        h = 1 / (n + 1)
        hemi = "LEFT" if ch.endswith("LEFT") else "RIGHT"
        # TD coverage
        for r in recs(ch, "timedomain"):
            ts0 = r['t_start']; te = ts0 + max(r.get('dur_s', 0) or 0, 86400)
            fc, op = HEMI_COLOR[hemi], 0.85
            if bin_mode:
                b = binmap.get((ch, round(ts0)), "unmatched")
                if b in BIN: fc, op = BIN[b], 0.92
                else: fc, op = DIM, 0.45
            ax.add_patch(Rectangle((xf(ts0), yb + 0.04 * h), max(xf(te) - xf(ts0), 0.001), 0.38 * h,
                                   facecolor=fc, edgecolor="none", alpha=op))
        # PSD ticks
        for r in recs(ch, "psd"):
            ts0 = r['t_start']
            col, ms = "#9AA0A6", 5
            if bin_mode:
                b = binmap.get((ch, round(ts0)), "unmatched")
                col = BIN[b] if b in BIN else DIM
                ms = 8 if b in BIN else 5
            ax.plot([xf(ts0)], [yb + 0.86 * h], marker="|", color=col, ms=ms,
                    mew=2.0 if bin_mode else 1.2)
        # bandpower
        bp = recs(ch, "bandpower")
        if bp:
            xs = [xf(r['t_start']) for r in bp]
            ax.plot(xs, [yb + 0.62 * h] * len(xs), ".", color=(DIM if bin_mode else "#21918c"),
                    ms=2, alpha=0.5 if bin_mode else 0.9)
        ax.text(-0.01, yb + 0.45 * h, ch.replace("_", " "), ha="right", va="center", fontsize=7.5, color="#444")
    # pain row
    pb, pt = 0.02, 1 / (n + 1) * 0.9
    pl, ph = yss.min(), yss.max()
    def ysc(v): return pb + (pt - pb) * (v - pl) / max(1e-9, ph - pl)
    if bin_mode:
        best = match(tol); _, lo, hi = binarize(best)
        cols = ["#0072B2" if v <= lo else ("#D55E00" if v >= hi else "#7E8794") for v in ys]
        ax.plot([xf(x) for x in ts], [ysc(v) for v in ys], lw=1.0, color="#999999", alpha=0.4, zorder=1)
        ax.scatter([xf(x) for x in ts], [ysc(v) for v in ys], s=12, c=cols, zorder=2)
    else:
        ax.plot([xf(x) for x in ts], [ysc(v) for v in ys], lw=1.2, color="#3A4A63", alpha=0.5)
        ax.scatter([xf(x) for x in ts], [ysc(v) for v in ys], s=8, c="#3A4A63", alpha=0.6)
    ax.text(-0.01, pt * 0.55, lbl, ha="right", va="center", fontsize=7.5, color="#C44E00", fontweight="bold")
    ax.set_xlim(-0.13, 1.02); ax.set_ylim(0, 1); ax.set_yticks([]); ax.set_xticks([])
    for s in ax.spines.values(): s.set_visible(False)

# Figure 1: timeline multimodal vs binarization
fig, axes = plt.subplots(2, 1, figsize=(11, 8))
draw_timeline(axes[0], False)
axes[0].set_title("Timeline — Multimodal view (lanes colored by sensing frequency)", fontsize=11, fontweight="bold", loc="left")
draw_timeline(axes[1], True, tol=15)
axes[1].set_title("Timeline — Binarization view (matched neural samples colored by pain bin, rest dimmed) · tertile · ±15 min",
                  fontsize=11, fontweight="bold", loc="left")
leg = [Line2D([0], [0], marker="s", color="w", markerfacecolor=BIN["high"], ms=10, label="HIGH pain"),
       Line2D([0], [0], marker="s", color="w", markerfacecolor=BIN["low"], ms=10, label="LOW pain"),
       Line2D([0], [0], marker="s", color="w", markerfacecolor=BIN["excluded"], ms=10, label="excluded middle"),
       Line2D([0], [0], marker="s", color="w", markerfacecolor=DIM, ms=10, label="not in binarized set")]
axes[1].legend(handles=leg, loc="upper right", ncol=4, fontsize=8, frameon=False, bbox_to_anchor=(1.0, 1.12))
fig.tight_layout()
fig.savefig("_review_export/preview_timeline_toggle.png", dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)

# Figure 2: binarization histogram at two windows
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, tol in zip(axes, (15, 60)):
    best = match(tol); fin = np.isfinite(best); ref = best[fin]
    lo, hi = np.percentile(ref, 33.3333), np.percentile(ref, 66.6667)
    bins = np.arange(np.floor(ref.min()) - 0.25, np.ceil(ref.max()) + 0.75, 0.5)
    ctr = (bins[:-1] + bins[1:]) / 2
    cnt, _ = np.histogram(ref, bins=bins)
    cols = [BIN["low"] if c <= lo else (BIN["high"] if c >= hi else BIN["excluded"]) for c in ctr]
    ax.bar(ctr, cnt, width=0.46, color=cols)
    ax.axvline(lo, color=BIN["low"], ls="--", lw=1.5)
    ax.axvline(hi, color=BIN["high"], ls="--", lw=1.5)
    # Mutually-exclusive classification (matches the model's if/elif): low first, then high, rest excluded.
    lab_h, _, _ = binarize(best)
    nlow = int((lab_h == "low").sum()); nhigh = int((lab_h == "high").sum()); nmid = int((lab_h == "excluded").sum())
    ax.set_title(f"Match window ±{tol} min — {int(fin.sum())} matched neural samples\n"
                 f"{nhigh} high / {nlow} low / {nmid} excluded", fontsize=10, fontweight="bold")
    ax.set_xlabel(lbl); ax.set_ylabel("Matched neural samples")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
fig.suptitle("Data available to binarize — recolors & recounts live as the match window moves", fontsize=12, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig("_review_export/preview_binarization_hist.png", dpi=150, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("rendered both preview PNGs")
