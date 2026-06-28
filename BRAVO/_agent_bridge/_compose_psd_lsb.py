import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import analytics
import statsmodels.api as sm
UID="2e3c75c00d7f4f37b53a048d195f11da"
K_TD_LSB = analytics.LSB_PER_UV2_TRANSFORM  # 352.62
K_TD_PSD = 4.79
K_PSD_LSB = K_TD_LSB / K_TD_PSD
print(f"K_TD_LSB={K_TD_LSB:.2f}  K_TD_PSD={K_TD_PSD:.3f}  => K_PSD_LSB = {K_PSD_LSB:.3f}")

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
def lfpmag_bp(lf,lm,c):
    band=(lf>=c-HALF)&(lf<c+HALF); v=lm[band]; v=v[v>0]
    return float(np.sum(v**2)) if v.size else np.nan
# End-to-end: on montage, compute LSB two ways:
#  direct:   LSB_td  = K_TD_LSB * TD_bp
#  via-PSD:  LSB_psd = K_PSD_LSB * PSD_bp   (PSD_bp from device LFPMagnitude)
# Agreement => composition is correct.
ltd=[]; lpsd=[]
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
                ltd.append(K_TD_LSB*tdbp); lpsd.append(K_PSD_LSB*pbp)
ltd=np.array(ltd); lpsd=np.array(lpsd)
fold=lpsd/ltd
print(f"\nEnd-to-end LSB agreement (via-PSD vs direct-TD), n={ltd.size}:")
print(f"  median fold (LSB_psd/LSB_td)= {np.median(fold):.4f}  (==1 ideal)")
print(f"  geomean fold = {np.exp(np.mean(np.log(fold))):.4f}  scatter fold = {np.exp(np.std(np.log(fold))):.4f}")
print(f"  p10/p90 fold = {np.percentile(fold,10):.3f}/{np.percentile(fold,90):.3f}")
# correlation of the two LSB estimates (log)
r=np.corrcoef(np.log(ltd),np.log(lpsd))[0,1]; print(f"  log-LSB correlation r={r:.4f}")
