import os, sys, time, importlib, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import availability as av, analytics
importlib.reload(analytics); importlib.reload(av); importlib.reload(bs)

FS=250.0; T0=1_700_000_000.0
rng=np.random.default_rng(42)

def td_rec(ch, start, secs=40.0, amp=2.0, f=20.0):
    n=int(secs*FS); t=np.arange(n)/FS
    x=amp*np.sin(2*np.pi*f*t)+0.1*rng.standard_normal(n)
    return {"ChannelNames":[ch],"Data":x.reshape(-1,1),"SamplingRate":FS,"StartTime":start,"Missing":None,"Source":"td"}

def event(ch, t, center=20.0):
    freq=np.linspace(0.95,100,100); mag=np.full_like(freq,0.1); mag[np.argmin(abs(freq-center))]=5.0
    return {"channel":ch,"t":t,"freq":freq,"power":mag,"center_hz":center}

uid="test-uid-cache"; ch="ZERO_THREE_LEFT"
td=[td_rec(ch,T0), td_rec(ch,T0+60)]
evs=[event(ch,T0+9000.0)]
pro_times=np.array([T0+20.0, T0+9000.0, T0+99999.0])

# first call
bs._LSB_SPECTRUM_MEMO.clear()
t0=time.perf_counter()
r1=bs._pro_lsb_spectrum_cached(uid, pro_times, [ch], td, evs)
t1=time.perf_counter()-t0

# second call (should hit memo)
t2=time.perf_counter()
r2=bs._pro_lsb_spectrum_cached(uid, pro_times, [ch], td, evs)
t3=time.perf_counter()-t2

print(f"first call: {t1*1000:.1f} ms  second call: {t3*1000:.1f} ms  ratio: {t1/max(t3,1e-9):.0f}x faster")
print(f"memo hit: {r1 is r2}")

spectra=r1[ch]
s0=spectra[0]; s1=spectra[1]; s2=spectra[2]
print(f"PRO+20s (TD):   tier={s0['tier']} n_bands={sum(v is not None for v in s0['lsb'])} cal@20Hz={s0['calibrated'][int(np.argmin(abs(bs._LSB_SPECTRUM_CENTERS-20)))]}")
print(f"PRO+9000s (PSD): tier={s1['tier']} n_bands={sum(v is not None for v in s1['lsb'])} cal@20Hz={s1['calibrated'][int(np.argmin(abs(bs._LSB_SPECTRUM_CENTERS-20)))]} cal@55Hz={s1['calibrated'][int(np.argmin(abs(bs._LSB_SPECTRUM_CENTERS-55)))]}")
print(f"PRO+99999s (none): tier={s2['tier']} all_none={all(v is None for v in s2['lsb'])}")
# verify montage TD (a dict with same schema as td_rec) goes through td_transform, NOT bridge
montage_td=[{"ChannelNames":[ch],"Data":np.sin(np.arange(10000)/FS*2*np.pi*20).reshape(-1,1),"SamplingRate":FS,"StartTime":T0,"Missing":None}]
rm=bs._pro_lsb_spectrum_cached("test-uid-montage", pro_times[:1], [ch], montage_td, [])  # no events
print(f"montage TD (no events): tier={rm[ch][0]['tier']} (expected td_transform)")
print("CACHE TEST OK")
