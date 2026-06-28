import os, sys, numpy as np, datetime as dt, bisect, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.bravo_service import models, PATIENT_EVENT_TYPE
UID="2e3c75c00d7f4f37b53a048d195f11da"
P=models.Participant.find(uid=UID); SF=models.SourceFile.find_all(owner=P)
def hemi(ch): return "RIGHT" if "RIGHT" in str(ch) or "Right" in str(ch) else "LEFT"
def shemi(h): return "RIGHT" if "Right" in str(h) else "LEFT"

# survey LFPMagnitude blocks keyed by hemisphere
surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
srows=[]
for s in surveys:
    t=bs.availability._to_epoch(s.get("StartTime")); desc=s.get("Descriptor")
    if t is None or not isinstance(desc,dict): continue
    for e in (desc.get("MedtronicPSD") or []):
        if not isinstance(e,dict): continue
        lm=np.asarray(e.get("LFPMagnitude",[]),float); lf=np.asarray(e.get("LFPFrequency",[]),float)
        if lm.size==100 and lf.size==100:
            srows.append((float(t),shemi(e.get("Hemisphere")),lf,lm))
# event FFTBinData blocks keyed by hemisphere
erows=[]
for r in models.Recording.find_all(source__in=SF,type=PATIENT_EVENT_TYPE):
    md=getattr(r,'metadata',None)
    if not isinstance(md,dict): continue
    for hk,hb in md.items():
        if not isinstance(hb,dict): continue
        f=hb.get("Frequency"); m=hb.get("FFTBinData")
        if not(isinstance(f,(list,tuple)) and isinstance(m,(list,tuple)) and len(f)==len(m)==100): continue
        h="RIGHT" if "Right" in str(hk) else "LEFT"
        t=None
        if hb.get("DateTime"):
            try: t=dt.datetime.fromisoformat(str(hb["DateTime"]).replace("Z","+00:00")).timestamp()
            except: t=None
        if t is None: t=getattr(r,'date',None)
        if t is None: continue
        erows.append((float(t),h,np.asarray(f,float),np.asarray(m,float)))

from collections import defaultdict
ev_by_h=defaultdict(list)
for t,h,f,m in erows: ev_by_h[h].append((t,f,m))
for h in ev_by_h: ev_by_h[h].sort(key=lambda x:x[0])

for TOL in (60,300,900):
    pairs=[]
    for ts,sh,lf,lm in srows:
        cand=ev_by_h.get(sh,[])
        if not cand: continue
        times=[c[0] for c in cand]; i=bisect.bisect_left(times,ts); best=None
        for j in (i-1,i):
            if 0<=j<len(cand):
                d=abs(cand[j][0]-ts)
                if d<=TOL and (best is None or d<best[0]): best=(d,cand[j])
        if best: pairs.append((lf,lm,best[1][1],best[1][2]))  # lf, LFPmag, evfreq, FFTbin
    # bin-by-bin paired points (in-band 2-50 Hz, where SNR is good), positive both sides
    xs=[]; ys=[]
    for lf,lm,ef,fb in pairs:
        if not np.allclose(lf,ef): continue
        band=(lf>=2)&(lf<=50)
        a=lm[band]; b=fb[band]
        ok=(a>0)&(b>0)
        xs.append(a[ok]); ys.append(b[ok])
    if not xs: print(f"TOL={TOL}s: {len(pairs)} pairs, 0 usable bins"); continue
    X=np.concatenate(xs); Y=np.concatenate(ys)
    import statsmodels.api as sm
    lx=np.log(X); ly=np.log(Y)
    res=sm.OLS(ly, sm.add_constant(lx)).fit()
    slope=res.params[1]; inter=res.params[0]; r2=res.rsquared
    print(f"TOL={TOL}s: pairs={len(pairs)} bins={X.size}  loglog: FFTbin = exp({inter:.3f})*LFPmag^{slope:.3f}  R2={r2:.3f}  r={np.sign(slope)*np.sqrt(r2):.3f}")
