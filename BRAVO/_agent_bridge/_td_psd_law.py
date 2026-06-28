import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.routines import analytics
import statsmodels.api as sm
UID="2e3c75c00d7f4f37b53a048d195f11da"

# Montage survey: TD Data (250Hz, channels) + Descriptor.MedtronicPSD[].LFPMagnitude (device PSD per contact)
# We need to match a TD CHANNEL to a device-PSD CONTACT block within the same survey recording.
surveys=bs._load_recordings(UID,["MedtronicBrainSenseSurvey"])
print(f"surveys: {len(surveys)}")
s=surveys[0]
print("TD channels:", s.get("ChannelNames"))
desc=s.get("Descriptor"); mp=[e for e in (desc.get("MedtronicPSD") or []) if isinstance(e,dict)]
print("PSD contacts:", [(str(e.get('Hemisphere')).split('.')[-1], str(e.get('SensingElectrodes')).split('.')[-1]) for e in mp][:6])
print("TD Data shape:", getattr(s.get('Data'),'shape',None))
