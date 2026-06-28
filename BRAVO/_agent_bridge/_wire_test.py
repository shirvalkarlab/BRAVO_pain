import os, sys, importlib, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import availability as av
importlib.reload(av); importlib.reload(bs)
UID="2e3c75c00d7f4f37b53a048d195f11da"
req={"ParticipantId":UID}
out=bs.availability_for_participant(req)
av_block=out.get("availability") or {}
pl=av_block.get("pro_lsb") or {}
pain=av_block.get("pain") or {}
print("n_PRO:", len(pain.get("t") or []))
print("pro_lsb channels:", list(pl.keys())[:8], "...(total %d)"%len(pl))
# tier tally across all channels
from collections import Counter
tally=Counter(); sat=0; vals=0
for ch, series in pl.items():
    for r in series:
        tally[str(r.get("tier"))]+=1
        if r.get("saturated"): sat+=1
        if r.get("lsb") is not None: vals+=1
print("tier tally:", dict(tally))
print("saturated windows:", sat, "| PRO-LSB values produced:", vals)
# show a sample channel's first few
for ch, series in list(pl.items())[:1]:
    print(f"sample channel {ch} (first 5 of {len(series)}):")
    for r in series[:5]:
        print(f"   t={r['t']:.0f} tier={str(r['tier']):14s} lsb={('%.1f'%r['lsb']) if r['lsb'] else 'None':>8} sat={r['saturated']} center={r['center_hz']}")
print("WIRE TEST OK")
