import os, sys, numpy as np
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO"); import django; django.setup()
sys.path.insert(0,"/usr/src/BRAVO/modules")
from Biomarkers import bravo_service as bs
from Biomarkers.bravo_service import models, PATIENT_EVENT_TYPE
from collections import Counter
UID="2e3c75c00d7f4f37b53a048d195f11da"
P=models.Participant.find(uid=UID); SF=models.SourceFile.find_all(owner=P)

# 1) What recording TYPES exist, and counts (the real taxonomy in the DB)
allrec=list(models.Recording.find_all(source__in=SF))
print("=== all Recording.type counts ===")
for t,c in Counter(getattr(r,'type','?') for r in allrec).most_common(): print(f"  {c:5d}  {t}")

# 2) NeuralActivitySnapshot — are these the 'Streaming' snapshots? check their names/metadata
nas=[r for r in allrec if getattr(r,'type','')=="NeuralActivitySnapshot"]
print(f"\n=== NeuralActivitySnapshot: {len(nas)} ===")
print("  names:", Counter((getattr(r,'name','') or '').strip() for r in nas).most_common(8))

# 3) PatientControllerEvent 'Streaming' — do they carry FFTBinData PSDs in metadata?
pce=[r for r in allrec if getattr(r,'type','')==PATIENT_EVENT_TYPE]
strm=[r for r in pce if (getattr(r,'name','') or '').strip().lower()=='streaming']
print(f"\n=== PatientControllerEvent 'Streaming': {len(strm)} ===")
withpsd=0; sample=None
for r in strm:
    md=getattr(r,'metadata',None)
    if isinstance(md,dict):
        for hb in md.values():
            if isinstance(hb,dict) and hb.get('FFTBinData') and hb.get('Frequency'):
                withpsd+=1; 
                if sample is None: sample=(np.asarray(hb['Frequency'],float),np.asarray(hb['FFTBinData'],float))
                break
print(f"  Streaming events carrying FFTBinData PSD: {withpsd}/{len(strm)}")
if sample is not None:
    f,m=sample; print(f"  sample PSD: bins={f.size} f=[{f.min():.1f}..{f.max():.1f}] pow=[{m.min():.3f}..{m.max():.3f}]")

# 4) The mislabel: which loader produces "Montage PSD" and does it pick up Streaming?
print("\n=== who emits name='Montage PSD'? ===")
import subprocess
print(subprocess.run(["grep","-rn","Montage PSD","/usr/src/BRAVO/modules/Biomarkers/"],capture_output=True,text=True).stdout[:800])
