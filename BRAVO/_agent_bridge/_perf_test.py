import os, sys, importlib, time, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import availability as av, analytics
importlib.reload(analytics); importlib.reload(av); importlib.reload(bs)
# correctness re-check first (all CS-4 tests via the runner-style harness)
import Biomarkers.tests.test_per_pro_lsb as T; importlib.reload(T)
p=f=0
for n in sorted(d for d in dir(T) if d.startswith("test_")):
    try: getattr(T,n)(); p+=1
    except Exception as e: print("FAIL",n,repr(e)); f+=1
print(f"CS-4 tests: {p} passed, {f} failed")
# perf on live RCS08 build (time the full availability call, repeated to show cache-free per-PRO cost)
UID="2e3c75c00d7f4f37b53a048d195f11da"
t=time.time(); out=bs.availability_for_participant({"ParticipantId":UID}); dt=time.time()-t
pl=(out.get("availability") or {}).get("pro_lsb") or {}
vals=sum(1 for ch in pl for r in pl[ch] if r.get("lsb") is not None)
from collections import Counter; tally=Counter(str(r.get("tier")) for ch in pl for r in pl[ch])
print(f"availability_for_participant wall: {dt:.1f}s | pro_lsb values: {vals} | tiers: {dict(tally)}")
