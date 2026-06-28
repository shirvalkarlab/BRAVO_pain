import os, sys, importlib, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers.routines import availability as av, analytics
importlib.reload(analytics); importlib.reload(av)
FS=250.0; T0=1_700_000_000.0
def td_rec(ch, start, secs=40.0, f=20.0, amp=2.0, seed=0):
    n=int(secs*FS); t=np.arange(n)/FS
    rng=np.random.default_rng(seed)
    x=amp*np.sin(2*np.pi*f*t)+0.1*rng.standard_normal(n)
    return {"ChannelNames":[ch],"Data":x.reshape(-1,1),"SamplingRate":FS,"StartTime":start,"Missing":None}
def event(ch,t,center=20.0):
    freq=np.linspace(0.95,100,100); mag=np.full_like(freq,0.1); mag[np.argmin(abs(freq-center))]=5.0
    return {"channel":ch,"t":t,"freq":freq,"power":mag,"center_hz":center}
ch="ZERO_THREE_LEFT"
centers=np.arange(2.5,100,1.0)
# TD pair at +20s
td=[td_rec(ch,T0)]
spec=av.per_pro_lsb_spectrum([T0+20.0], ch, centers, td_recordings=td, event_psd_recordings=[])
r=spec[0]
peak_i=int(np.nanargmax([v if v is not None else -1 for v in r["lsb"]]))
print(f"TD pair: tier={r['tier']} peak_center={centers[peak_i]:.1f}Hz peak_lsb={r['lsb'][peak_i]:.1f} calibrated@20Hz={r['calibrated'][int(np.argmin(abs(centers-20)))]}")
# cross-check: single-band per_pro_lsb at 20 Hz must equal the spectrum at center 20
single=av.per_pro_lsb([T0+20.0], None, ch, 20.0, td_recordings=td, event_psd_recordings=[])[0]
ci20=int(np.argmin(abs(centers-20.0)))
print(f"  single-band per_pro_lsb@20Hz={single['lsb']:.4f}  spectrum@20Hz={r['lsb'][ci20]:.4f}  match={abs(single['lsb']-r['lsb'][ci20])<1e-6}")
# PSD-only event pair at +9000s (no TD)
ev=[event(ch,T0+9000.0,center=20.0)]
spec2=av.per_pro_lsb_spectrum([T0+9000.0], ch, centers, td_recordings=[], event_psd_recordings=ev)
r2=spec2[0]
ci55=int(np.argmin(abs(centers-55.0)))
print(f"PSD bridge: tier={r2['tier']} lsb@20Hz={r2['lsb'][ci20]} cal@20={r2['calibrated'][ci20]} | lsb@55Hz_present={r2['lsb'][ci55] is not None} cal@55={r2['calibrated'][ci55]}")
# unmatched
spec3=av.per_pro_lsb_spectrum([T0+99999.0], ch, centers, td_recordings=td, event_psd_recordings=ev)
print(f"unmatched: tier={spec3[0]['tier']} all_none={all(v is None for v in spec3[0]['lsb'])}")
print("SPECTRUM TEST OK")
