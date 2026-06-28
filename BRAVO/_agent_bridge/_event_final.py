import os, sys, inspect, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
# counts of the two event families
nas=bs._load_recordings(UID,["NeuralActivitySnapshot"])
print("NeuralActivitySnapshot recs:", len(nas))
pe=bs._load_patient_events(UID)
mpe=bs._load_montage_psd_events(UID)
print("_load_patient_events:", len(pe), "| _load_montage_psd_events:", len(mpe))
# do patient events carry PSDs (the filled-diamond EVENTS lane w/ snapshots)?
withpsd=sum(1 for e in pe if e.get("psds"))
print("patient events WITH psds:", withpsd, "/", len(pe))
# inspect a patient-event PSD payload
for e in pe:
    if e.get("psds"):
        f,m=e["psds"][0]; f=np.asarray(f,float); m=np.asarray(m,float)
        print(f"  sample patient-event '{e['name']}': PSD bins={f.shape}, f[{f.min():.2f}..{f.max():.2f}], power[{np.nanmin(m):.3g}..{np.nanmax(m):.3g}]")
        break
# how is _load_patient_events built — does it read FFTBinData from BrainSenseEvent?
print("\n=== _load_patient_events source (first 45 lines) ===")
for l in inspect.getsource(bs._load_patient_events).splitlines()[:45]:
    print(l[:120])
