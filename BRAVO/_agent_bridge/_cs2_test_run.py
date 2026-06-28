import os, sys, importlib, traceback
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
import importlib
# reload edited modules
from Biomarkers import bravo_service as bs; importlib.reload(bs)
from Biomarkers.routines import availability as av; importlib.reload(av)

import modules.Biomarkers.tests.test_event_psd_taxonomy as t1
import modules.Biomarkers.tests.test_availability as t2
importlib.reload(t1); importlib.reload(t2)

tests = []
for mod in (t1, t2):
    for nm in dir(mod):
        if nm.startswith("test_") and ("event" in nm or "categor" in nm or "taxonomy" in nm or "streaming" in nm):
            tests.append((mod.__name__, nm, getattr(mod, nm)))
npass=nfail=0
for modn, nm, fn in tests:
    try:
        fn(); npass+=1; print(f"PASS {modn}.{nm}")
    except Exception as e:
        nfail+=1; print(f"FAIL {modn}.{nm}: {e}"); traceback.print_exc()
print(f"\n=== {npass} passed, {nfail} failed ===")
