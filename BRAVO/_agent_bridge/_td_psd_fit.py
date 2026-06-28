import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import analytics
import statsmodels.api as sm
UID="2e3c75c00d7f4f37b53a048d195f11da"

def td_chan_to_contact(ch):
    s=str(ch); h="RIGHT" if "RIGHT" in s else "LEFT"
    for pair in ("ZERO_AND_THREE","ONE_AND_THREE","ZERO_AND_TWO","ONE_AND_TWO","ZERO_AND_ONE","TWO_AND_THREE"):
        if pair in s: return pair,h
    return None,h
def psd_contact(e):
    h="RIGHT" if "Right" in str(e.get("Hemisphere")) else "LEFT"
    return str(e.get("SensingElectrodes")).split(".")[-1], h

surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
CENTERS=np.arange(5.0,46.0,5.0)  # 5..45 Hz band centers
HALF=2.5
def lfpmag_bandpower(lf,lm,c):
    band=(lf>=c-HALF)&(lf<c+HALF)
    v=lm[band]; v=v[v>0]
    return float(np.sum(v**2)) if v.size else np.nan  # sum squared in-band magnitude (matches TD-transform def)

rows=[]  # (contact,hemi,center, td_bp, psd_bp)
for s in surveys:
    D=s.get("Data"); fs=s.get("SamplingRate"); chans=s.get("ChannelNames"); desc=s.get("Descriptor")
    if not (isinstance(D,np.ndarray) and D.ndim==2 and isinstance(chans,list) and isinstance(desc,dict)): continue
    # build PSD lookup by (contact,hemi)
    psdmap={}
    for e in (desc.get("MedtronicPSD") or []):
        if not isinstance(e,dict): continue
        lf=np.asarray(e.get("LFPFrequency",[]),float); lm=np.asarray(e.get("LFPMagnitude",[]),float)
        if lf.size==100 and lm.size==100:
            psdmap[psd_contact(e)]=(lf,lm)
    for ci,ch in enumerate(chans):
        key=td_chan_to_contact(ch)
        if key not in psdmap: continue
        col=np.asarray(D[:,ci],float)
        if col.size < int(fs): continue
        lf,lm=psdmap[key]
        for c in CENTERS:
            tdbp=analytics.td_transform_band_power(col, fs, float(c), half_hz=HALF)  # 50% overlap median
            pbp=lfpmag_bandpower(lf,lm,c)
            if np.isfinite(tdbp) and np.isfinite(pbp) and tdbp>0 and pbp>0:
                rows.append((key[0],key[1],float(c),float(tdbp),float(pbp)))
print(f"paired (contact,center) bandpower points: {len(rows)}")
td=np.array([r[3] for r in rows]); psd=np.array([r[4] for r in rows])
lx=np.log(td); ly=np.log(psd)
res=sm.OLS(ly, sm.add_constant(lx)).fit()
ci=res.conf_int()
print(f"GLOBAL loglog: PSD_bp = exp({res.params[0]:.3f})*TD_bp^{res.params[1]:.3f}  R2={res.rsquared:.3f} r={np.sqrt(res.rsquared):.3f}")
print(f"  slope 95%CI=[{ci[1][0]:.3f},{ci[1][1]:.3f}]  n={td.size}")
# per-center fit (is the law band-dependent?)
print("per-center:")
import collections
bycen=collections.defaultdict(list)
for r in rows: bycen[r[2]].append((r[3],r[4]))
for c in sorted(bycen):
    pts=bycen[c]; 
    if len(pts)<10: continue
    a=np.log([p[0] for p in pts]); b=np.log([p[1] for p in pts])
    rr=sm.OLS(b,sm.add_constant(a)).fit()
    print(f"  {c:4.0f}Hz n={len(pts):4d} slope={rr.params[1]:.3f} r={np.sqrt(max(rr.rsquared,0)):.3f} ratio_gm={np.exp(np.mean(b-a)):.3f}")
