import os, sys, json, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
print("EVENT_PSD_SOURCE   =", bs.EVENT_PSD_SOURCE)
print("AVAILABILITY_PSD_TYPES =", bs.AVAILABILITY_PSD_TYPES)
print("PATIENT_EVENT_TYPE =", bs.PATIENT_EVENT_TYPE)
# how many event PSDs exist & do they carry a real spectrum?
for t in ([bs.EVENT_PSD_SOURCE] if isinstance(bs.EVENT_PSD_SOURCE,str) else list(bs.EVENT_PSD_SOURCE)):
    try:
        recs=bs._load_recordings(UID,[t]); print(f"\n{t}: {len(recs)} recs")
        if recs:
            e=recs[0]; print("  keys:", list(e.keys())[:18])
            for fld in ["FFTBinData","LFPMagnitude","LFPFrequency","Data","Descriptor","SenseID","EventName","EventID"]:
                if fld in e:
                    v=e[fld]
                    if isinstance(v,(list,np.ndarray)):
                        a=np.asarray(v); print(f"    {fld}: shape={a.shape} min={np.nanmin(a):.3g} max={np.nanmax(a):.3g}")
                    elif isinstance(v,dict): print(f"    {fld}: dict {list(v.keys())[:6]}")
                    else: print(f"    {fld}: {v}")
    except Exception as ex:
        print(f"{t}: ERR {ex!r}")
# the event_psd_rows pipeline -> what conversion does it use?
import inspect
for fn in ["_event_psd_rows","_load_recording_psd_rows","band_psd_lsb_conversion"]:
    try:
        src=inspect.getsource(getattr(bs,fn))
        # show only lines that mention conversion / k / lsb / psd_band
        hits=[l for l in src.splitlines() if any(w in l for w in ("psd_band_to_lsb","lsb_from_uv2","td_to_lsb","k=269","352","band_psd_lsb","LSB"))][:6]
        print(f"\n--- {fn} conversion lines ---")
        for h in hits: print("  ", h.strip()[:110])
    except Exception as ex:
        print(fn,"ERR",repr(ex)[:80])
