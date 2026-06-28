import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import analytics
UID="2e3c75c00d7f4f37b53a048d195f11da"
def td_chan_to_contact(ch):
    s=str(ch); h="RIGHT" if "RIGHT" in s else "LEFT"
    for pair in ("ZERO_AND_THREE","ONE_AND_THREE","ZERO_AND_TWO","ONE_AND_TWO","ZERO_AND_ONE","TWO_AND_THREE"):
        if pair in s: return pair,h
    return None,h
def psd_contact(e):
    return str(e.get("SensingElectrodes")).split(".")[-1], ("RIGHT" if "Right" in str(e.get("Hemisphere")) else "LEFT")
surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"]); CENTERS=np.arange(5.0,46.0,5.0); HALF=2.5
def lfpmag_bp(lf,lm,c):
    band=(lf>=c-HALF)&(lf<c+HALF); v=lm[band]; v=v[v>0]; return float(np.sum(v**2)) if v.size else np.nan
logratios=[]
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
            tdbp=analytics.td_transform_band_power(col,fs,float(c),half_hz=HALF); pbp=lfpmag_bp(lf,lm,c)
            if np.isfinite(tdbp) and np.isfinite(pbp) and tdbp>0 and pbp>0:
                logratios.append(np.log(pbp)-np.log(tdbp))
lr=np.array(logratios)
K=np.exp(np.median(lr)); Kgm=np.exp(np.mean(lr))
print(f"K_TD_PSD: median={K:.4f}  geomean={Kgm:.4f}  n={lr.size}")
print(f"K_PSD_LSB (=352.62/K): median-based={352.62/K:.4f}  geomean-based={352.62/Kgm:.4f}")
# bootstrap CI on geomean K
rng=np.random.default_rng(0); bs_=[np.exp(np.mean(rng.choice(lr,lr.size))) for _ in range(2000)]
lo,hi=np.percentile(bs_,[2.5,97.5]); print(f"K_TD_PSD geomean 95%CI=[{lo:.3f},{hi:.3f}] -> K_PSD_LSB=[{352.62/hi:.2f},{352.62/lo:.2f}]")
