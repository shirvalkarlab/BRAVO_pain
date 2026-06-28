import os, sys, numpy as np, importlib
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers.routines import availability as av, analytics
importlib.reload(analytics); importlib.reload(av)
fs=250.0; ch="ZERO_THREE_LEFT"; center=20.0
# tier 2: a 40 s TD recording at t0 with a 20 Hz signal, PRO at +20s
t0=1_700_000_000.0
n=int(40*fs); tt=np.arange(n)/fs
sig=2.0*np.sin(2*np.pi*20*tt)+0.1*np.random.default_rng(0).standard_normal(n)
td_rec={"ChannelNames":[ch],"Data":sig.reshape(-1,1),"SamplingRate":fs,"StartTime":t0}
# saturated TD: same but railed
sigsat=sig.copy(); sigsat[5000:5100]=5000.0
td_sat={"ChannelNames":[ch],"Data":sigsat.reshape(-1,1),"SamplingRate":fs,"StartTime":t0+1000}
# native series: a sensed sample near a PRO at t0+5000s
native={"t":[t0+5000.0],"y":[321.0],"center_hz":[20.0],"modeled":[False],"source":["streaming"]}
# event psd block near PRO at t0+9000
f=np.linspace(0,96.68,100); mag=np.zeros(100); mag[(f>=17.5)&(f<=22.5)]=2.0
ev={"channel":ch,"t":t0+9000.0,"freq":list(f),"power":list(mag),"center_hz":20.0}
pros=[t0+20.0,        # inside td_rec -> tier 2 TD
      t0+5000.0,      # near native -> tier 1
      t0+9000.0,      # only event -> tier 3 bridge
      t0+1020.0,      # inside saturated rec -> saturated, skip -> no other source -> None
      t0+99999.0]     # nothing -> None
res=av.per_pro_lsb(pros, native, ch, center,
                   td_recordings=[td_rec, td_sat], event_psd_recordings=[ev])
for r in res:
    print(f"  t=+{r['t']-t0:7.0f}s  tier={str(r['tier']):14s} lsb={('%.1f'%r['lsb']) if r['lsb'] else 'None':>8}  sat={r['saturated']}  {r['reason']}")
# assertions
assert res[0]["tier"]=="td_transform" and res[0]["lsb"]>0
assert res[1]["tier"]=="native" and abs(res[1]["lsb"]-321.0)<1e-9
assert res[2]["tier"]=="psd_bridge" and res[2]["lsb"]>0
assert res[3]["saturated"] is True and res[3]["lsb"] is None
assert res[4]["tier"] is None and res[4]["lsb"] is None
print("ALL TIER ASSERTIONS PASS")
