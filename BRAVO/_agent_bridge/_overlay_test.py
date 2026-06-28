import os, sys, numpy as np, importlib
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers.routines import availability as av, analytics
importlib.reload(analytics); importlib.reload(av)
fs=250.0
n=int(30*fs); tt=np.arange(n)/fs
sig=2.0*np.sin(2*np.pi*20*tt)+0.1*np.random.default_rng(0).standard_normal(n)
# agg=none per-window check
pw=analytics.td_transform_band_power(sig, fs, 20.0, step_samples=125, agg="none")
print(f"agg=none per-window shape: {np.asarray(pw).shape} (expect ~59 windows over 30s at 50% overlap)")
med_none=np.median(pw); med_default=analytics.td_transform_band_power(sig, fs, 20.0, step_samples=125)
print(f"median(agg=none)={med_none:.4f}  vs agg=median default={med_default:.4f}  equal={abs(med_none-med_default)<1e-9}")
# vector center agg=none shape
pwv=analytics.td_transform_band_power(sig, fs, np.array([10.,20.,30.]), step_samples=125, agg="none")
print(f"agg=none vector-center shape: {np.asarray(pwv).shape} (expect (W,3))")
# overlay
ov=av.per_pro_lsb_overlay(sig, fs, 15.0, 20.0)  # PRO at center of a 30s recording
print(f"overlay: n_windows={ov['n_windows']} median_lsb={ov['median_lsb']:.1f} used_s={ov['used_s']} sat={ov['saturated']} ok={ov['ok']}")
print(f"  first 3 (t_offset, lsb): {[(round(t,2),round(l,1)) for t,l in zip(ov['t_offset_s'][:3], ov['lsb'][:3])]}")
# saturation overlay
sigsat=sig.copy(); sigsat[3000:3050]=5000.0
ovs=av.per_pro_lsb_overlay(sigsat, fs, 15.0, 20.0)
print(f"saturated overlay: n_saturated={ovs['n_saturated']}/{ovs['n_windows']} saturated={ovs['saturated']} reason='{ovs['reason']}'")
assert np.asarray(pw).shape[0] in (59,60)
assert abs(med_none-med_default)<1e-9
assert ov['n_windows'] in (59,60) and ov['median_lsb']>0
assert ovs['n_saturated']>0 and ovs['saturated']
print("OVERLAY ASSERTIONS PASS")
