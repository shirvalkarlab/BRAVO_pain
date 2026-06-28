import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
import importlib
from Biomarkers import bravo_service as bs; importlib.reload(bs)
from Biomarkers.routines import availability as av; importlib.reload(av)
UID="2e3c75c00d7f4f37b53a048d195f11da"
pe=bs._load_patient_events(UID)
from collections import Counter
print("total patient events now surfaced:", len(pe))
print("by category:", Counter(e['category'] for e in pe).most_common())
print("by name (top):", Counter(e['name'] for e in pe).most_common(5))
mk=av.event_markers(pe)
print("markers n:", mk['n'], "| categories:", mk.get('categories'))
print("sample streaming marker keys:", [e for e in mk['events'] if e['category']=='Streaming event PSD'][:1])
