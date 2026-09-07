import os, sys, importlib, traceback, glob
sys.path.insert(0, "/usr/src/BRAVO")
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
import django; django.setup()
import importlib
# reload analytics to pick up edit
from modules.Biomarkers.routines import analytics
importlib.reload(analytics)
# WHICH PACKAGES ARE RUN HERE, AND WHY NOT THE OTHER TWO.
#
# This runner imports each test module and calls every top-level `test_*` function itself, because
# there is no pytest in this container. That works only for test files written against plain
# `assert`.
#
#   Biomarkers  — 19 files, none of which import pytest. Runs here.
#   CacheStore  — the one cache store, the provenance chain and the ledger. Written pytest-free on
#                 purpose so the cycle-refusal proof runs in the SAME container as the code it
#                 protects, rather than only on the analysis host.
#
# ClosedLoopDeployment (10 files) and StimOptimizer (18 files) are deliberately NOT run here:
# every one of them uses pytest fixtures or `pytest.raises`, so importing them in this container
# raises ImportError and would report 28 spurious failures. Those two suites run on the host:
#
#   cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
#       ClosedLoopDeployment/tests StimOptimizer/tests -q -W ignore
#
# So a green run here is NOT a green run of the whole platform. Report both counts, each from its
# own command, and never carry either number from a document.
PACKAGES = ["Biomarkers", "CacheStore"]

files=[]
for _pkg in PACKAGES:
    _base = f"/usr/src/BRAVO/modules/{_pkg}/tests"
    files += [(_pkg, p) for p in sorted(glob.glob(_base+"/test_*.py"))]
npass=nfail=0; fails=[]
for pkg, f in files:
    mod=f"modules.{pkg}.tests."+os.path.basename(f)[:-3]
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
