import os, sys, importlib, traceback, glob
# THE `live` MARK (2026-09-12). A test function carrying `@pytest.mark.live` reads the live RCS08
# record; pytest stores that mark on the function as `pytestmark`, and this runner reads the same
# attribute so the two runners agree on which tests are live without pytest running anything here.
# Routine run: every live test is skipped and counted in LIVE_SKIPPED. `--live`: ONLY the live
# tests run. The daily pass (`stability_precompute_loop.sh`) is what runs them with `--live`.
LIVE_ONLY = "--live" in sys.argv[1:]
# THE FAST RUN (decision 451): `--fast` leaves out what `modules/slow_tests.py` lists; the full run
# (no argument) is the one before every commit.
FAST = "--fast" in sys.argv[1:]
sys.path.insert(0, "/usr/src/BRAVO/modules")
from slow_tests import is_slow as _is_slow
# SHARDS (2026-10-02, the PI: "parallelize all the tests and run them massively parallel"). A routine
# run splits the test FILES across processes (`--shards N`, default: the core count, at most one per
# file); each process runs its files' tests in file order, exactly as one process did, and the parent
# adds the counts. The unit is ONE TEST FUNCTION, not a file (2026-10-02: test_analytics.py alone
# took 92 s and set the pace for the whole run): every shard imports the files its tests live in and
# runs them in the same alphabetical order one process used. `--shards 1` is the old one-process
# run. `--live` stays one process.
import json, subprocess, time
def _arg(name, default=None):
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a else default
SHARD = _arg("--shard")                    # "i/N": this process runs files i, i+N, i+2N, ...
N_SHARDS = int(_arg("--shards", "0") or 0)

def _is_live(fn):
    return any(getattr(m, "name", None) == "live" for m in getattr(fn, "pytestmark", []) or [])

import ast
def _units(files):
    """(package, file, test name) for every top-level `test_*` function, files in order, names in
    the alphabetical order `dir()` gave the one-process runner. Read from the source, not imported."""
    out = []
    for pkg, f in files:
        try:
            names = sorted(n.name for n in ast.parse(open(f).read()).body
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_"))
        except SyntaxError:
            names = ["<import>"]
        if FAST:
            names = [nm for nm in names if not _is_slow(f, nm)]
        out += [(pkg, f, nm) for nm in names] or [(pkg, f, "<import>")]
    return out

def _files():
    out = []
    for _pkg in ["Biomarkers", "CacheStore", "DecodeCommon", "ControlAnalyses", "MedtronicPercept"]:
        if FAST and _is_slow(f"/usr/src/BRAVO/modules/{_pkg}/tests/x.py", "x"):
            continue
        out += [(_pkg, p) for p in sorted(glob.glob(f"/usr/src/BRAVO/modules/{_pkg}/tests/test_*.py"))]
    return out

if SHARD is None and not LIVE_ONLY and N_SHARDS != 1:
    # the parent: start one process per shard, then add up what each reports
    n = N_SHARDS or (os.cpu_count() or 1)
    n = max(1, min(n, len(_units(_files()))))
    t0 = time.time()
    procs = [subprocess.Popen([sys.executable, "-B", os.path.abspath(__file__), "--shard", f"{i}/{n}"] + (["--fast"] if FAST else []),
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
             for i in range(n)]
    tot = {"pass": 0, "fail": 0, "live": 0}; fails = []; slow = []; bad = 0
    for pr in procs:
        out, _ = pr.communicate()
        rec = [l for l in out.splitlines() if l.startswith("SHARD_RESULT ")]
        if not rec:
            bad += 1; fails.append(("shard", "CRASHED", out[-300:])); continue
        r = json.loads(rec[-1][len("SHARD_RESULT "):])
        for k in tot: tot[k] += r[k]
        fails += [tuple(x) for x in r["fails"]]; slow += r["times"]
    nfail = tot["fail"] + bad
    print(f"PASS={tot['pass']} FAIL={nfail} LIVE_SKIPPED={tot['live']}  [{n} processes, {time.time()-t0:.0f} s]")
    for f, sec in sorted(slow, key=lambda x: -x[1])[:5]: print(f"  slowest file: {f} {sec:.1f} s")
    for mod, nm, e in fails[:20]: print("  FAIL", str(mod).split('.')[-1], nm, e)
    sys.exit(0)

sys.path.insert(0, "/usr/src/BRAVO")
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
# Tests never add requests to the live server's list of requests to replay (decision 435).
os.environ.setdefault("BRAVO_REMEMBER_REQUESTS", "0")
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
#   MedtronicPercept — the decoder of the device's exported files (2026-09-26: every recording
#                 starts at the tablet's clock time). It imports scipy and the platform's utility
#                 package, which the host has not got, so its tests run here only.
PACKAGES = ["Biomarkers", "CacheStore", "DecodeCommon", "ControlAnalyses", "MedtronicPercept"]

files = [(pkg, p) for pkg, p in _files() if pkg in PACKAGES]
_mine = None                                  # {file: set of test names} this shard runs
if SHARD is not None:
    _i, _n = (int(x) for x in SHARD.split("/"))
    _mine = {}
    for pkg, f, nm in _units(files)[_i::_n]:
        _mine.setdefault(f, set()).add(nm)
    files = [(pkg, f) for pkg, f in files if f in _mine]
npass=nfail=nlive_skipped=0; fails=[]; times=[]
for pkg, f in files:
    _t0 = time.time()
    mod=f"modules.{pkg}.tests."+os.path.basename(f)[:-3]
    try:
        m=importlib.import_module(mod); importlib.reload(m)
    except Exception as e:
        fails.append((mod,"IMPORT",repr(e))); nfail+=1; continue
    for nm in dir(m):
        if nm.startswith("test_") and callable(getattr(m,nm)) and (_mine is None or nm in _mine[f]) \
                and not (FAST and _is_slow(f, nm)):
            if _is_live(getattr(m, nm)) != LIVE_ONLY:
                if not LIVE_ONLY:
                    nlive_skipped += 1
                continue
            try:
                getattr(m,nm)(); npass+=1
            except Exception as e:
                nfail+=1; fails.append((mod,nm,repr(e)[:200]))
    times.append((os.path.basename(f), time.time() - _t0))
if SHARD is not None:
    print("SHARD_RESULT " + json.dumps({"pass": npass, "fail": nfail, "live": nlive_skipped,
                                        "fails": fails, "times": times}))
    sys.exit(0)
print(f"PASS={npass} FAIL={nfail}" + (" (live tests only)" if LIVE_ONLY else f" LIVE_SKIPPED={nlive_skipped}"))
for mod,nm,e in fails[:20]: print("  FAIL",mod.split('.')[-1],nm,e)
