import os, sys, numpy as np, datetime as dt, bisect, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.bravo_service import models, PATIENT_EVENT_TYPE
UID="2e3c75c00d7f4f37b53a048d195f11da"
P=models.Participant.find(uid=UID); SF=models.SourceFile.find_all(owner=P)

# --- harvest survey MedtronicPSD blocks: (t, channel, LFPMagnitude[100]) ---
def hemi_contact(hemi, sense):
    h = "RIGHT" if "Right" in str(hemi) else "LEFT"
    s=str(sense or "")
    pair = ("ZERO_THREE" if "ZERO_AND_THREE" in s else "ONE_THREE" if "ONE_AND_THREE" in s
            else "ZERO_TWO" if "ZERO_AND_TWO" in s else "ONE_TWO" if "ONE_AND_TWO" in s else None)
    return f"{pair}_{h}" if pair else None

surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
srows=[]
for s in surveys:
    t=bs.availability._to_epoch(s.get("StartTime"))
    desc=s.get("Descriptor"); 
    if t is None or not isinstance(desc,dict): continue
    for e in (desc.get("MedtronicPSD") or []):
        if not isinstance(e, dict): continue
        ch=hemi_contact(e.get("Hemisphere"), e.get("SensingElectrodes"))
        lm=np.asarray(e.get("LFPMagnitude",[]),float); lf=np.asarray(e.get("LFPFrequency",[]),float)
        if ch and lm.size==100 and lf.size==100:
            srows.append((float(t),ch,lf,lm))
print(f"survey PSD blocks: {len(srows)}")

# --- harvest event FFTBinData blocks: (t, channel, Frequency[100], FFTBinData[100], name) ---
erows=[]
for r in models.Recording.find_all(source__in=SF,type=PATIENT_EVENT_TYPE):
    md=getattr(r,'metadata',None); nm=(getattr(r,'name','') or '')
    if not isinstance(md,dict): continue
    for hk,hb in md.items():
        if not isinstance(hb,dict): continue
        ch=bs._event_block_channel(hk, hb.get("SenseID"))
        f=hb.get("Frequency"); m=hb.get("FFTBinData")
        if ch is None or not(isinstance(f,(list,tuple)) and isinstance(m,(list,tuple)) and len(f)==len(m)==100): continue
        t=None
        if hb.get("DateTime"):
            try: t=dt.datetime.fromisoformat(str(hb["DateTime"]).replace("Z","+00:00")).timestamp()
            except: t=None
        if t is None: t=getattr(r,'date',None)
        if t is None: continue
        erows.append((float(t),ch,np.asarray(f,float),np.asarray(m,float),nm))
print(f"event FFT blocks: {len(erows)}")

# --- pair survey block <-> event block: same channel, |dt|<=tol ---
TOL=120.0  # within 2 min
# index events by channel
from collections import defaultdict
ev_by_ch=defaultdict(list)
for t,ch,f,m,nm in erows: ev_by_ch[ch].append((t,f,m,nm))
for ch in ev_by_ch: ev_by_ch[ch].sort(key=lambda x:x[0])

pairs=[]
for ts,ch,lf,lm in srows:
    cand=ev_by_ch.get(ch,[])
    if not cand: continue
    times=[c[0] for c in cand]
    i=bisect.bisect_left(times,ts)
    best=None
    for j in (i-1,i):
        if 0<=j<len(cand):
            d=abs(cand[j][0]-ts)
            if d<=TOL and (best is None or d<best[0]): best=(d,cand[j])
    if best:
        d,(te,fe,me,nm)=best
        pairs.append((ch,lf,lm,fe,me,nm,d))
print(f"survey<->event coincident pairs (|dt|<={TOL}s, same channel): {len(pairs)}")
if pairs:
    # frequency axes identical?
    ch,lf,lm,fe,me,nm,d=pairs[0]
    print(f"  sample pair: ch={ch} dt={d:.1f}s name={nm}")
    print(f"  freq axes identical: {np.allclose(lf,fe)}")
    print(f"  LFPMag[:6]={np.round(lm[:6],4)}")
    print(f"  FFTBin[:6]={np.round(me[:6],4)}")
    # bin-by-bin: is FFTBinData == LFPMagnitude - baseline (quantized)?
    diffs=[]
    for ch,lf,lm,fe,me,nm,d in pairs[:200]:
        if np.allclose(lf,fe):
            diffs.append(lm-me)  # LFPMag minus FFTBin per bin
    if diffs:
        D=np.concatenate(diffs)
        print(f"  (LFPMag - FFTBin) over {len(diffs)} pairs: median={np.median(D):.4f} mean={np.mean(D):.4f} p10={np.percentile(D,10):.4f} p90={np.percentile(D,90):.4f}")
json.dump({"n_survey":len(srows),"n_event":len(erows),"n_pairs":len(pairs)}, open("/usr/src/BRAVO/_agent_bridge/_pair_summary.json","w"))
