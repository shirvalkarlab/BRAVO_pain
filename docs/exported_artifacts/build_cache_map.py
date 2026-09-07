"""The BRAVO cache map: three inputs, one cache location, three modules.

ONE DESCRIPTION, TWO OUTPUTS. The architecture SVG is the reference copy and the Excalidraw file is
the editable one, both generated from the NODES/EDGES tables below so they cannot drift apart.

Every number in here was measured on 2026-09-06 in the running container, not recalled:
the four cache directories and their sizes from os.listdir/getsize, the two byte caps from the
modules' own constants, and the timings from the alternating-round measurements committed tonight.
"""
import json, os

OUT = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------------------------
# THE THREE PLATFORM INPUTS. Numbered because the PI asked for them numbered and because their
# caching stories are completely different, which is the point of the whole diagram.
# --------------------------------------------------------------------------------------------
INPUTS = [
    dict(n="1", title="Medtronic Percept RC",
         sub="Session Report JSON, exported per visit",
         detail=["569 stored files for RCS08",
                 "voltage traces at 250/s, chronic power,",
                 "device spectra, therapy settings"],
         status="cached", note="the ONLY input that is cached"),
    dict(n="2", title="REDCap pain reports",
         sub="pulled fresh on every page request",
         detail=["760 reports, 765 rows x 28 columns",
                 "0.651 s per request",
                 "filed continuously by the participant"],
         status="never", note="NEVER cached, and deliberately so"),
    dict(n="3", title="Google Drive visit sheets",
         sub="at-home and in-clinic stim testing tabs",
         detail=["parsed offline 2026-09-05, 30 sheets",
                 "live in the analysis folder only",
                 "THE SERVER HAS NO COPY"],
         status="absent", note="never reaches the server at all"),
]

# --------------------------------------------------------------------------------------------
# THE SINGLE CACHE LOCATION as it stands today: one root, four directories, TWO separate
# implementations of the same store with different byte caps.
# --------------------------------------------------------------------------------------------
CACHE_ROOT = "$DATASERVER_PATH/cache/"
CACHE_KINDS = [
    dict(name="biomarker_shared", files="1 file", size="245.90 MB",
         what="3-second tiles + 98-band spectra", owner="Biomarkers", live=True),
    dict(name="biomarker_psd", files="97 files", size="500.32 MB",
         what="whole-participant assembled matrix", owner="Biomarkers", live=True),
    dict(name="biomarker_psd_rows", files="6,309 files", size="30.47 MB",
         what="per-recording spectra", owner="Biomarkers", live=False),
    dict(name="closed_loop", files="2 files", size="5.52 MB",
         what="evidence inputs + response", owner="ClosedLoop", live=True),
]

# --------------------------------------------------------------------------------------------
# THE THREE MODULES, outputs as a numbered list each.
# --------------------------------------------------------------------------------------------
MODULES = [
    dict(key="bm", title="Biomarker Exploration",
         reads="reads: tiles + assembled matrix + REDCap",
         outputs=["Correlation per band centre, one row per contact pair",
                  "Discrimination (area under curve) per band centre",
                  "Band centre x integration-time sweep, 22 x 10 grid",
                  "Data-availability timeline per channel"],
         cache="CACHED  cold 42.83 s -> 6.06 s with the file present"),
    dict(key="so", title="Stim Optimizer",
         reads="reads: therapy settings stream + REDCap",
         outputs=["Posterior surface over stimulation rate and current",
                  "Exploration queue with delivered-settings eligibility",
                  "Forward-simulated selection batches",
                  "Coverage and safety map"],
         cache="NO ON-DISK CACHE  2 stream rebuilds = 65.71 s per request"),
    dict(key="cl", title="Closed-Loop Deployment",
         reads="reads: evidence inputs (from the tile cache) + REDCap",
         outputs=["Deployability verdict, 6 of 50 settings",
                  "Evidence triangle: current -> power -> pain",
                  "Three-source comparison of how current moves power",
                  "Prescription, duty cycle and device rule ledger"],
         cache="CACHED  evidence inputs keyed on the recording set"),
]

# ============================================================================================
# ARCHITECTURE SVG
# ============================================================================================
W, H = 1500, 1060
X_IN, W_IN = 28, 300
X_ING, W_ING = 366, 158
X_CA, W_CA = 578, 330
X_MOD, W_MOD = 986, 490

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def box(x, y, w, h, cls, rx=10):
    return ('  <rect x="%d" y="%d" width="%d" height="%d" rx="%d" class="node %s"/>'
            % (x, y, w, h, rx, cls))

def txt(x, y, s, cls="label", anchor="start", weight=None):
    w = ' font-weight="%s"' % weight if weight else ""
    return '  <text x="%d" y="%d" class="%s" text-anchor="%s"%s>%s</text>' % (
        x, y, cls, anchor, w, esc(s))

svg, edges, nodes = [], [], []

svg.append('<svg viewBox="0 0 %d %d" role="img" aria-label="BRAVO cache map">' % (W, H))
svg.append('  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"'
           ' markerHeight="7" orient="auto-start-reverse">'
           '<path d="M0,0 L10,5 L0,10 z" fill="var(--line)"/></marker></defs>')

nodes.append(txt(28, 40, "What BRAVO caches, and what it does not", "title"))
nodes.append(txt(28, 62, "Measured in the running container, 2026-09-06. Three inputs, one cache "
                         "location, three modules.", "small"))

# ---- column headings
for x, s in ((X_IN, "THE THREE INPUTS"), (X_ING, "INGESTION"),
             (X_CA, "ONE CACHE LOCATION"), (X_MOD, "THE THREE MODULES")):
    nodes.append(txt(x, 92, s, "small", weight="700"))

# ---- inputs (primary focus: tallest, numbered, leftmost)
CLS = {"cached": "input", "never": "risk", "absent": "risk"}
in_y, in_h, in_gap = 112, 196, 26
in_centres = []
for k, inp in enumerate(INPUTS):
    y = in_y + k * (in_h + in_gap)
    in_centres.append(y + in_h / 2)
    nodes.append(box(X_IN, y, W_IN, in_h, CLS[inp["status"]]))
    nodes.append('  <circle cx="%d" cy="%d" r="15" fill="var(--bg)" stroke="var(--line)"/>'
                 % (X_IN + 30, y + 32))
    nodes.append(txt(X_IN + 30, y + 37, inp["n"], "label", "middle", "700"))
    nodes.append(txt(X_IN + 56, y + 30, inp["title"], "label"))
    nodes.append(txt(X_IN + 56, y + 50, inp["sub"], "small"))
    for j, d in enumerate(inp["detail"]):
        nodes.append(txt(X_IN + 24, y + 84 + j * 19, d, "small"))
    nodes.append(txt(X_IN + 24, y + in_h - 18, inp["note"], "small", weight="700"))

# ---- ingestion
ing_y, ing_h = 150, 196
nodes.append(box(X_ING, ing_y, W_ING, ing_h, "process"))
nodes.append(txt(X_ING + W_ING / 2, ing_y + 34, "Ingestion", "label", "middle"))
nodes.append(txt(X_ING + W_ING / 2, ing_y + 54, "decode + store", "small", "middle"))
for j, d in enumerate(["JSON decoder", "writes the DB rows,", "then warms the cache",
                       "in a background", "thread that cannot", "fail an upload"]):
    nodes.append(txt(X_ING + W_ING / 2, ing_y + 82 + j * 17, d, "small", "middle"))

# ---- the single cache location
ca_y, ca_h = 112, 452
nodes.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="12" class="zone"/>'
             % (X_CA - 10, ca_y - 10, W_CA + 20, ca_h + 20))
nodes.append(txt(X_CA + W_CA, 92, CACHE_ROOT, "small", "end"))
row_h = 100
for k, c in enumerate(CACHE_KINDS):
    y = ca_y + k * (row_h + 12)
    nodes.append(box(X_CA, y, W_CA, row_h, "storage" if c["live"] else "neutral"))
    nodes.append(txt(X_CA + 24, y + 28, c["name"], "label"))
    nodes.append(txt(X_CA + 24, y + 48, c["what"], "small"))
    nodes.append(txt(X_CA + 24, y + 68, "%s   %s   owner: %s" % (c["files"], c["size"], c["owner"]),
                     "small"))
    if not c["live"]:
        nodes.append(txt(X_CA + 24, y + 88, "NEVER READ by any live page (0 reads measured)",
                         "small", weight="700"))
    else:
        nodes.append(txt(X_CA + 24, y + 88, "read on every page view", "small"))

nodes.append(txt(X_CA, ca_y + ca_h + 26,
                 "TWO implementations of this one store, with different caps:", "small", weight="700"))
nodes.append(txt(X_CA, ca_y + ca_h + 44, "Biomarkers 1074 MB cap  /  ClosedLoop 268 MB cap", "small"))
nodes.append(txt(X_CA, ca_y + ca_h + 62, "Stim Optimizer has no entry here at all.", "small"))

# ---- modules
mod_y, mod_h, mod_gap = 112, 232, 28
mod_centres = []
MODCLS = {"bm": "neutral", "so": "risk", "cl": "neutral"}
for k, m in enumerate(MODULES):
    y = mod_y + k * (mod_h + mod_gap)
    mod_centres.append(y + mod_h / 2)
    nodes.append(box(X_MOD, y, W_MOD, mod_h, MODCLS[m["key"]]))
    nodes.append(txt(X_MOD + 24, y + 32, m["title"], "label"))
    nodes.append(txt(X_MOD + 24, y + 52, m["reads"], "small"))
    nodes.append(txt(X_MOD + 24, y + 76, "Outputs", "small", weight="700"))
    for j, o in enumerate(m["outputs"]):
        nodes.append(txt(X_MOD + 24, y + 96 + j * 21, "%d.  %s" % (j + 1, o), "small"))
    nodes.append(txt(X_MOD + 24, y + mod_h - 20, m["cache"], "small", weight="700"))

# ---- edges, drawn BEFORE nodes so arrows sit behind the boxes
def h_edge(x1, y1, x2, y2, dash=False):
    mx = (x1 + x2) / 2
    d = ' stroke-dasharray="7 5"' if dash else ""
    return ('  <path class="edge" marker-end="url(#a)"%s d="M%d,%d C%d,%d %d,%d %d,%d"/>'
            % (d, x1, y1, mx, y1, mx, y2, x2, y2))

# input 1 -> ingestion -> cache
edges.append(h_edge(X_IN + W_IN, in_centres[0], X_ING, ing_y + ing_h / 2))
edges.append(h_edge(X_ING + W_ING, ing_y + ing_h / 2, X_CA, ca_y + row_h / 2))
# INPUT 2 IS DRAWN AS A BUS THAT PASSES UNDER THE CACHE, not through it. The first version
# fanned three curves from REDCap across the cache boxes, which read as though the reports were
# being cached -- the exact opposite of the fact the diagram exists to state.
BUS_Y = 830
BUS_X = X_MOD - 34
edges.append('  <path class="edge" stroke-dasharray="7 5" d="M%d,%d L%d,%d L%d,%d L%d,%d"/>'
             % (X_IN + W_IN, in_centres[1], X_IN + W_IN + 40, in_centres[1],
                X_IN + W_IN + 40, BUS_Y, BUS_X, BUS_Y))
edges.append('  <path class="edge" stroke-dasharray="7 5" d="M%d,%d L%d,%d"/>'
             % (BUS_X, BUS_Y, BUS_X, mod_centres[0]))
for cy in mod_centres:
    edges.append('  <path class="edge" marker-end="url(#a)" stroke-dasharray="7 5" '
                 'd="M%d,%d L%d,%d"/>' % (BUS_X, cy, X_MOD, cy))
edges.append('  <text x="%d" y="%d" class="small" font-weight="700">'
             'REDCap, fetched fresh every request</text>' % (X_IN + W_IN + 52, BUS_Y - 10))
# input 3 -> nowhere: a stub that stops at the boundary
edges.append('  <path class="edge" stroke-dasharray="4 6" d="M%d,%d L%d,%d"/>'
             % (X_IN + W_IN, in_centres[2], X_IN + W_IN + 62, in_centres[2]))
edges.append('  <text x="%d" y="%d" class="small" font-weight="700" fill="var(--muted)">'
             'stops here</text>' % (X_IN + W_IN + 8, in_centres[2] - 12))
# cache -> modules
edges.append(h_edge(X_CA + W_CA, ca_y + row_h / 2, X_MOD, mod_centres[0] - 46))
edges.append(h_edge(X_CA + W_CA, ca_y + 3 * (row_h + 12) + row_h / 2, X_MOD, mod_centres[2] - 46))

svg.extend(edges)
svg.extend(nodes)

# ---- legend
ly = 972
svg.append(txt(28, ly - 12, "Legend", "small", weight="700"))
for k, (cls, lab) in enumerate([("input", "cached on disk"),
                                ("process", "ingestion (the only writer of new data)"),
                                ("storage", "cache read by a live page"),
                                ("neutral", "present but not read by any live page"),
                                ("risk", "not cached, or no cache at all")]):
    x = 28 + k * 278
    svg.append('  <rect x="%d" y="%d" width="18" height="14" rx="3" class="node %s"/>' % (x, ly, cls))
    svg.append(txt(x + 26, ly + 12, lab, "small"))
svg.append(txt(28, ly + 44, "Solid arrow = data flows and is cached on the way.   "
                            "Dashed arrow = flows on every request, never cached.   "
                            "Short dashed stub = never reaches the server.", "small"))
svg.append('</svg>')

tpl = open("/Users/pshirvalkar/.claude-science/orgs/e1a4e614-cfd2-4f53-ae46-1203303ddbf1/"
           "skills/diagram-maker/references/svg-template.md").read()
html = tpl.split("```html")[1].split("```")[0].replace("<!-- SVG -->", "\n".join(svg))
open(os.path.join(OUT, "cache_map.html"), "w").write(html)
print("wrote cache_map.html  (%d bytes, %d svg elements)" % (len(html), len(svg)))


# ============================================================================================
# STANDALONE SVG + PNG, so the diagram can be inspected rather than assumed
# ============================================================================================
import re as _re, xml.etree.ElementTree as _ET

_h = open(os.path.join(OUT, "cache_map.html")).read()
_css = _re.search(r"<style>(.*?)</style>", _h, _re.S).group(1)
_svg = _re.search(r"(<svg .*?</svg>)", _h, _re.S).group(1)
_vals = dict(_re.findall(r"--([a-z]+):\s*(#[0-9a-fA-F]{3,6});", _css.split("@media")[0]))
for _k, _v in _vals.items():
    _svg = _svg.replace("var(--%s)" % _k, _v)

# EXPLICIT font-size AND font-weight, never the `font:` shorthand. A numeric weight such as
# `font:650 20px ...` makes the whole shorthand invalid, so EVERY rule in the block is dropped and
# the text renders at the renderer's default size. The first render of this diagram had a title in
# giant black letters clipped off the top of the canvas for exactly that reason.
_klass = """<style>
.title{font-family:ui-sans-serif,system-ui,sans-serif;font-size:20px;font-weight:650;fill:%(fg)s}
.label{font-family:ui-sans-serif,system-ui,sans-serif;font-size:14px;font-weight:600;fill:%(fg)s}
.small{font-family:ui-sans-serif,system-ui,sans-serif;font-size:12px;fill:%(muted)s}
.node{stroke:%(line)s;stroke-width:1}
.neutral{fill:%(neutral)s}.input{fill:%(input)s}.process{fill:%(process)s}
.storage{fill:%(storage)s}.external{fill:%(external)s}.risk{fill:%(risk)s}
.edge{stroke:%(line)s;stroke-width:1.5;fill:none}
.zone{fill:none;stroke:%(line)s;stroke-width:1;stroke-dasharray:6 5;opacity:.8}
</style>""" % _vals
_svg = _svg.replace("<defs>", _klass + "<defs>", 1)
_svg = _svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" style="background:%s" '
                    % _vals["bg"], 1)
open(os.path.join(OUT, "cache_map.svg"), "w").write(_svg)
_ET.fromstring(_svg)

import cairosvg
cairosvg.svg2png(url=os.path.join(OUT, "cache_map.svg"),
                 write_to=os.path.join(OUT, "cache_map.png"),
                 scale=1.5, background_color=_vals["bg"])
from PIL import Image
print("wrote cache_map.svg and cache_map.png  %s" % (Image.open(os.path.join(OUT, "cache_map.png")).size,))


# ============================================================================================
# EXCALIDRAW — the EDITABLE copy, generated from the same tables above so it cannot disagree
# with the SVG. This is the one to open and rearrange; the SVG is the reference render.
# ============================================================================================
PAL = {"input": "#a5d8ff", "process": "#d0bfff", "storage": "#c3fae8",
       "neutral": "#e9ecef", "risk": "#ffc9c9", "note": "#fff3bf"}

_el = []

def _rect(eid, x, y, w, h, fill, text, size=16, align="left"):
    _el.append({"type": "rectangle", "id": eid, "x": x, "y": y, "width": w, "height": h,
                "roundness": {"type": 3}, "backgroundColor": fill, "fillStyle": "solid",
                "strokeColor": "#1e1e1e", "strokeWidth": 2, "roughness": 1, "opacity": 100,
                "angle": 0, "seed": abs(hash(eid)) % 100000, "version": 1, "versionNonce": 1,
                "isDeleted": False, "groupIds": [], "frameId": None, "link": None, "locked": False,
                "boundElements": [{"id": eid + "_t", "type": "text"}], "updated": 1})
    _el.append({"type": "text", "id": eid + "_t", "x": x + 14, "y": y + 12,
                "width": w - 28, "height": h - 24, "text": text, "originalText": text,
                "fontSize": size, "fontFamily": 1, "strokeColor": "#1e1e1e",
                "textAlign": align, "verticalAlign": "top", "containerId": eid,
                "autoResize": False, "lineHeight": 1.25, "angle": 0,
                "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 1,
                "roughness": 1, "opacity": 100, "seed": abs(hash(eid + "t")) % 100000,
                "version": 1, "versionNonce": 1, "isDeleted": False, "groupIds": [],
                "frameId": None, "link": None, "locked": False, "updated": 1})

def _label(eid, x, y, text, size=14, w=340):
    _el.append({"type": "text", "id": eid, "x": x, "y": y, "width": w, "height": size + 6,
                "text": text, "originalText": text, "fontSize": size, "fontFamily": 1,
                "strokeColor": "#495057", "textAlign": "left", "verticalAlign": "top",
                "containerId": None, "autoResize": True, "lineHeight": 1.25, "angle": 0,
                "backgroundColor": "transparent", "fillStyle": "solid", "strokeWidth": 1,
                "roughness": 1, "opacity": 100, "seed": abs(hash(eid)) % 100000,
                "version": 1, "versionNonce": 1, "isDeleted": False, "groupIds": [],
                "frameId": None, "link": None, "locked": False, "updated": 1})

def _arrow(eid, x, y, pts, src=None, dst=None, dashed=False, head="arrow"):
    _el.append({"type": "arrow", "id": eid, "x": x, "y": y,
                "width": max(abs(p[0]) for p in pts) or 1,
                "height": max(abs(p[1]) for p in pts) or 1,
                "points": pts, "endArrowhead": head, "startArrowhead": None,
                "strokeColor": "#495057", "backgroundColor": "transparent",
                "fillStyle": "solid", "strokeWidth": 2,
                "strokeStyle": "dashed" if dashed else "solid",
                "roughness": 1, "opacity": 100, "angle": 0, "roundness": {"type": 2},
                "startBinding": ({"elementId": src, "focus": 0, "gap": 4} if src else None),
                "endBinding": ({"elementId": dst, "focus": 0, "gap": 4} if dst else None),
                "seed": abs(hash(eid)) % 100000, "version": 1, "versionNonce": 1,
                "isDeleted": False, "groupIds": [], "frameId": None, "link": None,
                "locked": False, "updated": 1, "elbowed": False})

_label("ttl", 40, 24, "What BRAVO caches, and what it does not", 26, 700)
_label("sub", 40, 58, "Measured in the running container, 2026-09-06. Editable copy - move "
                      "anything, then hand it back.", 14, 800)

# inputs, numbered, primary focus
_label("h1", 40, 100, "THE THREE INPUTS", 13)
IY, IH = 130, 210
icls = {"cached": "input", "never": "risk", "absent": "risk"}
for k, inp in enumerate(INPUTS):
    body = ("%s.  %s\n%s\n\n%s\n\n%s"
            % (inp["n"], inp["title"], inp["sub"], "\n".join(inp["detail"]), inp["note"]))
    _rect("in%d" % k, 40, IY + k * (IH + 30), 340, IH, PAL[icls[inp["status"]]], body)

# ingestion
_label("h2", 430, 100, "INGESTION", 13)
_rect("ing", 430, 150, 210, 210, PAL["process"],
      "Ingestion\ndecode + store\n\nJSON decoder writes the DB\nrows, then warms the cache\n"
      "in a background thread\nthat cannot fail an upload")

# the one cache location
_label("h3", 700, 100, "ONE CACHE LOCATION   " + CACHE_ROOT, 13, 520)
CY, CH = 130, 118
for k, c in enumerate(CACHE_KINDS):
    body = ("%s\n%s\n%s   %s   owner: %s\n%s"
            % (c["name"], c["what"], c["files"], c["size"], c["owner"],
               "read on every page view" if c["live"]
               else "NEVER READ by any live page (0 reads measured)"))
    _rect("ca%d" % k, 700, CY + k * (CH + 14), 380, CH,
          PAL["storage"] if c["live"] else PAL["neutral"], body)
_rect("canote", 700, CY + 4 * (CH + 14), 380, 96, PAL["note"],
      "TWO implementations of this one store,\nwith different caps: Biomarkers 1074 MB,\n"
      "ClosedLoop 268 MB. Stim Optimizer has\nno entry here at all.")

# modules
_label("h4", 1140, 100, "THE THREE MODULES", 13)
MY, MH = 130, 250
mcls = {"bm": "neutral", "so": "risk", "cl": "neutral"}
for k, m in enumerate(MODULES):
    outs = "\n".join("%d.  %s" % (j + 1, o) for j, o in enumerate(m["outputs"]))
    body = "%s\n%s\n\nOutputs\n%s\n\n%s" % (m["title"], m["reads"], outs, m["cache"])
    _rect("mo%d" % k, 1140, MY + k * (MH + 30), 520, MH, PAL[mcls[m["key"]]], body)

# edges
_arrow("e1", 380, IY + IH / 2, [[0, 0], [50, 0]], "in0", "ing")
_arrow("e2", 640, 255, [[0, 0], [60, 0]], "ing", "ca0")
_arrow("e3", 1080, CY + CH / 2, [[0, 0], [60, 0]], "ca0", "mo0")
_arrow("e4", 1080, CY + 3 * (CH + 14) + CH / 2, [[0, 0], [60, 130]], "ca3", "mo2")
# REDCap bus, routed UNDER the cache rather than through it
_arrow("bus", 380, IY + IH + 30 + IH / 2,
       [[0, 0], [40, 0], [40, 620], [720, 620]], "in1", None, dashed=True, head=None)
for k in range(3):
    _arrow("bus%d" % k, 1100, MY + k * (MH + 30) + MH / 2, [[0, 0], [40, 0]], None,
           "mo%d" % k, dashed=True)
_arrow("stub", 380, IY + 2 * (IH + 30) + IH / 2, [[0, 0], [56, 0]], "in2", None,
       dashed=True, head=None)
_label("stublab", 400, IY + 2 * (IH + 30) + IH / 2 - 26, "stops here - never reaches the server", 13)
_label("buslab", 460, IY + IH + 30 + IH / 2 + 596, "REDCap, fetched fresh on every request", 13, 400)

doc = {"type": "excalidraw", "version": 2, "source": "bravo/cache-map",
       "elements": _el, "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}}
open(os.path.join(OUT, "cache_map.excalidraw"), "w").write(json.dumps(doc, indent=1))
print("wrote cache_map.excalidraw  (%d elements: %d shapes, %d arrows)"
      % (len(_el), sum(1 for e in _el if e["type"] == "rectangle"),
         sum(1 for e in _el if e["type"] == "arrow")))
