import os, sys, importlib, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
# find the across-frequency scan entry point
fns=[f for f in dir(bs) if "scan" in f.lower() or "spectral" in f.lower() or "feature_importance" in f.lower()]
print("scan-ish fns:", fns)
