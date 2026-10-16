"""Pull every BrainSense streaming recording (TD 250 Hz + 2 Hz band power/current) out of the
device exports, with the pulse width / rate / contacts in force on the sensed side.
Writes one npz per unique (channel, first packet time); file names carry no patient names."""
import json, sys, glob, os, hashlib
from multiprocessing import Pool
import numpy as np
D = sys.argv[1]; OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

def side_of(ch):
    return "Left" if ch.endswith("LEFT") else "Right"

def contacts(state):
    out = []
    for e in state.get("ElectrodeState", []):
        nm = e["Electrode"].split(".")[-1]; r = e["ElectrodeStateResult"].split(".")[-1]
        out.append(nm + ("-" if r == "Negative" else "+" if r == "Positive" else "?"))
    return " ".join(out)

def one(path):
    rows = []
    try:
        j = json.load(open(path))
    except Exception as ex:
        return [("ERR", os.path.basename(path)[-30:], str(ex))]
    lfps = j.get("BrainSenseLfp") or []
    for td in j.get("BrainSenseTimeDomain") or []:
        ch = td["Channel"]; t0 = td["FirstPacketDateTime"]; sd = side_of(ch)
        x = np.asarray(td["TimeDomainData"], float)
        ticks = [int(v) for v in td["TicksInMses"].strip(",").split(",") if v]
        psz = [int(v) for v in td["GlobalPacketSizes"].strip(",").split(",") if v]
        # matching band-power stream: same first packet time, channel list containing ch
        m = [b for b in lfps if b["FirstPacketDateTime"] == t0 and ch in b["Channel"].split(",")]
        if not m:
            m = [b for b in lfps if abs(np.datetime64(b["FirstPacketDateTime"][:19]) - np.datetime64(t0[:19])) <= np.timedelta64(2, 's') and ch in b["Channel"].split(",")]
        if not m:
            rows.append(("NOLFP", ch, t0, len(x))); continue
        b = m[0]; ts = b["TherapySnapshot"]; st = ts.get(sd, {})
        other = ts.get("Right" if sd == "Left" else "Left", {})
        ld = b["LfpData"]
        bt = np.array([d["TicksInMs"] for d in ld], float)
        ma = np.array([d.get(sd, {}).get("mA", np.nan) for d in ld], float)
        lfp = np.array([d.get(sd, {}).get("LFP", np.nan) for d in ld], float)
        ma_o = np.array([d.get("Right" if sd == "Left" else "Left", {}).get("mA", np.nan) for d in ld], float)
        key = hashlib.sha1((ch + t0).encode()).hexdigest()[:12]
        meta = dict(channel=ch, side=sd, t0=t0, pw=st.get("PulseWidthInMicroSecond"),
                    rate=st.get("RateInHertz"), sense_hz=st.get("FrequencyInHertz"),
                    contacts=contacts(st), other_pw=other.get("PulseWidthInMicroSecond"),
                    other_rate=other.get("RateInHertz"), group=ts.get("ActiveGroup"),
                    blank_us=ts.get("SensingBlankingDurationInMicroseconds"),
                    hp=ts.get("HighPassFilterInHertz"), gain=td.get("Gain"),
                    adaptive=st.get("AdaptiveTherapyStatus"), session=j.get("SessionDate"),
                    td_tick0=ticks[0] if ticks else None, n=len(x))
        rows.append(("OK", key, meta, x, bt, ma, lfp, ma_o, np.array(ticks), np.array(psz)))
    return rows

if __name__ == "__main__":
    fs = sorted(glob.glob(os.path.join(D, "*.json")))
    best = {}; errs = []; nolfp = 0
    with Pool(10) as p:
        for rows in p.imap_unordered(one, fs, chunksize=2):
            for r in rows:
                if r[0] == "ERR": errs.append(r[1:]); continue
                if r[0] == "NOLFP": nolfp += 1; continue
                _, key, meta, x, bt, ma, lfp, ma_o, tk, ps = r
                if key not in best or len(x) > best[key][1]["n"]:
                    best[key] = (key, meta, x, bt, ma, lfp, ma_o, tk, ps)
    import pandas as pd
    recs = []
    for key, meta, x, bt, ma, lfp, ma_o, tk, ps in best.values():
        np.savez_compressed(os.path.join(OUT, key + ".npz"), x=x, bt=bt, ma=ma, lfp=lfp, ma_o=ma_o, tk=tk, ps=ps)
        meta = dict(meta); meta["key"] = key
        meta["ma_min"] = float(np.nanmin(ma)) if len(ma) else np.nan
        meta["ma_max"] = float(np.nanmax(ma)) if len(ma) else np.nan
        recs.append(meta)
    pd.DataFrame(recs).to_csv(os.path.join(OUT, "_index.csv"), index=False)
    print("files", len(fs), "unique TD recordings", len(best), "no matching band power", nolfp, "errors", len(errs))
    for e in errs[:5]: print(e)
