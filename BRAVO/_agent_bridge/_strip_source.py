import os, sys, inspect, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
# Full source of the strip builders, to see EXACTLY which types feed the per-lane PSD ticks
for fn in ["_recording_rows_for_psd","_assemble_psd_rows","_event_psd_rows","_event_psd_index"]:
    try:
        src=inspect.getsource(getattr(bs,fn))
        print(f"\n===== {fn} ({len(src.splitlines())} lines) =====")
        for l in src.splitlines():
            s=l.strip()
            if any(k in s for k in ("_load_recordings","_load_patient_events","_load_montage_psd_events",
                                    "NeuralActivitySnapshot","PatientControllerEvent","AVAILABILITY_PSD_TYPES",
                                    "EVENT_PSD","name","type=","def ")):
                print("  |",l[:120])
    except Exception as e:
        print(fn,"ERR",repr(e)[:80])
