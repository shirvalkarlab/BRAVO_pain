import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
def td_check(t):
    recs=bs._load_recordings(UID,[t])
    if not recs: return f"{t}: 0 recs"
    e=recs[0]; keys=list(e.keys())
    d=e.get("Data")
    has_td = isinstance(d,np.ndarray) and d.ndim==2 and d.size>0
    sr=e.get("SamplingRate")
    return f"{t}: n={len(recs)}  Data_TD={has_td}  SR={sr}  keys={keys[:10]}"
for t in ["MedtronicBrainSenseSurvey","NeuralActivitySnapshot","MedtronicBaselineMontages","MedtronicStimulationMontages"]:
    print(td_check(t))
# patient events: PSD-only, no TD (confirm)
pe=bs._load_patient_events(UID)
print(f"\npatient events: n={len(pe)} keys={list(pe[0].keys())}  (no 'Data'/TD -> PSD only: {'Data' not in pe[0]})")
