"""Inventory the device-PSD products available as a no-TD backup source for RCS08."""
import os, sys, json, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"

out={}
for t in ["MedtronicBrainSenseSurvey","MedtronicMontage","MedtronicLFPMontage",
          "MedtronicBrainSenseEvent","MedtronicBrainSenseTimeDomain",
          "MedtronicBrainSensePowerDomain","MedtronicChronicBrainSense"]:
    try:
        recs=bs._load_recordings(UID,[t])
        out[t]=len(recs)
    except Exception as e:
        out[t]=f"ERR {type(e).__name__}"
print("=== recording-type counts ===")
print(json.dumps(out, indent=2))

# what carries a usable PSD descriptor? probe survey + event
for t in ["MedtronicBrainSenseSurvey","MedtronicLFPMontage","MedtronicBrainSenseEvent"]:
    try:
        recs=bs._load_recordings(UID,[t])
    except Exception:
        recs=[]
    if not recs: 
        print(f"\n{t}: 0 recs"); continue
    e=recs[0]
    print(f"\n=== {t}: {len(recs)} recs; first-rec keys ===")
    print(" ", [k for k in e.keys()][:20])
    # look for PSD-bearing fields
    for fld in ["Descriptor","LFPMagnitude","LFPFrequency","FFTBinData","MedtronicPSD","Data","ChannelNames"]:
        if fld in e:
            v=e[fld]
            if isinstance(v,(list,np.ndarray)):
                arr=np.asarray(v) if not isinstance(v,dict) else None
                print(f"    {fld}: {type(v).__name__} shape/len={getattr(arr,'shape',len(v))}")
            elif isinstance(v,dict):
                print(f"    {fld}: dict keys={list(v.keys())[:8]}")
            else:
                print(f"    {fld}: {type(v).__name__}={v}")
