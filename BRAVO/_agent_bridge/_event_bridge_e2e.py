import os, sys, numpy as np, importlib
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import availability, analytics
importlib.reload(analytics); importlib.reload(availability); importlib.reload(bs)
UID="2e3c75c00d7f4f37b53a048d195f11da"
# sensing centers from powerdomain
pdl=bs._load_recordings(UID,["MedtronicBrainSensePowerDomain"])
sensing=availability.analytics.power_center_freqs(pdl)
print("sensing centers (chan->Hz):", {k:round(v,1) for k,v in list(sensing.items())[:6]})
blocks=bs._event_psd_lsb_blocks(UID, sensing_hz_by_channel=sensing)
print(f"event PSD bridge blocks built: {len(blocks)}")
if blocks:
    cs=[b["center_hz"] for b in blocks]
    print(f"  center_hz: min={min(cs):.1f} max={max(cs):.1f} (should be in [{analytics.LSB_VALIDATED_HZ_LO},{analytics.LSB_DEPLOYABLE_HZ_HI}] OR a sensing center)")
    chs=set(b["channel"] for b in blocks); print(f"  channels: {sorted(chs)[:8]}")
# run lsb_series WITH events vs WITHOUT, count modeled bridge points
ev_method_tag="event_psd_bridge"
ls_with=availability.lsb_series([], pdl, montage_td_recordings=[], sensing_hz_by_channel=sensing, event_psd_recordings=blocks)
nbridge=0; lsbvals=[]
for ch,d in ls_with.items():
    for m,y in zip(d["method"], d["y"]):
        if m and ev_method_tag in m: nbridge+=1; lsbvals.append(y)
print(f"bridge LSB points emitted: {nbridge}")
if lsbvals:
    lv=np.array(lsbvals)
    print(f"  LSB range: {lv.min():.1f} .. {lv.max():.1f}  median={np.median(lv):.1f}")
    print(f"  method tag sample: {[m for d in ls_with.values() for m in d['method'] if m and ev_method_tag in m][:1]}")
    print(f"  all modeled=True: {all(mo for d in ls_with.values() for mo,me in zip(d['modeled'],d['method']) if me and ev_method_tag in me)}")
    print(f"  all source=psd_modeled: {all(s=='psd_modeled' for d in ls_with.values() for s,me in zip(d['source'],d['method']) if me and ev_method_tag in me)}")
