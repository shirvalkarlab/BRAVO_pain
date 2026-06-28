import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.bravo_service import models, PATIENT_EVENT_TYPE
UID="2e3c75c00d7f4f37b53a048d195f11da"
P=models.Participant.find(uid=UID); SF=models.SourceFile.find_all(owner=P)

def quantum(vals):
    u=np.unique(np.round(vals,5)); u=u[u>1e-6]
    if u.size<3: return None,u[:6]
    # smallest gap between consecutive small values approximates the quantum
    d=np.diff(np.sort(u))
    d=d[d>1e-6]
    return float(np.median(d[:30])), u[:6]

# survey LFPMagnitude pool
surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
lm_all=[]
for s in surveys:
    desc=s.get("Descriptor")
    if not isinstance(desc,dict): continue
    for e in (desc.get("MedtronicPSD") or []):
        if isinstance(e,dict):
            lm=np.asarray(e.get("LFPMagnitude",[]),float)
            if lm.size: lm_all.append(lm)
LM=np.concatenate(lm_all)
qlm,ulm=quantum(LM)
print(f"survey LFPMagnitude: n={LM.size} min={LM.min():.4f} max={LM.max():.4f} frac_neg={np.mean(LM<0):.3f}")
print(f"  smallest uniques: {np.round(ulm,5)}  est quantum={qlm:.5f}")

# event FFTBinData pool
fb_all=[]
for r in models.Recording.find_all(source__in=SF,type=PATIENT_EVENT_TYPE):
    md=getattr(r,'metadata',None)
    if not isinstance(md,dict): continue
    for hb in md.values():
        if isinstance(hb,dict):
            m=hb.get("FFTBinData")
            if isinstance(m,(list,tuple)) and len(m): fb_all.append(np.asarray(m,float))
FB=np.concatenate(fb_all)
qfb,ufb=quantum(FB)
print(f"event FFTBinData: n={FB.size} min={FB.min():.4f} max={FB.max():.4f} frac_neg={np.mean(FB<0):.3f}")
print(f"  smallest uniques: {np.round(ufb,5)}  est quantum={qfb:.5f}")
print(f"\nQUANTUM RATIO (FFTBin/LFPMag): {qfb/qlm:.4f}  (==1 => same unit)")

# Distribution match on POSITIVE values (negatives are the floor-handling difference):
# if same unit, the positive-tail percentiles should align closely.
for q in [50,75,90,95,99]:
    a=np.percentile(LM[LM>0],q); b=np.percentile(FB[FB>0],q)
    print(f"  p{q}: LFPMag={a:.4f}  FFTBin(>0)={b:.4f}  ratio={b/a:.3f}")
