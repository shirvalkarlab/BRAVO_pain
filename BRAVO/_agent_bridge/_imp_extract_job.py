import sys; sys.path.insert(0, "/usr/src/BRAVO")
import os, django, json, csv
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
django.setup()
from Server import models
imps = list(models.DBSEvent.find_all(type__endswith="Impedance"))
rows=[]
for ev in imps:
    info = ev.get_info(data=True)
    date = info.get("Date")
    rec = info.get("Recording") or []
    if not rec: continue
    md = rec[0].get("Metadata") or {}
    R = md.get("Right") or {}
    lead = R.get("LeadModel")
    B = R.get("Bipolar")
    status = md.get("Status")
    z_0_7 = z_0_3 = None
    if B and len(B)>=8 and len(B[0])>=8:
        z_0_7 = B[0][7]   # ring0-ring3 on 8-contact directional
    if B and len(B)>=4 and len(B[0])>=4:
        z_0_3 = B[0][3]
    rows.append((date, lead, status, z_0_7, z_0_3))
# dedup identical (date,z) and sort
seen=set(); uniq=[]
for r in sorted(rows, key=lambda x:(x[0] or 0)):
    k=(r[0], r[3])
    if k in seen: continue
    seen.add(k); uniq.append(r)
out="/usr/src/BRAVO/_agent_bridge/imp_series_RCS08.csv"
with open(out,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["date_utc","lead","status","right_0_3_bipolar_ohm","right_0_3idx_ohm"])
    for r in uniq: w.writerow(r)
print("TOTAL_EVENTS", len(rows), "UNIQUE", len(uniq))
import numpy as np
zs=[r[3] for r in uniq if r[3]]
print("Z_0_7 n=%d min=%.0f median=%.0f max=%.0f"%(len(zs),min(zs),np.median(zs),max(zs)))
print("DATE_RANGE", min(r[0] for r in uniq), max(r[0] for r in uniq))
print("LEADS", set(r[1] for r in uniq))
