import os, sys, inspect, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"

# What functions build per-lane PSD ticks / availability strips (NOT the events diamonds)?
print("=== bs funcs that build psd rows / availability ticks ===")
print([f for f in dir(bs) if any(k in f.lower() for k in ("psd_row","assemble_psd","psd_index","psd_sample","present_freq","availab"))])

# _assemble_psd_rows / _load_recording_psd_rows -- which recording TYPES do they pull?
for fn in ["_assemble_psd_rows","_recording_rows_for_psd","_load_recording_psd_rows","_event_psd_rows"]:
    try:
        src=inspect.getsource(getattr(bs,fn))
        types=[l.strip() for l in src.splitlines() if "_load_recordings" in l or "type" in l.lower() and ("Snapshot" in l or "Event" in l or "Montage" in l or "Survey" in l or "[" in l)]
        print(f"\n--- {fn}: recording-type references ---")
        for t in types[:8]: print("  ",t[:110])
    except Exception as e:
        print(fn,"->",repr(e)[:80])

# AVAILABILITY_PSD_TYPES and any EVENT psd source feeding the strip
print("\nAVAILABILITY_PSD_TYPES =", bs.AVAILABILITY_PSD_TYPES)
print("EVENT_PSD_SOURCE =", bs.EVENT_PSD_SOURCE)
# Does _assemble_psd_rows include NeuralActivitySnapshot or streaming PCE?
try:
    src=inspect.getsource(bs._assemble_psd_rows)
    for kw in ["NeuralActivitySnapshot","PatientControllerEvent","Streaming","_load_patient_events","_load_montage_psd_events","EVENT_PSD","AVAILABILITY_PSD_TYPES"]:
        if kw in src: print(f"  _assemble_psd_rows references: {kw}")
except Exception as e: print("assemble src err",e)
