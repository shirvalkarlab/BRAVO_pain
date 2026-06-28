"""
3-SECOND DSP HYBRID of the percept-spectral-repro transform.

Difference from the repo's transform:
  repo:   1-second unit = 250 nonzero samples -> zero-pad to 256 -> RC+S-Hann FFT -> band power,
          then MEDIAN over all 1-s windows in the block.
  hybrid: 3-second unit = 750 samples = three consecutive 250-sample sub-windows, each
          zero-padded to 256 and run through the SAME RC+S-Hann/peak-scale DSP, band powers
          AVERAGED -> one 3-s band power. This mirrors the device's AveragingDurationInMilliSeconds
          = 3000 (its LSB IS a 3-s average), so TD and LSB are both 3-s averages == apples-to-apples.

Slid across every paired TD-streaming block (step = 1 s, window = 3 s). Each 3-s TD window is
matched to the CONCURRENT stim-off device LSB (PowerDomain samples whose offset falls in the
window). Then the single transform scale k = median(LSB / uV^2) is fit, two flavors:

  FLAVOR A (per-window):  every 3-s window is its own calibration point. Fit k over all windows,
                          metrics over all windows. Tests within-block concurrent tracking.
  FLAVOR B (block-median): collapse each block to median uV^2 & median LSB (repo style), fit k,
                          metrics over blocks.
"""
import os, sys, json, csv
import numpy as np

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
sys.path.insert(0, "/usr/src/BRAVO")
import django; django.setup()
from modules.Biomarkers import bravo_service as bs
from modules.Biomarkers.routines import availability as av, analytics as an

UID="2e3c75c00d7f4f37b53a048d195f11da"
WIDTH_HZ=5.0; STIM_OFF_MA=0.1; SR=250.0
N_FFT=256; NONZERO=250; MAXF=96.68
WIN_SEC=3.0; WIN_SAMP=750; STEP_SAMP=250          # 3-s window, 1-s sliding step
SUB=250                                            # sub-window length

# ── verbatim repo DSP ────────────────────────────────────────────────────────
def percept_frequency_bins(sr=SR, n_fft=N_FFT, maxf=MAXF):
    bins=np.round(np.arange(n_fft//2+1)*sr/n_fft,2); return bins[bins<=maxf+1e-9]
def _rcs_hann(nonzero,n_fft):
    c=np.zeros(n_fft); n=np.arange(nonzero); c[:nonzero]=0.5*(1-np.cos(2*np.pi*n/nonzero)); return c
_COEFFS=_rcs_hann(NONZERO,N_FFT); _FREQS=percept_frequency_bins()
def survey_spectrum_one_window(win):
    w=np.asarray(win,float); w=w-np.nanmean(w)
    p=np.zeros(N_FFT); p[:len(w)]=w[:NONZERO]
    mag=np.abs(np.fft.rfft(p*_COEFFS,n=N_FFT)); mag=2.0*mag/N_FFT
    return mag[:len(_FREQS)]
def band_power_uv2(mags,center_hz,width=WIDTH_HZ):
    half=width/2.0; m=(_FREQS>=center_hz-half)&(_FREQS<=center_hz+half)
    return float(np.sum(mags[m]**2))

def transform_uv2_3s(win750, center_hz):
    """3-s band power = MEAN of three 250-sample sub-window band powers (device 3-s averaging)."""
    v=np.asarray(win750,float); v=v[np.isfinite(v)]
    if v.size < SUB: return None
    subs=[v[k:k+SUB] for k in range(0, v.size-SUB+1, SUB)]   # up to 3 non-overlap sub-windows
    bps=[band_power_uv2(survey_spectrum_one_window(s),center_hz) for s in subs]
    bps=[b for b in bps if np.isfinite(b)]
    return float(np.mean(bps)) if bps else None

# ── load + pair blocks ───────────────────────────────────────────────────────
td_recs=bs._load_recordings(UID,["MedtronicBrainSenseTimeDomain"])
pd_recs=bs._load_recordings(UID,["MedtronicBrainSensePowerDomain"])
print(f"TD:{len(td_recs)}  PD:{len(pd_recs)}")

def side_of(n):
    u=str(n).upper()
    return "Left" if "LEFT" in u else ("Right" if "RIGHT" in u else None)
def block_center(pd_rec,ch):
    d=pd_rec.get("Descriptor") if isinstance(pd_rec.get("Descriptor"),dict) else {}
    t=d.get("Therapy") if isinstance(d.get("Therapy"),dict) else {}
    sd=side_of(ch)
    if sd and isinstance(t.get(sd),dict):
        try:
            f=float(t[sd].get("FrequencyInHertz"))
            if f>0: return f
        except (TypeError,ValueError): pass
    return None

import collections
pd_by_start=collections.defaultdict(list)
for r in pd_recs:
    try: pd_by_start[round(float(r.get("StartTime")))].append(r)
    except: pass
def find_pd(ts,tol=10):
    b=round(float(ts))
    for d in range(-tol,tol+1):
        if b+d in pd_by_start: return pd_by_start[b+d]
    return []

# ── sliding 3-s windows, concurrent LSB match ────────────────────────────────
win_rows=[]   # per-window
probe_pd_rate=None
for td in td_recs:
    try: ts=float(td.get("StartTime"))
    except: continue
    pds=find_pd(ts)
    if not pds: continue
    td_chans=list(td.get("ChannelNames") or [])
    td_data=np.asarray(td.get("Data"),float)
    if td_data.ndim!=2: continue
    td_rate=float(td.get("SamplingRate") or SR)

    for pd_rec in pds:
        pd_data=np.asarray(pd_rec.get("Data"),float)
        pd_chans=list(pd_rec.get("ChannelNames") or [])
        if pd_data.ndim!=2: continue
        pd_rate=float(pd_rec.get("SamplingRate") or 2.0)
        if probe_pd_rate is None: probe_pd_rate=pd_rate
        n_pd=pd_data.shape[0]
        pd_offsets=np.arange(n_pd)/pd_rate    # seconds from PD start (== TD start, concurrent)

        for ci,ch in enumerate(td_chans):
            if ci>=td_data.shape[1]: continue
            chU=ch.upper()
            ctr=block_center(pd_rec,ch)
            if ctr is None or not np.isfinite(ctr) or ctr<=0: continue
            pcol=scol=None
            for pi,nm in enumerate(pd_chans):
                u=str(nm).upper()
                if chU in u and "POWER" in u: pcol=pi
                if chU in u and "STIM"  in u: scol=pi
            if pcol is None or pcol>=pd_data.shape[1]: continue
            lsb=pd_data[:,pcol]
            mA =pd_data[:,scol] if (scol is not None and scol<pd_data.shape[1]) else np.zeros(n_pd)
            lsb_ok=np.isfinite(lsb)&(lsb>0)&(lsb<1e6)&(mA<STIM_OFF_MA)   # stim-off, valid, no sentinel

            td_uv=td_data[:,ci]   # already µV
            nsamp=td_uv.size
            for start in range(0, nsamp-WIN_SAMP+1, STEP_SAMP):
                ws=start/td_rate; we=(start+WIN_SAMP)/td_rate
                uv2=transform_uv2_3s(td_uv[start:start+WIN_SAMP], ctr)
                if uv2 is None or uv2<=0: continue
                inwin=lsb_ok & (pd_offsets>=ws) & (pd_offsets<we)
                if inwin.sum()<1: continue
                win_lsb=float(np.median(lsb[inwin]))
                win_rows.append(dict(channel=ch, center_hz=round(ctr,2), session=round(ts),
                                     win_start_s=round(ws,2), n_lsb=int(inwin.sum()),
                                     uv2=uv2, lsb=win_lsb))

print(f"pd_rate={probe_pd_rate} Hz   3-s windows with concurrent LSB: {len(win_rows)}")
if not win_rows: raise SystemExit("no windows")

# ── metrics helpers ──────────────────────────────────────────────────────────
def med_ratio(uv2,lsb):
    r=lsb/uv2; r=r[np.isfinite(r)&(r>0)]; return float(np.median(r)) if len(r) else None
def metrics(yT,yP):
    m=np.isfinite(yT)&np.isfinite(yP)&(yT>0)&(yP>0); yT,yP=yT[m],yP[m]
    if len(yT)<3: return None
    return dict(n=int(len(yT)),
                r=round(float(np.corrcoef(yT,yP)[0,1]),3),
                r_log=round(float(np.corrcoef(np.log(yT),np.log(yP))[0,1]),3),
                rmse=round(float(np.sqrt(np.mean((yP-yT)**2))),1),
                median_fold=round(float(np.median(np.exp(np.abs(np.log(yP/yT))))),3))

uv2=np.array([r["uv2"] for r in win_rows]); lsb=np.array([r["lsb"] for r in win_rows])
sess=np.array([r["session"] for r in win_rows])

# FLAVOR A: per-window, fit k over all windows; also session-held-out CV
kA=med_ratio(uv2,lsb)
predA=uv2*kA
# 5-fold CV by session
usess=sorted(set(sess.tolist())); g2f={s:i%5 for i,s in enumerate(usess)}
foldid=np.array([g2f[s] for s in sess]); predA_cv=np.full(len(uv2),np.nan)
for f in range(5):
    tr=foldid!=f; kcv=med_ratio(uv2[tr],lsb[tr])
    predA_cv[foldid==f]=uv2[foldid==f]*kcv
mA_fit=metrics(lsb,predA); mA_cv=metrics(lsb,predA_cv)

# FLAVOR B: block-median (per channel|center|session), repo style
from collections import defaultdict
agg=defaultdict(lambda: ([], []))
for r in win_rows:
    key=(r["channel"],r["center_hz"],r["session"]); agg[key][0].append(r["uv2"]); agg[key][1].append(r["lsb"])
buv2=np.array([np.median(v[0]) for v in agg.values()])
blsb=np.array([np.median(v[1]) for v in agg.values()])
kB=med_ratio(buv2,blsb); predB=buv2*kB
mB_fit=metrics(blsb,predB)

print(f"\nFLAVOR A (per-window)   k = {kA:.1f}   n_windows = {len(uv2)}")
print(f"FLAVOR B (block-median) k = {kB:.1f}   n_blocks  = {len(buv2)}")
print(f"\n{'Flavor':<34}{'n':>7}{'r':>7}{'r_log':>7}{'RMSE':>9}{'medfold':>9}")
print("-"*73)
for lab,m in [("A: per-window + fitted k",mA_fit),
              ("A: per-window + session-CV k",mA_cv),
              ("B: block-median + fitted k",mB_fit)]:
    if m: print(f"{lab:<34}{m['n']:>7}{m['r']:>7.3f}{m['r_log']:>7.3f}{m['rmse']:>9.1f}{m['median_fold']:>9.3f}")

# ── save ─────────────────────────────────────────────────────────────────────
OUT="/usr/src/BRAVO/_agent_bridge/transform_3s_windows.csv"
with open(OUT,"w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["channel","center_hz","session","win_start_s","n_lsb","uv2","lsb"])
    w.writeheader()
    for r in win_rows: w.writerow(r)
print(f"\nSaved {OUT}")
summ=dict(dsp="3-s window = mean of 3x(250-samp/256-FFT/RC+S-Hann/peak) band powers",
          window_sec=WIN_SEC, step_samp=STEP_SAMP, pd_rate_hz=probe_pd_rate,
          n_windows=len(uv2), n_blocks=len(buv2),
          k_flavorA_per_window=kA, k_flavorB_block_median=kB,
          metrics=dict(A_per_window_fit=mA_fit, A_per_window_cv=mA_cv, B_block_median_fit=mB_fit))
with open("/usr/src/BRAVO/_agent_bridge/transform_3s_summary.json","w") as f:
    json.dump(summ,f,indent=2,default=float)
print("Saved transform_3s_summary.json")
