import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"
pe=bs._load_patient_events(UID)
# stack a few event PSDs and characterize: any negatives? dynamic range? compare to survey LFPMagnitude
neg=0; tot=0; mins=[]; maxs=[]
for e in pe[:50]:
    for f,m in e["psds"]:
        m=np.asarray(m,float); neg+=int((m<0).sum()); tot+=m.size; mins.append(np.nanmin(m)); maxs.append(np.nanmax(m))
print(f"event FFTBinData: {neg}/{tot} negative bins; min range [{min(mins):.3g},{max(mins):.3g}] max range [{min(maxs):.3g},{max(maxs):.3g}]")
# survey LFPMagnitude for comparison (known to be µV magnitude, all >=0)
sur=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
mp=sur[0]["Descriptor"]["MedtronicPSD"][0]
lm=np.asarray(mp["LFPMagnitude"],float)
print(f"survey LFPMagnitude: min={lm.min():.3g} max={lm.max():.3g} (µV magnitude, >=0)")
# is FFTBinData maybe 10*log10 or 20*log10? a linear µV^2 spectrum at a 20Hz peak would be strongly peaked.
e=pe[0]; f,m=e["psds"][0]; f=np.asarray(f,float); m=np.asarray(m,float)
pk=f[np.nanargmax(m)]
print(f"sample event '{e['name']}': peak at {pk:.1f} Hz, value={np.nanmax(m):.3g}; values at 5/20/60Hz:",
      [round(float(m[np.argmin(abs(f-x))]),3) for x in (5,20,60)])
