import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
# Reproduce what the timeline actually surfaces today
pe = bs._load_patient_events(UID)          # patient events (streaming excluded)
mpe = bs._load_montage_psd_events(UID)     # "Montage PSD" markers (NeuralActivitySnapshot)
from collections import Counter
print("patient events surfaced:", len(pe), Counter(e['name'] for e in pe).most_common())
print("montage-psd events surfaced:", len(mpe), Counter(e['name'] for e in mpe).most_common())
# Are the NeuralActivitySnapshot times actually the STREAMING event times? overlap test
import numpy as np
nas=bs._load_recordings(UID,["NeuralActivitySnapshot"])
nas_t=sorted(float(bs.availability._to_epoch(s.get("StartTime"))) for s in nas if bs.availability._to_epoch(s.get("StartTime")))
# streaming PCE times
from Biomarkers.bravo_service import models, PATIENT_EVENT_TYPE
import datetime as dt
P=models.Participant.find(uid=UID); SF=models.SourceFile.find_all(owner=P)
strm=[r for r in models.Recording.find_all(source__in=SF,type=PATIENT_EVENT_TYPE) if (getattr(r,'name','') or '').strip().lower()=='streaming']
def et(r):
    md=getattr(r,'metadata',None)
    if isinstance(md,dict):
        for hb in md.values():
            if isinstance(hb,dict) and hb.get('DateTime'):
                try: return dt.datetime.fromisoformat(str(hb['DateTime']).replace('Z','+00:00')).timestamp()
                except: pass
    return None
strm_t=sorted([t for t in (et(r) for r in strm) if t])
print(f"\nNeuralActivitySnapshot n={len(nas_t)}  streaming-PCE n={len(strm_t)}")
# how many NAS times coincide (<=5s) with a streaming-PCE time?
import bisect
co=0
for t in nas_t:
    i=bisect.bisect_left(strm_t,t)
    for j in (i-1,i):
        if 0<=j<len(strm_t) and abs(strm_t[j]-t)<=5: co+=1; break
print(f"NAS times within 5s of a streaming-PCE time: {co}/{len(nas_t)}")
