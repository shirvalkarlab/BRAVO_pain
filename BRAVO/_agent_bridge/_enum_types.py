import os, sys, json, collections, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
import Database as DB
UID="2e3c75c00d7f4f37b53a048d195f11da"
# Enumerate EVERY recording type actually stored for this participant (no guessing)
try:
    allrecs = bs._load_recordings(UID, None)  # None -> all types?
    print("ALL types via None:", len(allrecs) if allrecs else 0)
except Exception as e:
    print("None-load failed:", repr(e)[:120])
# Direct DB enumeration
try:
    recs = DB.getRecordingsList(UID) if hasattr(DB,"getRecordingsList") else None
    print("DB.getRecordingsList:", type(recs))
except Exception as e:
    print("getRecordingsList err:", repr(e)[:120])
# what loader functions exist?
print("\nbs functions w/ 'load' or 'event' or 'snapshot':")
print([f for f in dir(bs) if any(k in f.lower() for k in ("load","event","snapshot","montage","psd"))])
