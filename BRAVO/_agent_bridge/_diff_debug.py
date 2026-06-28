import os, sys, importlib, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers.routines import availability as av, analytics
importlib.reload(analytics); importlib.reload(av)
FS=250.0; T0=1_700_000_000.0
n=int(40*FS); t=np.arange(n)/FS
rng=np.random.default_rng(0)
x=2.0*np.sin(2*np.pi*20.0*t)+0.1*rng.standard_normal(n)
td=[{"ChannelNames":["ZERO_THREE_LEFT"],"Data":x.reshape(-1,1),"SamplingRate":FS,"StartTime":T0,"Missing":None}]
ch="ZERO_THREE_LEFT"
# direct window cut at +20s
sl,used=analytics.transform_centered_window(x,FS,20.0,extent_s=30.0,missing=None,max_missing_frac=0.10)
step=int(round(FS*analytics.TRANSFORM_STEP_SECONDS))
# scalar center via td_to_lsb (what per_pro_lsb does)
a=analytics.td_to_lsb(sl,FS,20.0,half_hz=2.5,step_samples=step)
# vector center via td_transform_band_power (what spectrum does), pick the 20.0 element
centers=np.arange(2.5,100,1.0)
ci=int(np.argmin(abs(centers-20.0)))
print("center grid value at ci:", centers[ci])  # is it exactly 20.0?
bp=analytics.td_transform_band_power(sl,FS,centers,half_hz=2.5,step_samples=step)
b=analytics.LSB_PER_UV2_TRANSFORM*bp[ci]
# scalar 20.0 directly
bp_sc=analytics.td_transform_band_power(sl,FS,20.0,half_hz=2.5,step_samples=step)
print(f"td_to_lsb scalar@20.0      = {a:.6f}")
print(f"spectrum vector@grid[{ci}]   = {b:.6f}  (grid center {centers[ci]})")
print(f"scalar bp@20.0 *352.62     = {analytics.LSB_PER_UV2_TRANSFORM*bp_sc:.6f}")
print(f"=> diff is grid offset: 20.0 vs {centers[ci]}  (centers grid doesn't hit 20.0 exactly)")
