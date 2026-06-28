"""
Sliding-window calibration of k (LSB/µV²) from concurrent BrainSense TD + PowerDomain LSB.

Design:
  - Window:  3000 ms of raw 250 Hz TD  (matches device Dual/SingleInverse averaging_ms=3000)
  - Step:    500 ms  (2 Hz LSB update rate — one comparison per LSB sample)
  - Welch:   nperseg=256 (1.024 s), hann window, density scaling — EXACT k=269 calibration path
  - Pairing: each LSB sample at t paired with TD window [t-3s, t] (causal IIR match).
             Windows with >10% Missing-flagged samples dropped.
  - Stim:    only stim-off samples (< STIM_OFF_MA mA) used.
  - Output:  per (channel, session, center_hz) k values + full pairs CSV.

Performance: FULLY VECTORIZED — no Python loop over LSB samples.
  All valid TD windows for a (session × channel) are stacked into one (N, 750) matrix,
  then processed with a single batch FFT (numpy rfft over axis=-1), giving a (N, 129)
  power matrix. Band integrals and k values are computed in one numpy pass.
  Inner Python loop is only over TD recordings (~232), not over individual LSB samples (~100k).
"""
import os, sys, json, csv, collections
import numpy as np
from scipy.signal import welch as _welch
from scipy.stats import spearmanr

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
sys.path.insert(0, "/usr/src/BRAVO")
import django; django.setup()

from modules.Biomarkers import bravo_service as bs
from modules.Biomarkers.routines import analytics as an
from modules.Biomarkers.routines import availability as av

UID         = "2e3c75c00d7f4f37b53a048d195f11da"
WIN_S       = 3.0     # window length (s) — matches device averaging_ms
BAND_HALF   = 2.5     # ±Hz around sensing center
STIM_OFF_MA = 0.1     # mA threshold for stim-off
MAX_MISS    = 0.10    # max Missing fraction allowed in a window
ADC_NV      = an.ADC_NV_PER_LSB   # 146 nV/count -> µV when /1000

# ── Load all recordings ONCE ─────────────────────────────────────────────────
print("Loading recordings...")
td_recs  = bs._load_recordings(UID, ["MedtronicBrainSenseTimeDomain"])
pd_recs  = bs._load_recordings(UID, ["MedtronicBrainSensePowerDomain"])
chronic  = bs._load_recordings(UID, bs.CHRONIC_TYPES)
pdl      = bs._load_recordings(UID, bs.POWERDOMAIN_TYPES)
print(f"  TD:{len(td_recs)}  PD:{len(pd_recs)}  chronic:{len(chronic)}  pdl:{len(pdl)}")

# ── Pre-build center_hz lookup: channel -> most common sensing Hz ─────────────
print("Building center-Hz cache from lsb_series...")
lsb_all = av.lsb_series(chronic, pdl)
center_cache = {}   # channel_upper -> float Hz
for ch, d in lsb_all.items():
    centers = np.asarray(d.get("center_hz", []), dtype=float)
    centers = centers[np.isfinite(centers) & (centers > 0)]
    if len(centers):
        vals, cnt = np.unique(np.round(centers, 1), return_counts=True)
        center_cache[ch.upper()] = float(vals[np.argmax(cnt)])
print(f"  center_cache: {center_cache}")

def get_center(ch_name):
    return center_cache.get(ch_name.upper())

# ── Index PD records by start time ───────────────────────────────────────────
pd_by_start = collections.defaultdict(list)
for r in pd_recs:
    try: s = round(float(r.get("StartTime")))
    except: continue
    pd_by_start[s].append(r)

def find_pd(td_start, tol=10):
    base = round(float(td_start))
    for d in range(-tol, tol + 1):
        hits = pd_by_start.get(base + d)
        if hits:
            return hits
    return []

# ── Batch Welch: all windows in one (N, n_win) matrix → (N,) band power ──────
NPERSEG = 256
_HANN    = np.hanning(NPERSEG).astype(np.float32)     # length-256 hann window
_HANN_SS = float(np.sum(_HANN**2))                    # normalisation denominator
_NOVERLAP = NPERSEG // 2                              # 50% overlap (scipy default)
_STEP_SEG = NPERSEG - _NOVERLAP                       # 128 samples

def batch_welch_band_power(windows_uv, fs, center_hz, half=BAND_HALF):
    """
    windows_uv : (N, n_win) float32 — N causal 3-s TD windows in µV
    Returns     : (N,) float64 — band-integrated power in µV² (nan where undefined)
    """
    N, n_win = windows_uv.shape
    # number of 256-pt sub-segments that fit (scipy: (n_win - nperseg)//step + 1)
    n_segs = (n_win - NPERSEG) // _STEP_SEG + 1
    if n_segs < 1:
        return np.full(N, np.nan)

    # Stack all sub-windows: (N, n_segs, 256)
    segs = np.stack(
        [windows_uv[:, i*_STEP_SEG : i*_STEP_SEG + NPERSEG] for i in range(n_segs)],
        axis=1
    ).astype(np.float64)

    # Detrend (remove mean of each sub-window) + apply hann
    segs -= segs.mean(axis=2, keepdims=True)
    segs *= _HANN[np.newaxis, np.newaxis, :]           # broadcast (1,1,256)

    # Batch rfft → (N, n_segs, 129); one-sided power density
    rft = np.fft.rfft(segs, n=NPERSEG, axis=2)        # (N, n_segs, 129)
    pwr = (np.abs(rft)**2) / (fs * _HANN_SS)
    pwr[:, :, 1:-1] *= 2.0                             # double one-sided bins
    pwr = pwr.mean(axis=1)                             # average segments → (N,129)

    freqs = np.fft.rfftfreq(NPERSEG, d=1.0/fs)        # (129,)
    m = (freqs >= center_hz - half) & (freqs < center_hz + half)
    if m.sum() < 2:
        return np.full(N, np.nan)

    return np.trapezoid(pwr[:, m], freqs[m], axis=1)  # (N,) µV²

# ── Main pairing loop (over sessions, vectorized over LSB samples) ────────────
rows = []
n_td_skipped = 0

for ti, td in enumerate(td_recs):
    try: ts = float(td.get("StartTime"))
    except: continue

    pds = find_pd(ts)
    if not pds:
        n_td_skipped += 1
        continue

    td_chans = list(td.get("ChannelNames") or [])
    td_data  = np.asarray(td.get("Data"), dtype=np.float32)   # (n_samp, n_ch)
    fs       = float(td.get("SamplingRate") or 250.0) or 250.0
    n_win    = int(WIN_S * fs)

    if td_data.ndim != 2 or td_data.shape[0] < n_win:
        continue

    # Missing mask (n_samp,)
    td_miss = td.get("Missing")
    if td_miss is not None:
        ma = np.asarray(td_miss, dtype=np.float32).ravel()
        miss_mask = (ma > 0) if ma.size == td_data.shape[0] else np.zeros(td_data.shape[0], bool)
    else:
        miss_mask = np.zeros(td_data.shape[0], bool)

    # Precompute per-window missing fractions via cumsum → O(n_samp) not O(n_win*n_lsb)
    miss_cum = np.concatenate([[0], np.cumsum(miss_mask.astype(np.float32))])

    session_id = str(round(ts))

    for pd_rec in pds:
        pd_data  = np.asarray(pd_rec.get("Data"), dtype=np.float64)
        pd_chans = list(pd_rec.get("ChannelNames") or [])
        try: pd_start = float(pd_rec.get("StartTime"))
        except: pd_start = ts
        pd_fs = float(pd_rec.get("SamplingRate") or 2.0) or 2.0

        if pd_data.ndim != 2: continue

        for ci, td_ch in enumerate(td_chans):
            if ci >= td_data.shape[1]: continue

            center_hz = get_center(td_ch)
            if center_hz is None: continue

            td_ch_up = td_ch.upper()
            pcol = scol = None
            for pi, nm in enumerate(pd_chans):
                nu = str(nm).upper()
                if td_ch_up in nu and "POWER" in nu: pcol = pi
                if td_ch_up in nu and "STIM"  in nu: scol = pi
            if pcol is None or pcol >= pd_data.shape[1]: continue

            lsb_arr  = pd_data[:, pcol]
            stim_arr = (pd_data[:, scol]
                        if scol is not None and scol < pd_data.shape[1]
                        else np.zeros(len(lsb_arr)))

            # ── Vectorized filter: all LSB samples at once ────────────────
            li_all   = np.arange(len(lsb_arr))
            t_lsb_all = pd_start + li_all / pd_fs
            end_all   = np.round((t_lsb_all - ts) * fs).astype(int)
            start_all = end_all - n_win

            valid = (
                np.isfinite(lsb_arr) & (lsb_arr > 0) &
                (stim_arr < STIM_OFF_MA) &
                (start_all >= 0) & (end_all <= td_data.shape[0])
            )
            if not valid.any(): continue

            idx_v    = np.where(valid)[0]
            starts_v = start_all[idx_v]
            ends_v   = end_all[idx_v]
            lsb_v    = lsb_arr[idx_v]
            t_lsb_v  = t_lsb_all[idx_v]

            # Vectorized missing fraction via cumsum: O(n_valid) not O(n_valid*n_win)
            miss_frac = (miss_cum[ends_v] - miss_cum[starts_v]) / n_win
            keep      = miss_frac <= MAX_MISS
            if not keep.any(): continue

            starts_v = starts_v[keep]; ends_v = ends_v[keep]
            lsb_v    = lsb_v[keep];   t_lsb_v = t_lsb_v[keep]

            # TD column in µV; stack all valid windows → (N, n_win)
            td_col_uv = td_data[:, ci] * np.float32(ADC_NV / 1000.0)
            windows   = np.stack([td_col_uv[s:e] for s, e in zip(starts_v, ends_v)])

            # Drop windows with any non-finite value
            fin_ok  = np.isfinite(windows).all(axis=1)
            if not fin_ok.any(): continue
            windows  = windows[fin_ok]
            lsb_v    = lsb_v[fin_ok]
            t_lsb_v  = t_lsb_v[fin_ok]

            # Batch Welch → band power for all windows at once
            uv2_v = batch_welch_band_power(windows, fs, center_hz)
            good  = np.isfinite(uv2_v) & (uv2_v > 0)
            if not good.any(): continue

            for t_l, lsb_val, uv2 in zip(t_lsb_v[good], lsb_v[good], uv2_v[good]):
                rows.append({
                    "channel":    td_ch,
                    "session_id": session_id,
                    "t_lsb":      round(float(t_l), 2),
                    "center_hz":  center_hz,
                    "uv2":        round(float(uv2), 8),
                    "lsb":        round(float(lsb_val), 4),
                    "k":          round(float(lsb_val / uv2), 4),
                })

print(f"\nTotal paired windows: {len(rows)}  (TD recs without PD match: {n_td_skipped})")
if not rows:
    print("NO PAIRS — check center_cache and PD column matching"); raise SystemExit(1)
print(f"Channels: {sorted({r['channel'] for r in rows})}")

# ── Save full pairs CSV ───────────────────────────────────────────────────────
OUT_CSV = "/usr/src/BRAVO/_agent_bridge/sliding_calib_pairs.csv"
fields = list(rows[0].keys())
with open(OUT_CSV, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
print(f"Saved pairs CSV: {OUT_CSV}")

# ── Per (channel × center_hz) summary ────────────────────────────────────────
summaries = []
by_ch_hz  = collections.defaultdict(list)
for r in rows:
    by_ch_hz[(r["channel"], r["center_hz"])].append(r)

for (ch, hz), grp in sorted(by_ch_hz.items()):
    n = len(grp)
    if n < 5: continue
    ks   = np.array([r["k"]   for r in grp], dtype=float)
    uv2s = np.array([r["uv2"] for r in grp], dtype=float)
    lsbs = np.array([r["lsb"] for r in grp], dtype=float)
    sessions = sorted({r["session_id"] for r in grp})
    rho, p_rho = spearmanr(np.log10(uv2s), np.log10(lsbs))
    slope, intercept = np.polyfit(np.log10(uv2s), np.log10(lsbs), 1)
    k_fold = float(np.exp(np.std(np.log(ks[ks>0])))) if (ks > 0).sum() > 1 else np.nan
    summaries.append(dict(
        channel=ch, center_hz=hz, n=n, n_sessions=len(sessions),
        sessions="|".join(sessions),
        k_median=round(float(np.median(ks)), 2),
        k_p10=round(float(np.percentile(ks, 10)), 2),
        k_p90=round(float(np.percentile(ks, 90)), 2),
        k_sigma_fold=round(k_fold, 3),
        loglog_slope=round(float(slope), 4),
        loglog_intercept=round(float(intercept), 4),
        spearman_rho=round(float(rho), 3),
        spearman_p=round(float(p_rho), 5),
    ))

print(f"\n{'Channel':<24} {'Hz':>6} {'n':>6} {'sess':>5} {'k_med':>8} {'fold':>6} {'rho':>6}")
print("-" * 65)
for s in summaries:
    print(f"  {s['channel']:<22} {s['center_hz']:6.1f} {s['n']:6d} {s['n_sessions']:5d} "
          f"{s['k_median']:8.1f} {s['k_sigma_fold']:6.2f} {s['spearman_rho']:6.3f}")

OUT_SUM = "/usr/src/BRAVO/_agent_bridge/sliding_calib_summary.json"
with open(OUT_SUM, "w") as f:
    json.dump(summaries, f, indent=2)
print(f"\nSaved summary JSON: {OUT_SUM}")
