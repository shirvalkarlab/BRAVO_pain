import os, sys, numpy as np, importlib
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers.routines import analytics; importlib.reload(analytics)
print("K_TD_PSD =", analytics.LSB_PER_UV2_DEVICE_PSD_TD_RATIO)
print("K_PSD_LSB =", round(analytics.LSB_PER_DEVICE_PSD,4))
# clamp
m=np.array([-0.11, 0.0, 0.5, -0.05, 2.0])
print("clamp:", analytics.clamp_device_psd(m))
# band power: synthetic PSD with a peak at 20 Hz
f=np.linspace(0,96.68,100); mag=np.zeros(100); 
peakbins=(f>=17.5)&(f<22.5); mag[peakbins]=np.array([1.0,2.0,3.0,2.0,1.0])[:peakbins.sum()] if peakbins.sum()<=5 else 2.0
bp=analytics.device_psd_band_power(f,mag,20.0,half_hz=2.5)
print("band power @20Hz:", round(bp,4), " expected sum of squares:", round(float(np.sum(mag[peakbins]**2)),4))
lsb=analytics.device_psd_to_lsb(f,mag,20.0)
print("device_psd_to_lsb @20Hz:", round(lsb,4), "== K*bp:", round(analytics.LSB_PER_DEVICE_PSD*bp,4))
# vector center
print("vector centers:", np.round(analytics.device_psd_to_lsb(f,mag,np.array([10.,20.,30.])),3))
# negative-only band -> clamped to 0 -> NaN
mneg=np.where(mag>0,-0.1,mag); print("all-neg band -> ", analytics.device_psd_to_lsb(f,mneg,20.0))
