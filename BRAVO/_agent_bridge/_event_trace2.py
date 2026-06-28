import os, sys, json, inspect, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
# the montage-PSD-events loader the timeline uses (the green ticks the user means)
for fn in ["_load_montage_psd_events","_load_patient_events"]:
    try:
        ev=getattr(bs,fn)(UID)
        print(f"{fn}: type={type(ev).__name__} len={len(ev) if hasattr(ev,'__len__') else '-'}")
        if isinstance(ev,list) and ev:
            print("  entry[0] keys:", list(ev[0].keys())[:18])
            e=ev[0]
            for fld in ["FFTBinData","LFPFrequency","LFPMagnitude","EventName","SenseID","NeuralActivity","StartTime","Channel"]:
                if fld in e:
                    v=e[fld]
                    if isinstance(v,(list,np.ndarray)):
                        a=np.asarray(v); print(f"    {fld}: shape={a.shape} min={np.nanmin(a):.3g} max={np.nanmax(a):.3g}")
                    else: print(f"    {fld}: {str(v)[:60]}")
    except Exception as ex:
        print(f"{fn}: ERR {ex!r}")
# show the montage_psd_events loader body (where the FFTBinData snapshot is read)
print("\n=== _load_montage_psd_events source (first 40 lines) ===")
try:
    src=inspect.getsource(bs._load_montage_psd_events).splitlines()
    for l in src[:40]: print(l[:120])
except Exception as ex: print("ERR",ex)
