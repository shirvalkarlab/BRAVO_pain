import os, sys, time, importlib, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import availability as av, analytics
importlib.reload(analytics); importlib.reload(av); importlib.reload(bs)

FS=250.0; T0=1_700_000_000.0
rng=np.random.default_rng(42)
centers=np.array(bs._LSB_SPECTRUM_CENTERS)

def td_rec(ch, start, secs=40.0, f=20.0):
    n=int(secs*FS); t=np.arange(n)/FS
    x=2.0*np.sin(2*np.pi*f*t)+0.1*rng.standard_normal(n)
    return {"ChannelNames":[ch],"Data":x.reshape(-1,1),"SamplingRate":FS,"StartTime":start,"Missing":None}

def event(ch, t, center=20.0):
    freq=np.linspace(0.95,100,100); mag=np.full_like(freq,0.1); mag[np.argmin(abs(freq-center))]=5.0
    return {"channel":ch,"t":t,"freq":freq,"power":mag,"center_hz":center}

uid="test-uid-cache"; ch="ZERO_THREE_LEFT"
td=[td_rec(ch,T0), td_rec(ch,T0+60)]
evs=[event(ch,T0+9000.0)]
pro_times=np.array([T0+20.0, T0+9000.0, T0+99999.0])

bs._LSB_SPECTRUM_MEMO.clear()
t0=time.perf_counter()
r1=bs._pro_lsb_spectrum_cached(uid, pro_times, [ch], td, evs)
t1=time.perf_counter()-t0
t2=time.perf_counter()
r2=bs._pro_lsb_spectrum_cached(uid, pro_times, [ch], td, evs)
t3=time.perf_counter()-t2
print(f"first={t1*1000:.1f}ms  second={t3*1000:.2f}ms  hit={r1 is r2}")

s0,s1,s2=r1[ch]
ci20=int(np.argmin(abs(centers-20.0))); ci55=int(np.argmin(abs(centers-55.0)))
print(f"PRO+20s  tier={s0['tier']}  n_bands={sum(v is not None for v in s0['lsb'])}  cal@{centers[ci20]}Hz={s0['calibrated'][ci20]}")
print(f"PRO+9000 tier={s1['tier']}  n_bands={sum(v is not None for v in s1['lsb'])}  cal@{centers[ci20]}Hz={s1['calibrated'][ci20]}  cal@{centers[ci55]}Hz={s1['calibrated'][ci55]}")
print(f"PRO+9999 tier={s2['tier']}  all_none={all(v is None for v in s2['lsb'])}")
# montage TD must go through td_transform
montage_td=[{"ChannelNames":[ch],"Data":np.sin(np.arange(10000)/250.0*2*np.pi*20).reshape(-1,1),"SamplingRate":250.0,"StartTime":T0,"Missing":None}]
rm=bs._pro_lsb_spectrum_cached("uid-m", pro_times[:1], [ch], montage_td, [])
print(f"montage-only tier={rm[ch][0]['tier']}  (expected td_transform)")
print("CACHE TEST OK")
