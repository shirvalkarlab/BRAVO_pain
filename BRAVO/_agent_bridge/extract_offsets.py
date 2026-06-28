import os, sys, django, numpy as np, csv, collections
os.environ.setdefault("DJANGO_SETTINGS_MODULE","BRAVO.settings")
sys.path.insert(0,"/usr/src/BRAVO")
django.setup()
from modules.Biomarkers import bravo_service as bs
from modules.Biomarkers.routines import availability as av

uid="2e3c75c00d7f4f37b53a048d195f11da"
HALF=2.5; LINE_LO,LINE_HI=58.5,61.5

def band_power(freq,power,center,half=HALF):
    freq=np.asarray(freq,float); power=np.asarray(power,float).copy()
    inb=(freq>=LINE_LO)&(freq<=LINE_HI)
    if inb.any() and (~inb).sum()>=2:
        power[inb]=np.interp(freq[inb],freq[~inb],power[~inb])
    m=(freq>=center-half)&(freq<center+half)
    if m.sum()<2: return np.nan
    return float(np.trapezoid(power[m],freq[m]))

rows,nc,ncomp=bs._assemble_psd_rows_cached(uid)
psd_by_ch=collections.defaultdict(list)
for r in rows:
    psd_by_ch[r['channel']].append((float(r['t']),r['freq'],r['power']))
for ch in psd_by_ch: psd_by_ch[ch].sort(key=lambda x:x[0])

chronic=bs._load_recordings(uid,bs.CHRONIC_TYPES)
pdl=bs._load_recordings(uid,bs.POWERDOMAIN_TYPES)
lsb=av.lsb_series(chronic,pdl)

# For each PSD epoch: find NEAREST LSB sample (signed offset = t_lsb - t_psd, seconds),
# plus the LSB center_hz at that nearest sample, plus band power at that center.
out=[]
for ch,psds in psd_by_ch.items():
    if ch not in lsb: continue
    L=lsb[ch]
    ly=np.asarray(L['y'],float); lt=np.asarray(L['t'],float); lc=np.asarray(L['center_hz'],float)
    ok=np.isfinite(ly)&(ly>0)&np.isfinite(lt)
    ly,lt,lc=ly[ok],lt[ok],lc[ok]
    order=np.argsort(lt); ly,lt,lc=ly[order],lt[order],lc[order]
    if len(lt)<20: continue
    for (tp,fr,pw) in psds:
        j=int(np.searchsorted(lt,tp))
        cands=[k for k in (j-1,j) if 0<=k<len(lt)]
        if not cands: continue
        k=min(cands,key=lambda k:abs(lt[k]-tp))
        off=lt[k]-tp           # signed seconds
        cen=lc[k] if np.isfinite(lc[k]) else np.nan
        if not np.isfinite(cen): continue
        bp=band_power(fr,pw,cen)
        if not (np.isfinite(bp) and bp>0): continue
        out.append((ch,tp,float(cen),bp,float(ly[k]),off))

with open("/usr/src/BRAVO/_agent_bridge/psd_lsb_nearest.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["channel","t_psd","center_hz","psd_bandpower_uV2","lsb_nearest","offset_s"])
    w.writerows(out)
print("wrote nearest pairs:",len(out))
# quick offset census
ao=np.abs([r[5] for r in out])
for thr,lab in [(0,"exact 0s"),(30,"<=30s"),(60,"<=1min"),(300,"<=5min"),(600,"<=10min"),(1800,"<=30min"),(3600,"<=1h"),(7200,"<=2h")]:
    print(f"  {lab:<10}: {(ao<=thr).sum()}")
