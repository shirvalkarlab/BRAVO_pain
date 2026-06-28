import os, sys, importlib, traceback
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
import Biomarkers.tests.test_per_pro_lsb as T
importlib.reload(T)
names=[n for n in dir(T) if n.startswith("test_")]
p=f=0
for n in sorted(names):
    try:
        getattr(T,n)(); print("PASS",n); p+=1
    except Exception as e:
        print("FAIL",n,repr(e)); traceback.print_exc(); f+=1
print(f"\nCS-4 per-PRO tests: {p} passed, {f} failed")
