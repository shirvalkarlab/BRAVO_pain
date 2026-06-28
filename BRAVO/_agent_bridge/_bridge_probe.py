import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import analytics
UID="2e3c75c00d7f4f37b53a048d195f11da"

def ck(s): return str(s).split(".")[-1]
sur=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
print("=== B. Montage-survey TD vs device-PSD band power (per contact-band) ===")
xs,ys=[],[]
for r in sur:
    chans=list(r.get("ChannelNames",[])); data=np.asarray(r.get("Data"))
    fs=float(r.get("SamplingRate",250.0))
    mp=(r.get("Descriptor") or {}).get("MedtronicPSD") or []
    if data.ndim!=2: continue
    for entry in mp:
        if not isinstance(entry,dict): continue
        f=np.asarray(entry.get("LFPFrequency") or [],float)
        mag=np.asarray(entry.get("LFPMagnitude") or [],float)
        pk=entry.get("PeakFrequencyInHertz")
        if f.size==0 or mag.size==0 or pk is None: continue
        hemi=ck(entry.get("Hemisphere","")); tok=ck(entry.get("SensingElectrodes",""))
        ci=None
        for j,cn in enumerate(chans):
            CN=str(cn).upper()
            if hemi.upper() in CN and ("ZERO" in CN or tok.split("_")[0] in CN):
                ci=j; break
        if ci is None or ci>=data.shape[1]: continue
        td=data[:,ci].astype(float)
        if np.sum(np.isfinite(td))<256: continue
        tdbp=analytics.td_transform_band_power(td, fs, float(pk))
        if not np.isfinite(tdbp) or tdbp<=0: continue
        bmask=(f>=pk-2.5)&(f<=pk+2.5)
        if bmask.sum()==0: continue
        psdbp=float(np.sum(mag[bmask]**2))
        if psdbp<=0: continue
        xs.append(tdbp); ys.append(psdbp)
xs=np.array(xs); ys=np.array(ys); n=xs.size
print(f"  paired contact-bands: {n}")
if n>10:
    lx,ly=np.log(xs),np.log(ys); slope,inter=np.polyfit(lx,ly,1); r=np.corrcoef(lx,ly)[0,1]
    print(f"  log-log: PSDbp = exp({inter:.3f}) * TDbp^{slope:.3f}   r={r:.4f}")
    print(f"  median ratio PSDbp/TDbp = {np.median(ys/xs):.4g}  (if slope~1 -> single bridge factor)")

print("\n=== C. units: event FFTBinData vs montage LFPMagnitude ===")
pe=bs._load_patient_events(UID)
ev=np.concatenate([np.asarray(m,float) for e in pe[:80] for _,m in e["psds"]]) if pe else np.array([])
mg=np.concatenate([np.asarray(en["LFPMagnitude"],float) for r in sur[:80]
                   for en in ((r.get("Descriptor") or {}).get("MedtronicPSD") or []) if isinstance(en,dict) and en.get("LFPMagnitude")])
print(f"  event FFTBinData: min={ev.min():.3f} max={ev.max():.3f} mean={ev.mean():.3f} frac_neg={np.mean(ev<0):.3f}")
print(f"  montage LFPMag  : min={mg.min():.3f} max={mg.max():.3f} mean={mg.mean():.3f} frac_neg={np.mean(mg<0):.3f}")
