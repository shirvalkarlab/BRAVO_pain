import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import analytics
import statsmodels.api as sm
from statsmodels.stats.stattools import jarque_bera
UID="2e3c75c00d7f4f37b53a048d195f11da"
def td_chan_to_contact(ch):
    s=str(ch); h="RIGHT" if "RIGHT" in s else "LEFT"
    for pair in ("ZERO_AND_THREE","ONE_AND_THREE","ZERO_AND_TWO","ONE_AND_TWO","ZERO_AND_ONE","TWO_AND_THREE"):
        if pair in s: return pair,h
    return None,h
def psd_contact(e):
    h="RIGHT" if "Right" in str(e.get("Hemisphere")) else "LEFT"
    return str(e.get("SensingElectrodes")).split(".")[-1], h
surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
CENTERS=np.arange(5.0,46.0,5.0); HALF=2.5
def lfpmag_bandpower(lf,lm,c):
    band=(lf>=c-HALF)&(lf<c+HALF); v=lm[band]; v=v[v>0]
    return float(np.sum(v**2)) if v.size else np.nan
rows=[]
for s in surveys:
    D=s.get("Data"); fs=s.get("SamplingRate"); chans=s.get("ChannelNames"); desc=s.get("Descriptor")
    if not (isinstance(D,np.ndarray) and D.ndim==2 and isinstance(chans,list) and isinstance(desc,dict)): continue
    psdmap={}
    for e in (desc.get("MedtronicPSD") or []):
        if not isinstance(e,dict): continue
        lf=np.asarray(e.get("LFPFrequency",[]),float); lm=np.asarray(e.get("LFPMagnitude",[]),float)
        if lf.size==100 and lm.size==100: psdmap[psd_contact(e)]=(lf,lm)
    for ci,ch in enumerate(chans):
        key=td_chan_to_contact(ch)
        if key not in psdmap: continue
        col=np.asarray(D[:,ci],float)
        if col.size<int(fs): continue
        lf,lm=psdmap[key]
        for c in CENTERS:
            tdbp=analytics.td_transform_band_power(col,fs,float(c),half_hz=HALF); pbp=lfpmag_bandpower(lf,lm,c)
            if np.isfinite(tdbp) and np.isfinite(pbp) and tdbp>0 and pbp>0:
                rows.append((key[0]+"_"+key[1],float(c),float(tdbp),float(pbp)))
td=np.array([r[2] for r in rows]); psd=np.array([r[3] for r in rows])
lx=np.log(td); ly=np.log(psd)
# slope-1-constrained: PSD_bp = K * TD_bp  -> K = geometric mean of (psd/td)
logK=np.mean(ly-lx); K=np.exp(logK); sd=np.std(ly-lx)
print(f"slope-1-constrained law: PSD_bp = {K:.4f} * TD_bp   (log sd={sd:.3f} -> fold {np.exp(sd):.3f}x)")
# this K is the device-PSD/Welch offset. In dB: 
print(f"  offset in dB: {10*np.log10(K):.2f} dB  (code note said ~6 dB)")
# residual normality of slope-1 model
resid=ly-lx-logK; jb=jarque_bera(resid); print(f"  slope-1 resid JB p={jb[1]:.3g}  median|resid|={np.median(np.abs(resid)):.3f}")
# per-contact K stability
import collections
byc=collections.defaultdict(list)
for r in rows: byc[r[0]].append(np.log(r[3])-np.log(r[2]))
print("per-contact slope-1 K (geom mean psd/td):")
for c in sorted(byc):
    v=np.array(byc[c]); print(f"  {c:18s} n={v.size:4d} K={np.exp(np.mean(v)):.3f} fold={np.exp(np.std(v)):.3f}")
