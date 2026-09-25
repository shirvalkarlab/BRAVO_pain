import os, sys, importlib, traceback, glob
# THE `live` MARK (2026-09-12). A test function carrying `@pytest.mark.live` reads the live RCS08
# record; pytest stores that mark on the function as `pytestmark`, and this runner reads the same
# attribute so the two runners agree on which tests are live without pytest running anything here.
# Routine run: every live test is skipped and counted in LIVE_SKIPPED. `--live`: ONLY the live
# tests run. The daily pass (`stability_precompute_loop.sh`) is what runs them with `--live`.
LIVE_ONLY = "--live" in sys.argv[1:]

def _is_live(fn):
    return any(getattr(m, "name", None) == "live" for m in getattr(fn, "pytestmark", []) or [])

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
# there was no pytest in this container when it was written (pytest has been installed since
# decision 84, 2026-09-09, for the host suite; this runner still calls the functions itself). That
# works only for test files written against plain `assert`.
#
#   Biomarkers  — 22 files on 2026-09-07, none of which import pytest. Runs here.
#   CacheStore  — the one cache store, the provenance chain and the ledger. Written pytest-free on
#                 purpose so the cycle-refusal proof runs in the SAME container as the code it
#                 protects, rather than only on the analysis host.
#   DecodeCommon — the canonical decoded form (Track B). Its tests take no arguments on purpose
#                 so they run here, where the recordings are, as well as under pytest on the host.
#
# ClosedLoopDeployment (11 files) and StimOptimizer (20 files, on 2026-09-07) are deliberately NOT run here:
# every one of them uses pytest fixtures or `pytest.raises`, so importing them in this container
# raises ImportError and would report one spurious failure per file. Those two suites run on the host:
#
#   cd BRAVO/modules && PYTHONPATH=. python -B -m pytest \
#       ClosedLoopDeployment/tests StimOptimizer/tests -q -W ignore
#
# So a green run here is NOT a green run of the whole platform. Report both counts, each from its
# own command, and never carry either number from a document.
PACKAGES = ["Biomarkers", "CacheStore", "DecodeCommon", "ControlAnalyses"]

files=[]
for _pkg in PACKAGES:
    _base = f"/usr/src/BRAVO/modules/{_pkg}/tests"
    files += [(_pkg, p) for p in sorted(glob.glob(_base+"/test_*.py"))]
npass=nfail=nlive_skipped=0; fails=[]
for pkg, f in files:
    mod=f"modules.{pkg}.tests."+os.path.basename(f)[:-3]
    try:
        m=importlib.import_module(mod); importlib.reload(m)
    except Exception as e:
        fails.append((mod,"IMPORT",repr(e))); nfail+=1; continue
    for nm in dir(m):
        if nm.startswith("test_") and callable(getattr(m,nm)):
            if _is_live(getattr(m, nm)) != LIVE_ONLY:
                if not LIVE_ONLY:
                    nlive_skipped += 1
                continue
            try:
                getattr(m,nm)(); npass+=1
            except Exception as e:
                nfail+=1; fails.append((mod,nm,repr(e)[:200]))
print(f"PASS={npass} FAIL={nfail}" + (" (live tests only)" if LIVE_ONLY else f" LIVE_SKIPPED={nlive_skipped}"))
for mod,nm,e in fails[:20]: print("  FAIL",mod.split('.')[-1],nm,e)
