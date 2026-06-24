# Standalone demo of the NEW binarization histogram with per-group source boxes,
# mirroring the production BinarizationPreview.js layout, on the real RCS08 scan.
import json, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

d = json.load(open("BRAVO/_review_export_rcs08.json"))
scan = d["psd_scan_index"]; pm = {m["key"]: m for m in d["pain_metrics"]}["nrs"]
import datetime as dt
pt = []; pv = []
for p in pm["points"]:
    t = dt.datetime.strptime(p["t"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()
    pt.append(t); pv.append(p["v"])
pt = np.array(pt); pv = np.array(pv); o = np.argsort(pt); pt, pv = pt[o], pv[o]

def match(tol_min):
    tol = tol_min*60; rows=[]
    for e in scan:
        ts=e["t"]; i=np.searchsorted(pt, ts); best=None; bd=None
        for k in (i-1,i):
            if 0<=k<len(pt):
                dd=abs(pt[k]-ts)
                if dd<=tol and (bd is None or dd<bd): best=k; bd=dd
        if best is not None: rows.append((pv[best], e["source"]))
    return rows

BIN={"high":"#D55E00","low":"#0072B2","excluded":"#5A6066"}
def render(ax, tol):
    rows=match(tol); vals=np.array([r[0] for r in rows]); srcs=[r[1] for r in rows]
    lo,hi=np.percentile(vals,33.3333),np.percentile(vals,66.6667)
    # integer bins
    los,his=int(round(vals.min())),int(round(vals.max()))
    edges=np.arange(los-0.5,his+1.5,1.0); ctr=(edges[:-1]+edges[1:])/2
    cnt,_=np.histogram(vals,bins=edges)
    cols=[BIN["low"] if c<=lo else (BIN["high"] if c>=hi else BIN["excluded"]) for c in ctr]
    ax.bar(ctr,cnt,width=0.92,color=cols)
    yMax=max(1,cnt.max())
    # per-group source breakdown
    by={"low":{"td":0,"montage":0},"high":{"td":0,"montage":0},"excluded":{"td":0,"montage":0}}
    for v,s in zip(vals,srcs):
        b="low" if v<=lo else ("high" if v>=hi else "excluded")
        k="td" if "td" in s.lower() else "montage"; by[b][k]+=1
    ax.set_ylim(0,yMax*1.6)
    ax.axhline(yMax,ls=":",color=BIN["excluded"],lw=1)
    def box(x,yf,color,label,g):
        txt=f"{label}\n{g['td']+g['montage']} samples\n{g['td']} TD · {g['montage']} PSD · LSB n/a"
        ax.text(x,yMax*yf,txt,ha="center",va="bottom",fontsize=8.5,color="white",fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.4",fc=color,ec=color,lw=1.5,alpha=0.94))
    loX=ctr[ctr<=lo].mean() if (ctr<=lo).any() else lo
    hiX=ctr[ctr>=hi].mean() if (ctr>=hi).any() else hi
    box(loX,1.02,BIN["low"],"Low",by["low"])
    box(hiX,1.02,BIN["high"],"High",by["high"])
    box((lo+hi)/2,1.30,BIN["excluded"],"Excluded",by["excluded"])
    ax.axvline(lo,ls="--",color=BIN["low"],lw=1.5); ax.axvline(hi,ls="--",color=BIN["high"],lw=1.5)
    ax.set_title(f"Match window ±{tol} min — {len(vals)} matched neural samples",fontsize=10,fontweight="bold")
    ax.set_xlabel("NRS (0–10)"); ax.set_ylabel("Matched neural samples")
    for sp in ("top","right"): ax.spines[sp].set_visible(False)

fig,axes=plt.subplots(1,2,figsize=(15,5.2))
render(axes[0],15); render(axes[1],60)
fig.suptitle("Binarization histogram — per-group modality boxes (TD / PSD / LSB), excluded box above the max line",
             fontsize=12,fontweight="bold")
fig.tight_layout(rect=[0,0,1,0.96])
fig.savefig("_review_export/preview_hist_boxes.png",dpi=130)
print("rendered preview_hist_boxes.png")
