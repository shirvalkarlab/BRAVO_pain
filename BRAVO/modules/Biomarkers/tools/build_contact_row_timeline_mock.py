#!/usr/bin/env python3
"""
Design mock-up generator: chronic + streaming LFP timeline laid out by RECORDING CONTACT.

WHAT THIS DEMONSTRATES (the design that motivated the BiomarkerTimeline rework):
  - The chronic 24/7 LFP is NOT a single fixed channel. Over time the Percept is reprogrammed to
    sense from different bipolar contacts (e.g. 0-3, 1-3, 0-2) AND different center frequencies.
    Stamping one channel/frequency per recording hides that history.
  - Here every chronic trend point is assigned to whichever bipolar contact was the PROGRAMMED
    sensing channel at its timestamp (read from GroupHistory), so the signal lives in the row of
    the contact it truly came from. One row per (hemisphere, contact).
  - The frequency ribbon under each row shows the real programmed-band history (from GroupHistory),
    NOT a single 'latest' value -- so the center frequency leaves the title entirely.
  - On-demand streaming (BrainSenseLfp) is folded into the SAME contact rows, distinguished from
    chronic by mark: chronic = thin continuous line, streaming = diamond + vertical range bar
    (p10-p90 of each brief recording). Streaming contact identity comes from TherapySnapshot.
  - Active-window shading tints each contact's row only where it was the programmed channel.

Standalone REVIEW/DESIGN artifact rendered against the real RCS08 export set; reads the raw JSONs
directly (not the DB) and writes an interactive Plotly HTML + a PNG. Reference for the component
port in Client/src/views/Reports/Biomarkers/BiomarkerTimeline.js.

Usage:
    python3 build_contact_row_timeline_mock.py \
        --jsons "/path/to/RCS008 jsons" --out ./optB_contact_rows

Requires: plotly, kaleido==0.2.1 (PNG export uses the headless-Chromium flags set below), numpy.
"""
import os, sys, glob, json, argparse
import numpy as np
from datetime import datetime
import plotly.graph_objects as go
import plotly.io as pio

# Headless-Chromium flags required for kaleido PNG export on a sandbox / no-GPU host.
try:
    pio.kaleido.scope.chromium_args = ("--single-process", "--no-zygote", "--no-sandbox",
                                       "--disable-gpu", "--disable-dev-shm-usage")
except Exception:
    pass

# ---------------------------------------------------------------- visual identity
HEMI = {
    "Left":  {"region": "GPi", "base": "#4B2E83", "accent": "#5E3C99"},
    "Right": {"region": "VIM", "base": "#0B6B2E", "accent": "#117733"},
}
# Distinct shade per contact within a hemisphere family.
CONTACT_SHADE = {
    "Left":  {"0-3": "#4B2E83", "1-3": "#7B5FB0", "0-2": "#B49BD8"},
    "Right": {"0-3": "#0B6B2E", "1-3": "#3E9C62", "0-2": "#86C9A2"},
}
# Fixed categorical frequency palette (snapped Percept FFT bins) -- stable color per frequency.
FREQ_PAL = {7.8: "#332288", 8.8: "#0072B2", 9.8: "#56B4E9", 10.7: "#009E73",
            11.7: "#94C973", 12.7: "#E69F00", 13.7: "#D55E00", 22.5: "#AA4499",
            23.4: "#882255", 24.4: "#CC6677", 26.4: "#CC79A7", 28.3: "#DDCC77"}
BIN = 250.0 / 256.0
# Contact map: GroupHistory uses ZERO_AND_THREE; streaming uses ZERO_THREE_<HEMI>.
CMAP_GROUP = {"ZERO_AND_THREE": "0-3", "ONE_AND_THREE": "1-3", "ZERO_AND_TWO": "0-2",
              "ZERO_AND_ONE": "0-1", "TWO_AND_THREE": "2-3", "ONE_AND_TWO": "1-2"}
CMAP_STREAM = {"ZERO_THREE": "0-3", "ONE_THREE": "1-3", "ZERO_TWO": "0-2",
               "ZERO_ONE": "0-1", "TWO_THREE": "2-3", "ONE_TWO": "1-2"}
CORD = ["0-3", "1-3", "0-2", "0-1", "2-3", "1-2", "?"]
SIX_H = 6 * 3600
SENTINEL = 1e6  # LFP power is physically << 1e6; larger values are uint32 no-data sentinels.


def snap(hz):
    if hz is None:
        return None
    try:
        return round(round(float(hz) / BIN) * BIN, 1)
    except (TypeError, ValueError):
        return None


def fcol(hz):
    s = snap(hz)
    if s is None:
        return "#BDBDBD"
    k = min(FREQ_PAL, key=lambda x: abs(x - s))
    return FREQ_PAL[k] if abs(k - s) < 0.6 else "#9E9E9E"


def fmt_contact(c):
    """'0-3' -> '0⁻3⁺' (lower contact cathode, higher anode, no separator dash)."""
    import re
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(c))
    return f"{m.group(1)}\u207B{m.group(2)}\u207A" if m else str(c)


def darken(hexc, f=0.62):
    h = hexc.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"


def _parse(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


# ---------------------------------------------------------------- data extraction
def configs_from_groups(groups):
    """{hemi: (contact, freq)} for the active group (else any) of one GroupHistory snapshot."""
    if not isinstance(groups, list):
        return {}
    cand = [g for g in groups if isinstance(g, dict) and g.get("ActiveGroup")] or \
           [g for g in groups if isinstance(g, dict)]
    out = {}
    for g in cand:
        ps = g.get("ProgramSettings") or {}
        for ch in ps.get("SensingChannel", []) or []:
            if not isinstance(ch, dict):
                continue
            hraw = str(ch.get("HemisphereLocation", ""))
            hemi = "Left" if "Left" in hraw else ("Right" if "Right" in hraw else None)
            if not hemi:
                continue
            chan = CMAP_GROUP.get(str(ch.get("Channel", "")).replace("SensingElectrodeConfigDef.", ""), "?")
            ss = ch.get("SensingSetup") if isinstance(ch.get("SensingSetup"), dict) else ch
            freq = None
            for k in ("FrequencyInHertz", "Frequency"):
                v = ss.get(k)
                if v:
                    freq = round(float(v), 2)
                    break
            if hemi not in out:
                out[hemi] = (chan, freq)
    return out


def contact_from_stream_sc(sc, hemi):
    if not sc:
        return None
    s = str(sc).replace("SensingChannelDef.", "").replace("_" + hemi.upper(), "")
    return CMAP_STREAM.get(s)


def load_dataset(jsons_dir):
    """Read every RCS08 JSON; return (sched, chronic, stream) keyed by hemisphere."""
    files = sorted(glob.glob(os.path.join(jsons_dir, "*.json")) +
                   glob.glob(os.path.join(jsons_dir, "Stage 1", "*.json")))
    sched = {"Left": [], "Right": []}
    chronic = {"Left": [], "Right": []}
    stream = {"Left": [], "Right": []}
    for f in files:
        try:
            J = json.load(open(f))
        except Exception:
            continue
        # GroupHistory -> dated (contact, freq) schedule per hemisphere
        for e in (J.get("GroupHistory") or []):
            if not isinstance(e, dict):
                continue
            sd = e.get("SessionDate")
            if not sd:
                continue
            cfg = configs_from_groups(e.get("Groups"))
            for hemi in ("Left", "Right"):
                if hemi in cfg:
                    sched[hemi].append((_parse(sd).timestamp(), cfg[hemi][0], cfg[hemi][1]))
        # Chronic LFP trend points
        tl = (J.get("DiagnosticData") or {}).get("LFPTrendLogs") or {}
        for hk, hemi in [("HemisphereLocationDef.Left", "Left"), ("HemisphereLocationDef.Right", "Right")]:
            h = tl.get(hk)
            if not isinstance(h, dict):
                continue
            for blk in h.values():
                if isinstance(blk, list):
                    for r in blk:
                        d, lfp = r.get("DateTime"), r.get("LFP")
                        if d is None or lfp is None:
                            continue
                        chronic[hemi].append((_parse(d).timestamp(), float(lfp)))
        # On-demand streaming (BrainSenseLfp); median/p10/p90, sentinels dropped
        for r in (J.get("BrainSenseLfp") or []):
            if not isinstance(r, dict):
                continue
            t0 = r.get("FirstPacketDateTime")
            if not t0:
                continue
            t = _parse(t0).timestamp()
            ts = r.get("TherapySnapshot") or {}
            ld = r.get("LfpData") or []
            for hemi in ("Left", "Right"):
                c = contact_from_stream_sc((ts.get(hemi) or {}).get("SensingChannel"), hemi)
                if c is None:
                    continue
                vals = [d[hemi]["LFP"] for d in ld
                        if isinstance(d, dict) and isinstance(d.get(hemi), dict) and "LFP" in d[hemi]]
                vals = [v for v in vals if 0 <= v < SENTINEL]
                if vals:
                    stream[hemi].append((t, c, float(np.median(vals)),
                                         float(np.percentile(vals, 10)), float(np.percentile(vals, 90))))
    for h in sched:
        sched[h] = sorted(set(sched[h]), key=lambda x: x[0])
        chronic[h] = sorted(set(chronic[h]), key=lambda x: x[0])
    return sched, chronic, stream


def cfg_at(sched, hemi, t):
    cur = None
    for ts, chan, freq in sched[hemi]:
        if ts <= t:
            cur = (chan, freq)
        else:
            break
    if cur:
        return cur
    return (sched[hemi][0][1], sched[hemi][0][2]) if sched[hemi] else ("?", None)


def build_contacts(sched, chronic, hemi):
    """contact -> {t, lfp, epochs:[(t0,t1,hz)]} for one hemisphere."""
    by = {}
    for t, lfp in chronic[hemi]:
        chan, freq = cfg_at(sched, hemi, t)
        by.setdefault(chan, {"t": [], "lfp": [], "f": []})
        by[chan]["t"].append(t)
        by[chan]["lfp"].append(lfp)
        by[chan]["f"].append(snap(freq))
    out = {}
    for chan, d in by.items():
        t = np.array(d["t"])
        lfp = np.array(d["lfp"])
        f = d["f"]
        order = np.argsort(t)
        t, lfp, f = t[order], lfp[order], [f[i] for i in order]
        ep = []
        for i in range(len(t)):
            if not ep or ep[-1][2] != f[i]:
                ep.append([t[i], t[i], f[i]])
            else:
                ep[-1][1] = t[i]
        out[chan] = {"t": t, "lfp": lfp, "epochs": ep}
    return out


def contacts_sorted(by):
    return sorted(by.keys(), key=lambda c: CORD.index(c) if c in CORD else 99)


# ---------------------------------------------------------------- render helpers
def break_gaps(t, y, max_gap=SIX_H):
    if len(t) == 0:
        return [], []
    xs = [datetime.utcfromtimestamp(t[0])]
    ys = [y[0]]
    for i in range(1, len(t)):
        if t[i] - t[i - 1] > max_gap:
            xs.append(None)
            ys.append(None)
        xs.append(datetime.utcfromtimestamp(t[i]))
        ys.append(y[i])
    return xs, ys


def robust(y, lo=0.5, hi=99.5, pad=0.08):
    y = np.asarray([v for v in y if v is not None and np.isfinite(v)])
    if len(y) == 0:
        return [0, 1]
    a, b = np.percentile(y, lo), np.percentile(y, hi)
    if b <= a:
        b = a + 1
    s = b - a
    return [a - s * pad, b + s * 0.10]


def coverage_windows(t, max_gap=2 * 86400):
    """Contiguous data-present spans for one contact's chronic timestamps (broken at >max_gap)."""
    cov = []
    for tt in t:
        if not cov or tt - cov[-1][1] > max_gap:
            cov.append([tt, tt])
        else:
            cov[-1][1] = tt
    return cov


def freq_ribbon_shapes(epochs, y0, y1, coverage=None):
    """Draw the frequency ribbon, CLIPPED to the contact's data-coverage windows so color + the Hz
    label only appear where the contact actually recorded (one contact senses at a time)."""
    shapes, anns = [], []
    for t0, t1, hz in epochs:
        if t1 < t0:
            t0, t1 = t1, t0
        # Intersect [t0,t1] with coverage -> visible sub-segments (full span when no coverage given).
        for c0, c1 in (coverage if coverage else [[t0, t1]]):
            s0, s1 = max(t0, c0), min(t1, c1)
            if s1 < s0:
                continue
            if s1 <= s0:
                s1 = s0 + 6 * 3600   # near-zero-width epoch gets a visible sliver
            shapes.append(dict(type="rect", xref="x", yref="paper",
                               x0=datetime.utcfromtimestamp(s0), x1=datetime.utcfromtimestamp(s1),
                               y0=y0, y1=y1, fillcolor=fcol(hz), line=dict(width=0.4, color="white"),
                               layer="above"))
            if (s1 - s0) > 4 * 86400 and hz:
                anns.append(dict(xref="x", yref="paper", x=datetime.utcfromtimestamp((s0 + s1) / 2),
                                 y=(y0 + y1) / 2, text=f"<b>{hz:g}</b>", showarrow=False,
                                 font=dict(size=12, color="#111"), xanchor="center", yanchor="middle"))
    return shapes, anns


# ---------------------------------------------------------------- figure
def render(sched, chronic, stream, out_base):
    rows = []
    for hemi in ("Left", "Right"):
        by = build_contacts(sched, chronic, hemi)
        for c in contacts_sorted(by):
            rows.append((hemi, c, by[c]))

    allt = np.concatenate([d["t"] for _, _, d in rows])
    gmin, gmax = datetime.utcfromtimestamp(allt.min()), datetime.utcfromtimestamp(allt.max())

    ROW_PX, RIB_PX, GAP_PX, BANNER_PX, TOPPAD, BOTPAD = 120, 24, 22, 50, 44, 56
    yb, prev, total = [], None, TOPPAD
    for hemi, c, d in rows:
        if hemi != prev:
            total += BANNER_PX
            prev = hemi
        st = total
        sb = st + ROW_PX
        rt = sb + 2
        rb = rt + RIB_PX
        yb.append((hemi, c, d, st, sb, rt, rb))
        total = rb + GAP_PX
    total += BOTPAD
    H = total
    yd = lambda px: 1 - px / H

    fig = go.Figure()
    shapes, anns, prev = [], [], None
    for idx, (hemi, c, d, st, sb, rt, rb) in enumerate(yb, 1):
        Hc = HEMI[hemi]
        col = CONTACT_SHADE[hemi][c]
        scol = darken(col)
        yref, yax = f"y{idx}", f"yaxis{idx}"
        if hemi != prev:
            anns.append(dict(xref="paper", yref="paper", x=0, y=yd(st) + 0.022,
                             text=f"<b>{hemi.upper()} HEMISPHERE</b> · {Hc['region']}", showarrow=False,
                             font=dict(size=21, color=Hc["base"]), xanchor="left", yanchor="bottom"))
            prev = hemi
        sv = [x for x in stream[hemi] if x[1] == c]
        yvals = list(d["lfp"]) + [x[2] for x in sv] + [x[4] for x in sv]
        yr = robust(yvals)
        # active-window tint
        t = d["t"]
        if len(t):
            spans, s0, pv = [], t[0], t[0]
            for tt in t[1:]:
                if tt - pv > 2 * 86400:
                    spans.append((s0, pv))
                    s0 = tt
                pv = tt
            spans.append((s0, pv))
            for a, b in spans:
                shapes.append(dict(type="rect", xref="x", yref="paper",
                                   x0=datetime.utcfromtimestamp(a), x1=datetime.utcfromtimestamp(b),
                                   y0=yd(sb), y1=yd(st), fillcolor=col, opacity=0.06,
                                   line=dict(width=0), layer="below"))
        xs, ys = break_gaps(d["t"], d["lfp"])
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=col, width=0.9),
                                 yaxis=yref, showlegend=False, connectgaps=False,
                                 hovertemplate="chronic %{x|%Y-%m-%d %H:%M}<br>LFP %{y:.0f}<extra></extra>"))
        if sv:
            sx = [datetime.utcfromtimestamp(x[0]) for x in sv]
            smed = [x[2] for x in sv]
            slo = [x[2] - x[3] for x in sv]
            shi = [x[4] - x[2] for x in sv]
            fig.add_trace(go.Scatter(x=sx, y=smed, mode="markers", yaxis=yref, showlegend=False,
                                     marker=dict(color=scol, size=5, symbol="diamond",
                                                 line=dict(width=0.5, color="white")),
                                     error_y=dict(type="data", symmetric=False, array=shi, arrayminus=slo,
                                                  color=scol, thickness=1.4, width=0),
                                     hovertemplate="streaming %{x|%Y-%m-%d %H:%M}<br>median LFP %{y:.0f}<extra></extra>"))
        fig.layout[yax] = dict(domain=[max(0, yd(sb)), yd(st)], range=yr, showgrid=False, zeroline=False,
                               ticks="outside", tickfont=dict(size=11), linecolor=col, linewidth=3, nticks=3)
        anns.append(dict(xref="paper", yref="paper", x=0.004, y=yd(st) - 0.006,
                         text=f"<b>{hemi[0]} {fmt_contact(c)}</b>", showarrow=False, font=dict(size=18, color=col),
                         xanchor="left", yanchor="bottom", bgcolor="rgba(255,255,255,0.78)"))
        s, a = freq_ribbon_shapes(d["epochs"], yd(rb), yd(rt), coverage=coverage_windows(d["t"]))
        shapes += s
        anns += a
        anns.append(dict(xref="paper", yref="paper", x=0.004, y=(yd(rt) + yd(rb)) / 2, text="freq",
                         showarrow=False, font=dict(size=11, color="#888"), xanchor="left", yanchor="middle"))

    used = sorted({e[2] for _, _, d in rows for e in d["epochs"] if e[2]})
    ly = 0.82
    anns.append(dict(xref="paper", yref="paper", x=1.012, y=ly + 0.05, text="<b>Sensing freq (Hz)</b>",
                     showarrow=False, font=dict(size=14), xanchor="left"))
    for i, hz in enumerate(used):
        yy = ly - i * 0.034
        shapes.append(dict(type="rect", xref="paper", yref="paper", x0=1.012, x1=1.032,
                           y0=yy - 0.012, y1=yy + 0.012, fillcolor=fcol(hz), line=dict(width=0.4, color="white")))
        anns.append(dict(xref="paper", yref="paper", x=1.040, y=yy, text=f"{hz:g}", showarrow=False,
                         font=dict(size=13), xanchor="left", yanchor="middle"))
    ky = ly - len(used) * 0.034 - 0.06
    anns.append(dict(xref="paper", yref="paper", x=1.012, y=ky + 0.03, text="<b>Source</b>",
                     showarrow=False, font=dict(size=14), xanchor="left"))
    shapes.append(dict(type="line", xref="paper", yref="paper", x0=1.012, x1=1.032, y0=ky, y1=ky,
                       line=dict(color="#555", width=1.4)))
    anns.append(dict(xref="paper", yref="paper", x=1.038, y=ky, text="chronic 24/7 (line)",
                     showarrow=False, font=dict(size=12), xanchor="left", yanchor="middle"))
    anns.append(dict(xref="paper", yref="paper", x=1.022, y=ky - 0.032, text="◆", showarrow=False,
                     font=dict(size=13, color="#555"), xanchor="center", yanchor="middle"))
    anns.append(dict(xref="paper", yref="paper", x=1.038, y=ky - 0.032, text="streaming (bar = range)",
                     showarrow=False, font=dict(size=12), xanchor="left", yanchor="middle"))

    fig.update_layout(height=H, width=1500, shapes=shapes, annotations=anns,
                      margin=dict(l=78, r=205, t=16, b=46), plot_bgcolor="white", paper_bgcolor="white",
                      font=dict(family="Roboto, Helvetica, Arial", size=12, color="#344767"),
                      xaxis=dict(domain=[0, 1], range=[gmin, gmax], anchor="y", showgrid=True,
                                 gridcolor="#E8E8EC", tickfont=dict(size=13)),
                      title=dict(text="<b>RCS08 chronic + streaming LFP by recording contact</b> — "
                                      "signal lives in the contact it came from; frequency ribbon shows "
                                      "the programmed band over time", x=0.5, font=dict(size=13.5)))
    fig.write_html(out_base + ".html", include_plotlyjs="cdn")
    try:
        fig.write_image(out_base + ".png", width=1500, height=H)
    except Exception as exc:
        print(f"(PNG export skipped: {exc})", file=sys.stderr)
    return H, len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsons", required=True, help="Folder of RCS08 Percept JSON exports.")
    ap.add_argument("--out", default="./contact_row_timeline", help="Output basename (.html/.png appended).")
    args = ap.parse_args()
    sched, chronic, stream = load_dataset(args.jsons)
    H, n = render(sched, chronic, stream, args.out)
    print(f"Rendered {n} contact rows (H={H}px) -> {args.out}.html / .png")
    for hemi in ("Left", "Right"):
        by = build_contacts(sched, chronic, hemi)
        print(f"  {hemi}: contacts={contacts_sorted(by)}, "
              f"chronic={sum(len(by[c]['t']) for c in by)}, streaming={len(stream[hemi])}")


if __name__ == "__main__":
    main()
