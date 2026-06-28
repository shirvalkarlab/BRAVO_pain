import os, sys, numpy as np, datetime as dt
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.bravo_service import models, PATIENT_EVENT_TYPE
UID="2e3c75c00d7f4f37b53a048d195f11da"
P=models.Participant.find(uid=UID); SF=models.SourceFile.find_all(owner=P)

# Where does montage LFPMagnitude live? Survey has Descriptor.MedtronicPSD with LFPMagnitude(100,) + LFPFrequency(100,)
surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
print(f"surveys: {len(surveys)}")
s=surveys[0]
desc=s.get("Descriptor")
print("survey Descriptor keys:", list(desc.keys()) if isinstance(desc,dict) else type(desc))
mpsd = desc.get("MedtronicPSD") if isinstance(desc,dict) else None
if isinstance(mpsd,list) and mpsd:
    e0=mpsd[0]
    print("MedtronicPSD[0] keys:", list(e0.keys()))
    print("  Hemisphere:", e0.get("Hemisphere"), "SensingElectrodes:", e0.get("SensingElectrodes"))
    lf=np.asarray(e0.get("LFPFrequency",[]),float); lm=np.asarray(e0.get("LFPMagnitude",[]),float)
    print(f"  LFPFrequency: n={lf.size} [{lf.min():.1f}..{lf.max():.1f}]" if lf.size else "  no LFPFreq")
    print(f"  LFPMagnitude: n={lm.size} min={lm.min():.4f} max={lm.max():.4f} frac_neg={np.mean(lm<0):.3f}" if lm.size else "  no LFPMag")
    print(f"  n MedtronicPSD entries: {len(mpsd)}")
