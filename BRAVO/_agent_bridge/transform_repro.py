"""
Reproduce the percept-spectral-repro 'transform' model (HANDOFF: r=0.993, RMSE 60.6 LSB,
k=352.6) on RCS08 concurrent BrainSenseTimeDomain -> BrainSenseLfp/PowerDomain blocks.

The transform DSP is copied VERBATIM from
  github.com/shirvalkarlab/percept-spectral-repro  src/percept_spectral_repro/spectral.py
  + products.brainsense_streaming_selected_band_power
so the candidate uV^2 is byte-identical to the repo.

Pairing is BLOCK-LEVEL (matching the repo benchmark):
  - candidate uV^2  = median over 250-sample windows of band_power_uv2(transform DSP)
  - target  LSB     = median device LSB over the paired PowerDomain block (stim-off)
Then a single global scale k = median(LSB / uV^2) is fit (the repo's fitted_scale), plus a
report/block-held-out 5-fold CV k. Metrics: Pearson r, RMSE (LSB), median fold-error.
Welch256 x fixed-269 and x fitted-k are computed as comparators.
"""
import os, sys, json, csv
import numpy as np
from scipy.signal import welch as _welch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
sys.path.insert(0, "/usr/src/BRAVO")
import django; django.setup()
from modules.Biomarkers import bravo_service as bs
from modules.Biomarkers.routines import availability as av, analytics as an

UID = "2e3c75c00d7f4f37b53a048d195f11da"
WIDTH_HZ    = 5.0
STIM_OFF_MA = 0.1
ADC_NV      = an.ADC_NV_PER_LSB   # device counts -> uV when /1000

# ─────────────────────────────────────────────────────────────────────────────
# VERBATIM transform DSP from percept-spectral-repro/spectral.py + products.py
#   default selected-band product params: nonzero=250, step=250, window=rcs_hann,
#   n_fft=256, detrend=mean, scale=peak, aggregation=mean_magnitude
# ─────────────────────────────────────────────────────────────────────────────
N_FFT=256; NONZERO=250; STEP=250; SR=250.0; MAXF=96.68

def percept_frequency_bins(sr=SR, n_fft=N_FFT, maxf=MAXF):
    bins = np.round(np.arange(n_fft//2 + 1) * sr / n_fft, 2)
    return bins[bins <= maxf + 1e-9]

def _rcs_hann(nonzero, n_fft):
    coeffs = np.zeros(n_fft)
    n = np.arange(nonzero)
    coeffs[:nonzero] = 0.5 * (1 - np.cos(2*np.pi*n/nonzero))   # rcs_hann
    return coeffs

_COEFFS = _rcs_hann(NONZERO, N_FFT)
_FREQS  = percept_frequency_bins()

def survey_spectrum_one_window(win):
    # detrend = mean (per-window), window=rcs_hann, scale=peak (2/n_fft),
    # aggregation=mean_magnitude over the single window
    w = np.asarray(win, dtype=float)
    w = w - np.nanmean(w)
    padded = np.zeros(N_FFT); padded[:NONZERO] = w
    mag = np.abs(np.fft.rfft(padded * _COEFFS, n=N_FFT))
    mag = 2.0 * mag / N_FFT            # scale="peak"
    return mag[:len(_FREQS)]

def band_power_uv2(mags, center_hz, width=WIDTH_HZ):
    half = width/2.0
    mask = (_FREQS >= center_hz-half) & (_FREQS <= center_hz+half)
    return float(np.sum(mags[mask]**2))   # sum of squared magnitudes

def transform_uv2_block(samples_uv, center_hz):
    """Median over 250-sample non-overlapping windows of the band power."""
    v = np.asarray(samples_uv, dtype=float)
    v = v[np.isfinite(v)]
    if v.size < NONZERO: return None
    starts = range(0, v.size - NONZERO + 1, STEP)
    powers = [band_power_uv2(survey_spectrum_one_window(v[s:s+NONZERO]), center_hz)
              for s in starts]
    powers = [p for p in powers if np.isfinite(p)]
    return float(np.median(powers)) if powers else None

def welch256_uv2_block(samples_uv, center_hz, width=WIDTH_HZ):
    v = np.asarray(samples_uv, dtype=float); v = v[np.isfinite(v)]
    if v.size < 256: return None
    f, p = _welch(v, fs=SR, window="hann", nperseg=256, detrend="constant", scaling="density")
    half = width/2.0
    m = (f >= center_hz-half) & (f < center_hz+half)
    return float(np.trapezoid(p[m], f[m])) if m.sum() >= 2 else None

# ─────────────────────────────────────────────────────────────────────────────
# Load paired blocks
# ─────────────────────────────────────────────────────────────────────────────
td_recs = bs._load_recordings(UID, ["MedtronicBrainSenseTimeDomain"])
pd_recs = bs._load_recordings(UID, ["MedtronicBrainSensePowerDomain"])
chronic = bs._load_recordings(UID, bs.CHRONIC_TYPES)
pdl     = bs._load_recordings(UID, bs.POWERDOMAIN_TYPES)
print(f"TD:{len(td_recs)}  PD:{len(pd_recs)}")

# Per-block sensing center: read from each PowerDomain record's own
# Descriptor.Therapy.{Left,Right}.FrequencyInHertz (the band the device actually sensed
# for THAT block), matched to the channel's side. This is the repo's lfp.left/right_frequency_hz.
def side_of(name):
    u = str(name).upper()
    if "LEFT" in u:  return "Left"
    if "RIGHT" in u: return "Right"
    return None

def block_center(pd_rec, ch_name):
    desc = pd_rec.get("Descriptor") if isinstance(pd_rec.get("Descriptor"), dict) else {}
    ther = desc.get("Therapy") if isinstance(desc.get("Therapy"), dict) else {}
    sd = side_of(ch_name)
    if sd and isinstance(ther.get(sd), dict):
        f = ther[sd].get("FrequencyInHertz")
        try:
            f = float(f)
            if f > 0: return f
        except (TypeError, ValueError):
            pass
    return None

import collections
pd_by_start = collections.defaultdict(list)
for r in pd_recs:
    try: pd_by_start[round(float(r.get("StartTime")))].append(r)
    except: pass
def find_pd(ts, tol=10):
    b=round(float(ts))
    for d in range(-tol,tol+1):
        if b+d in pd_by_start: return pd_by_start[b+d]
    return []

# ─────────────────────────────────────────────────────────────────────────────
# Block-level pairing
# ─────────────────────────────────────────────────────────────────────────────
rows = []
for td in td_recs:
    try: ts = float(td.get("StartTime"))
    except: continue
    pds = find_pd(ts)
    if not pds: continue
    td_chans = list(td.get("ChannelNames") or [])
    td_data  = np.asarray(td.get("Data"), float)
    if td_data.ndim != 2: continue

    for pd_rec in pds:
        pd_data  = np.asarray(pd_rec.get("Data"), float)
        pd_chans = list(pd_rec.get("ChannelNames") or [])
        if pd_data.ndim != 2: continue
        for ci, ch in enumerate(td_chans):
            if ci >= td_data.shape[1]: continue
            chU = ch.upper()
            # per-block sensing center for THIS channel's side
            ctr = block_center(pd_rec, ch)
            if ctr is None or not np.isfinite(ctr) or ctr <= 0: continue
            pcol=scol=None
            for pi,nm in enumerate(pd_chans):
                u=str(nm).upper()
                if chU in u and "POWER" in u: pcol=pi
                if chU in u and "STIM"  in u: scol=pi
            if pcol is None or pcol>=pd_data.shape[1]: continue
            lsb = pd_data[:,pcol]
            mA  = pd_data[:,scol] if (scol is not None and scol<pd_data.shape[1]) else np.zeros(len(lsb))
            off = (mA < STIM_OFF_MA) & np.isfinite(lsb) & (lsb>0)
            if off.sum() < 3: continue
            target_lsb = float(np.median(lsb[off]))

            # TD is ALREADY in µV (verified: amplitudes ~±60 µV) — no ADC conversion
            td_uv = td_data[:,ci]
            t_uv2 = transform_uv2_block(td_uv, ctr)
            w_uv2 = welch256_uv2_block(td_uv, ctr)
            if t_uv2 is None or t_uv2<=0: continue
            rows.append(dict(channel=ch, center_hz=round(ctr,2), session=round(ts),
                             target_lsb=target_lsb,
                             transform_uv2=t_uv2, welch256_uv2=w_uv2))

print(f"Paired blocks: {len(rows)}")
if not rows: raise SystemExit("no pairs")

# ─────────────────────────────────────────────────────────────────────────────
# Fit global scale k = median(target/uv2)  (repo fitted_scale) + block-CV k
# ─────────────────────────────────────────────────────────────────────────────
def med_ratio(rs, key):
    r=[x["target_lsb"]/x[key] for x in rs if x.get(key) and x[key]>0]
    return float(np.median(r)) if r else None

def metrics(rs, pred_key):
    yT=np.array([x["target_lsb"] for x in rs if x.get(pred_key) is not None])
    yP=np.array([x[pred_key]      for x in rs if x.get(pred_key) is not None])
    if len(yT)<3: return None
    r = float(np.corrcoef(yT,yP)[0,1])
    rmse = float(np.sqrt(np.mean((yP-yT)**2)))
    fold = np.exp(np.abs(np.log(yP/yT))); medfold=float(np.median(fold))
    return dict(n=len(yT), r=round(r,4), rmse=round(rmse,1), median_fold=round(medfold,3))

# transform + fitted k (all-data)
k_tr = med_ratio(rows, "transform_uv2")
for x in rows: x["transform_fit"] = x["transform_uv2"]*k_tr if x.get("transform_uv2") else None
# welch256 + fixed 269 and + fitted k
k_w  = med_ratio(rows, "welch256_uv2")
for x in rows:
    x["welch256_269"] = x["welch256_uv2"]*269.0 if x.get("welch256_uv2") else None
    x["welch256_fit"] = x["welch256_uv2"]*k_w    if (x.get("welch256_uv2") and k_w) else None

# block-held-out 5-fold CV for the transform (group by session)
sessions = sorted({x["session"] for x in rows})
g2f = {s:i%5 for i,s in enumerate(sessions)}
for x in rows:
    tr=[y for y in rows if g2f[y["session"]]!=g2f[x["session"]]]
    kcv=med_ratio(tr,"transform_uv2")
    x["transform_cv"]= x["transform_uv2"]*kcv if (kcv and x.get("transform_uv2")) else None

print(f"\nfitted k (transform)   = {k_tr:.1f}   (repo HANDOFF: 352.6)")
print(f"fitted k (welch256)    = {k_w:.1f}   (repo HANDOFF: 270.2)")
print(f"\n{'Method':<34}{'n':>5}{'r':>8}{'RMSE(LSB)':>11}{'medfold':>9}")
print("-"*67)
for label,key in [("transform + fitted k","transform_fit"),
                  ("transform + block-CV k","transform_cv"),
                  ("welch256 x fixed 269","welch256_269"),
                  ("welch256 + fitted k","welch256_fit")]:
    m=metrics(rows,key)
    if m: print(f"{label:<34}{m['n']:>5}{m['r']:>8.3f}{m['rmse']:>11.1f}{m['median_fold']:>9.3f}")

# Save
OUT="/usr/src/BRAVO/_agent_bridge/transform_repro_rows.csv"
keys=["channel","center_hz","session","target_lsb","transform_uv2","welch256_uv2",
      "transform_fit","transform_cv","welch256_269","welch256_fit"]
with open(OUT,"w",newline="") as f:
    w=csv.DictWriter(f, fieldnames=keys); w.writeheader()
    for x in rows: w.writerow({k:x.get(k) for k in keys})
print(f"\nSaved {OUT}")
summ=dict(n_blocks=len(rows), k_transform=k_tr, k_welch256=k_w,
          metrics={lab:metrics(rows,key) for lab,key in
                   [("transform_fit","transform_fit"),("transform_cv","transform_cv"),
                    ("welch256_269","welch256_269"),("welch256_fit","welch256_fit")]})
with open("/usr/src/BRAVO/_agent_bridge/transform_repro_summary.json","w") as f:
    json.dump(summ,f,indent=2,default=float)
print("Saved transform_repro_summary.json")
