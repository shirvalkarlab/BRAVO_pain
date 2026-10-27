import sys; sys.path.insert(0,".")
import numpy as np, pandas as pd
from steps import F
pd.set_option("display.width",250)
d=pd.read_pickle("steps4_scored.pkl"); P=np.load("steps4_psd.npy"); d["i"]=np.arange(len(d))
TONES=(55.5,111.0)
def line25(p):
    near=np.zeros_like(F,bool)
    for g in (5,25,30,55,60,80,85,110,115)+TONES: near|=np.abs(F-g)<=1.0
    i=int(np.argmin(np.abs(F-25))); ring=(np.abs(F-25)>=1.5)&(np.abs(F-25)<=4)&~near
    return np.clip(p[i-1:i+2]-np.median(p[ring]),0,None).sum()*0.5
sel=d[(d.rate==55)&(d.sense_hz.between(25.5,27.5))].copy()
sel["L25"]=[line25(P[i]) for i in sel.i]
sel["band_pow"]=[P[i][np.abs(F-r.sense_hz)<=2.5].sum()*0.5 for i,r in zip(sel.i,sel.itertuples())]
off=sel[(sel.ma==0)&(sel.ma_other_max==0)]
print("55 Hz rate, device band centred 25.5-27.5 Hz; 25 Hz landing inside the band")
for ch,g in sel.groupby("channel"):
    b=off[off.channel==ch].L25.median() if (off.channel==ch).any() else np.nan
    g=g.assign(net=np.clip(g.L25-b,0,None)); g["share"]=g.net/g.band_pow
    g["mAbin"]=pd.cut(g.ma,[-0.01,0,1,2,3,4,6])
    print(ch, "stim-off baseline at 25 Hz (uV^2):", round(b,4) if b==b else b)
    print(g.groupby(["grp","mAbin"],observed=True).agg(steps=("key","size"),recs=("key","nunique"),days=("session","nunique"),
          net_line_uV2=("net","median"),band_uV2=("band_pow","median"),share_med=("share","median"),share_max=("share","max")).round(4).to_string())
# within-recording change from the recording's own 0 mA step
rows=[]
for k,g in d.groupby("key"):
    z=g[(g.ma==0)]
    if z.empty: continue
    b_bb=z.bb_5_32.median(); b_l=z.lfp_med.median()
    for r in g[g.ma>0].itertuples():
        rows.append(dict(channel=r.channel,rate=r.rate,grp=r.grp,pw=r.pw,session=r.session,key=k,ma=r.ma,bb_x=r.bb_5_32/b_bb,lfp_x=r.lfp_med/b_l if b_l>0 else np.nan))
w=pd.DataFrame(rows); w["mAbin"]=pd.cut(w.ma,[0,1,2,3,4,6])
print("\nWithin one recording: power with current on / the same recording's 0 mA step")
print(w.groupby(["channel","rate","grp","mAbin"],observed=True).agg(recs=("key","nunique"),days=("session","nunique"),steps=("key","size"),
      broadband_x=("bb_x","median"),device_band_x=("lfp_x","median")).round(2).to_string())
