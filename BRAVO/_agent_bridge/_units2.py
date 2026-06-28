import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
UID="2e3c75c00d7f4f37b53a048d195f11da"

# 1) Does a survey recording that's TIME-COINCIDENT with an event let us compare FFTBinData vs LFPMagnitude
#    on the same signal? If FFTBinData ~ f(LFPMagnitude) we can identify the transform.
pe=bs._load_patient_events(UID)
sur=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
# grab one event PSD and look at its full shape vs a survey LFPMagnitude on similar band
e=pe[0]; f,m=e["psds"][0]; f=np.asarray(f,float); m=np.asarray(m,float)
print("event FFTBinData stats: n=%d  f=[%.2f..%.2f]  vals min=%.4f max=%.4f mean=%.4f"%(m.size,f.min(),f.max(),m.min(),m.max(),m.mean()))
# Is it 10*log10? invert and see if it becomes a clean peaked spectrum
lin = 10**(m/10.0)
print("if 10log10 -> linear: min=%.4g max=%.4g  peak@%.1fHz"%(lin.min(),lin.max(),f[np.argmax(lin)]))
# Is it already linear magnitude? then negatives are impossible -> rule out
print("negatives present -> not linear magnitude/power. frac_neg=%.3f"%float((m<0).mean()))
# Medtronic FFTBinData is documented as 'RMS µV' AFTER a Hann + Yptp scaling; but negative => it's been
# baseline/log transformed in BRAVO ingest. Find where FFTBinData is populated in ingest.
