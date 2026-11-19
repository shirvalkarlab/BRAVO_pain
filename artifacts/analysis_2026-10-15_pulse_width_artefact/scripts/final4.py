import numpy as np, pandas as pd
rng=np.random.default_rng(2)
d=pd.read_pickle("steps4_scored.pkl")
rows=[]
for k,g in d.groupby("key"):
    z=g[g.ma==0]
    if z.empty: continue
    for r in g[g.ma>0].itertuples():
        rows.append(dict(key=k,channel=r.channel,rate=r.rate,grp=r.grp,ma=r.ma,session=r.session,
                         lfp_x=r.lfp_med/z.lfp_med.median(),bb_x=r.bb_5_32/z.bb_5_32.median()))
w=pd.DataFrame(rows)
s=w[(w.channel=="ZERO_THREE_RIGHT")&(w.rate==55)&(w.grp==">120")]
for lo,hi in ((0,1),(1,2),(2,3),(3,4),(0,4)):
    t=s[(s.ma>lo)&(s.ma<=hi)]; ks=t.key.unique()
    per=t.groupby("key")[["lfp_x","bb_x"]].median()   # one value per recording
    bs=[per.loc[rng.choice(per.index,len(per))].median().values for _ in range(4000)]
    ci=np.percentile(np.array(bs),[2.5,97.5],axis=0)
    print(f"{lo}-{hi} mA: {len(per)} recordings / {t.session.nunique()} days; device band x {per.lfp_x.median():.2f} [{ci[0,0]:.2f}, {ci[1,0]:.2f}]; broadband x {per.bb_x.median():.2f} [{ci[0,1]:.2f}, {ci[1,1]:.2f}]")
