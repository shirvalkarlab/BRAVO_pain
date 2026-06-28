import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
nas=bs._load_recordings(UID,["NeuralActivitySnapshot"])
print(f"NeuralActivitySnapshot: {len(nas)}")
s=nas[0]
print("keys:", list(s.keys()))
for k in ("Spectrum","PSD"):
    v=s.get(k)
    print(f"\n--- {k}: type={type(v).__name__}", end="")
    if isinstance(v,list):
        print(f" len={len(v)}")
        if v and isinstance(v[0],dict):
            e=v[0]; print(f"  [0] keys: {list(e.keys())}")
            for kk,vv in e.items():
                if isinstance(vv,(list,tuple)):
                    a=np.asarray(vv,float) if all(isinstance(x,(int,float)) for x in vv[:3]) else None
                    if a is not None and a.size:
                        print(f"    {kk}: n={a.size} [{a.min():.4f}..{a.max():.4f}] frac_neg={np.mean(a<0):.3f}")
                    else:
                        print(f"    {kk}: {str(vv)[:60]}")
                else:
                    print(f"    {kk}: {vv}")
    elif isinstance(v,dict):
        print(f" keys={list(v.keys())}")
# TD present?
d=s.get("Data"); print(f"\nTD Data: shape={getattr(d,'shape',None)} SR={s.get('SamplingRate')} chans={s.get('ChannelNames')}")
