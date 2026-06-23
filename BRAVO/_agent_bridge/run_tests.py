import os, sys, importlib, traceback, glob
sys.path.insert(0, "/usr/src/BRAVO")
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
import django; django.setup()
import importlib
# reload analytics to pick up edit
from modules.Biomarkers.routines import analytics
importlib.reload(analytics)
base="/usr/src/BRAVO/modules/Biomarkers/tests"
files=sorted(glob.glob(base+"/test_*.py"))
npass=nfail=0; fails=[]
for f in files:
    mod="modules.Biomarkers.tests."+os.path.basename(f)[:-3]
    try:
        m=importlib.import_module(mod); importlib.reload(m)
    except Exception as e:
        fails.append((mod,"IMPORT",repr(e))); nfail+=1; continue
    for nm in dir(m):
        if nm.startswith("test_") and callable(getattr(m,nm)):
            try:
                getattr(m,nm)(); npass+=1
            except Exception as e:
                nfail+=1; fails.append((mod,nm,repr(e)[:200]))
print(f"PASS={npass} FAIL={nfail}")
for mod,nm,e in fails[:20]: print("  FAIL",mod.split('.')[-1],nm,e)
