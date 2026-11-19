import numpy as np, pandas as pd
pd.set_option("display.width",250); pd.set_option("display.max_columns",30)
rng=np.random.default_rng(1)
d=pd.read_pickle("steps4_scored.pkl"); on=d[d.ma>0]
def slope0(x,y): return float((x*y).sum()/(x*x).sum())
def boot(a,b,col,n=4000):
    ka,kb=a.key.unique(),b.key.unique(); ga={k:a[a.key==k] for k in ka}; gb={k:b[b.key==k] for k in kb}; o=[]
    for _ in range(n):
        aa=pd.concat([ga[k] for k in rng.choice(ka,len(ka))]); bb=pd.concat([gb[k] for k in rng.choice(kb,len(kb))])
        sa=slope0(aa.ma,aa[col]); o.append(slope0(bb.ma,bb[col])/sa if sa>0 else np.nan)
    o=np.array(o); return np.nanpercentile(o,[2.5,97.5]), np.isnan(o).mean()
print("RATE-MATCHED: 100 us against wider pulses, same pair, shared currents")
for ch,rate,narrow,wide in [("ZERO_THREE_RIGHT",55,[100],[150,160,180]),("ZERO_THREE_RIGHT",110,[100],[180,200,220]),
                            ("ONE_THREE_LEFT",55,[90,100],[180,270]),("ZERO_THREE_RIGHT",145,[60],[140,160,180])]:
    g=on[(on.channel==ch)&(on.rate==rate)]; a=g[g.pw.isin(narrow)]; b=g[g.pw.isin(wide)]
    if a.empty or b.empty: print(ch,rate,"missing a group", len(a), len(b)); continue
    cap=min(a.ma.max(),b.ma.max()); a=a[a.ma<=cap+1e-9]; b=b[b.ma<=cap+1e-9]
    for col in ("A_all","A_band"):
        sa,sb=slope0(a.ma,a[col]),slope0(b.ma,b[col]); ci,nf=boot(a,b,col)
        print(f"{ch} {rate} Hz {col}: {narrow} us {a.key.nunique()} recs/{a.session.nunique()} days/{len(a)} steps slope {sa:.2f} uV/mA; "
              f"{wide} us {b.key.nunique()} recs/{b.session.nunique()} days/{len(b)} steps slope {sb:.2f}; ratio {sb/sa if sa>0 else float('nan'):.2f} "
              f"[{ci[0]:.2f}, {ci[1]:.2f}]; charge model {b.pw.mean()/a.pw.mean():.2f}; shared 0-{cap:g} mA; det {a.det_all.mean():.2f} vs {b.det_all.mean():.2f}")
s=on[on.lfp_n_spike>0]
print("\nDevice band-power spikes (>=10x the step median):", int(s.lfp_n_spike.sum()), "of", int(on.lfp_n.sum()), "current-on samples;",
      "steps", len(s), "recordings", s.key.nunique(), "days", s.session.nunique())
print(s.groupby(["channel","pw","rate","session"]).agg(spikes=("lfp_n_spike","sum"),n=("lfp_n","sum"),ma=("ma","max")).to_string())
o=d[d.ma==0]; print("at 0 mA:", int(o.lfp_n_spike.sum()), "of", int(o.lfp_n.sum()))
# where does the line energy sit? share of line power in each frequency range, current-on steps with a line found
def arr(x): return np.array([float(v) for v in str(x).split()]) if isinstance(x,str) else np.array([])
from collections import defaultdict
for grp in ("61-120",">120"):
    acc=defaultdict(float)
    for r in on[(on.grp==grp)&(on.det_all==1)].itertuples():
        for f,p in zip(arr(r.line_freqs),arr(r.line_powers)): acc["5-32.5" if 5<=f<=32.5 else ("<5" if f<5 else "32.5-123")]+=p
    t=sum(acc.values()); print(grp, {k:round(v/t,3) for k,v in acc.items()}, "(usable landings only; 55/110 Hz bins excluded here)")
