import os, sys, json, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
sur=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
# 1) does every survey carry raw TD alongside the PSD descriptor?
has_td=sum(1 for r in sur if isinstance(r.get("Data"),np.ndarray) and np.asarray(r["Data"]).size>0)
print("surveys:",len(sur),"| with raw TD Data:",has_td)
# 2) what's inside Descriptor.MedtronicPSD — peak only, or full magnitude spectrum?
e=sur[0]; mp=e["Descriptor"]["MedtronicPSD"]
print("\nMedtronicPSD: type",type(mp).__name__,"len",len(mp) if isinstance(mp,list) else "-")
if isinstance(mp,list) and mp:
    print("  entry[0] keys:", list(mp[0].keys()))
    for k,v in mp[0].items():
        if isinstance(v,(list,np.ndarray)):
            arr=np.asarray(v); print(f"    {k}: array shape={arr.shape} min={np.nanmin(arr):.3g} max={np.nanmax(arr):.3g}")
        else:
            print(f"    {k}: {v}")
# 3) chronic — native LSB only, no spectrum, no TD?
ch=bs._load_recordings(UID,["MedtronicChronicBrainSense"])
print("\nchronic recs:",len(ch),"| first keys:",list(ch[0].keys())[:12] if ch else None)
