import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.bravo_service import models, PATIENT_EVENT_TYPE
UID="2e3c75c00d7f4f37b53a048d195f11da"
P=models.Participant.find(uid=UID); SF=models.SourceFile.find_all(owner=P)

# Pull a large sample of event FFTBinData across ALL events, characterize distribution
pce=[r for r in models.Recording.find_all(source__in=SF,type=PATIENT_EVENT_TYPE)]
allvals=[]; neg_frac_per_event=[]; n_events_with_neg=0; peak0_count=0; nev=0
for r in pce:
    md=getattr(r,'metadata',None)
    if not isinstance(md,dict): continue
    for hb in md.values():
        if not isinstance(hb,dict): continue
        m=hb.get('FFTBinData'); f=hb.get('Frequency')
        if not (isinstance(m,(list,tuple)) and len(m)>0): continue
        a=np.asarray(m,float); fr=np.asarray(f,float)
        allvals.append(a); nev+=1
        nf=float(np.mean(a<0)); neg_frac_per_event.append(nf)
        if (a<0).any(): n_events_with_neg+=1
        if a.size and int(np.argmax(a))<=1: peak0_count+=1
allv=np.concatenate(allvals)
print(f"event-PSD hemisphere-blocks sampled: {nev}")
print(f"  global min/max/mean: {allv.min():.4f} / {allv.max():.4f} / {allv.mean():.4f}")
print(f"  global frac negative bins: {np.mean(allv<0):.3f}")
print(f"  blocks with >=1 negative bin: {n_events_with_neg}/{nev} ({100*n_events_with_neg/nev:.1f}%)")
print(f"  median per-block neg-frac: {np.median(neg_frac_per_event):.3f}  p90: {np.percentile(neg_frac_per_event,90):.3f}")
print(f"  blocks peaking at bin 0/1 (1/f or DC): {peak0_count}/{nev}")
# Distribution of values: are negatives small? characterize the value histogram
qs=[0,1,5,25,50,75,95,99,100]
print("  value percentiles:", {q: round(float(np.percentile(allv,q)),4) for q in qs})
# Are the values QUANTIZED? (log-domain often shows discrete steps)
u=np.unique(np.round(allv,4))
print(f"  unique rounded values: {u.size} (first 12: {u[:12]})")
# step between smallest positive values -> hints at a log/quantization base
posu=u[u>0][:8]
print(f"  smallest positive uniques: {posu}")
if posu.size>=3:
    print(f"  ratios between consecutive small positives: {np.round(posu[1:]/posu[:-1],4)}")
