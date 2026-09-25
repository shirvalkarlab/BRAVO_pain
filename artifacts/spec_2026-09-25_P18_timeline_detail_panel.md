# Design spec: the timeline's detail panel (item P-18)

> Specification only. Nothing built. No source file under `Client/src` or `BRAVO/` was edited to
> produce this document.
> Author: worker-research (agent) | Date: 2026-09-25
> Status: draft, for the PI and for whoever builds it

## 1. What this is answering

The component `Client/src/views/Reports/Biomarkers/BiomarkerDataTimeline.js` draws the Biomarkers
page's data-availability timeline (one row per sensing channel, plus a pain row and a stimulation
row, all against calendar time). Its header comment, lines 1-21, describes a right-hand panel that
shows "the selected channel's real PSD curve, raw uV waveform, and LSB trend" when a lane is
clicked, and calls the timeline "the front door to the decode (select band -> threshold ->
controller)". That panel does not exist. I read the whole file (426 lines) and found no click
listener, no selection state, no inspector component, and no zoom-to-waveform code anywhere in it —
the comment describes a plan, not the code below it. This is tracked as item P-18 in
`artifacts/pending_items_from_handoffs_2026-09-25.md`, sourced from two June handoff documents
(`HANDOFF_session_psd-cache_ui-fixes.md` and a science-workspace copy), and flagged again in that
document's "Found in passing" section. Item N-17 in the same document is adjacent but separate: it
asks the PI to confirm four display choices already built into the existing timeline (the slate
pain line's colour, hiding unmatched PSD marks in the split view, hiding the frequency legend
there, and the stimulation row's height). None of those four are part of the missing panel; a
builder should leave them as they are unless the PI rules on N-17 separately.

**Where this sits today, exactly.** `BiomarkerDataTimeline` is rendered once, near the top of the
Biomarkers page, inside the "Pain Biomarker Exploration" card, in `Client/src/views/Reports/Biomarkers/index.js`
around line 565. It is the first thing a clinician or researcher sees on that page — it loads on
page open, before anyone presses the page's "Compute biomarker now" button, from the lightweight
`/api/queryDataAvailability` payload. Today, clicking anywhere on it does nothing.

## 2. Read this first if you build it: the layout skill

CLAUDE.md (`.claude/settings.local.json`'s `skillOverrides` note in §7) names a project skill,
`bravo-timeline-layout`, described as carrying "the timeline's left-label geometry,
`BiomarkerDataTimeline.js`" and says: "Load the matching one before touching either file; if it
does not load, ask for the conventions rather than inventing them." **I looked for it and could not
find it on this machine**: it is not under `/Users/pshirvalkar/dev/BRAVO_pain/.claude/skills/` (17
skills are present there — `swarm-plan`, `code-check`, `swarm-review`, `swarm-research`, `tailor`,
`qa-engineer`, `architect`, `ui-ux-designer`, `security-auditor`, `builder`, `land-the-plane`,
`swarm-execute`, and four templates/agents directories — but no `bravo-timeline-layout` among
them), nor under `~/.claude/`. CLAUDE.md itself warns the whole `.claude/` tree "exists on this
machine and in no clone" and to "run `ls .claude` before relying on any of it" — I did, and the
skill named in the prose is not there on this checkout. **A builder must check their own
environment for it before starting, and if it is still missing, ask the PI or whoever maintains the
skill for the conventions rather than guessing at them**, per CLAUDE.md's own instruction.

In its absence, here is what the current code already establishes as the de facto convention,
read directly out of `BiomarkerDataTimeline.js` (lines 355-390, comment header "LEFT-LABEL COLUMN
GEOMETRY"): the left-hand gutter holds three right-to-left columns (LSB tick numbers, contact
names such as "L 0⁻3⁺", and a rotated hemisphere/region label), laid out from **estimated text
widths** rather than fixed pixel offsets, with a uniform 12 px gap between columns, and the contact
and region fonts shrink together only if the total gutter would exceed 230 px. The comment there
says plainly why: "Earlier these used hand-tuned paper-fraction / fixed xshift values and collided
when the contact font was large or the plot was wide." **Any new panel that changes the plot's
width (a right-hand column, in particular) will change how much horizontal room Plotly gives the
chart, and this self-sizing left gutter, plus the per-lane LSB zoom-rescaling logic that references
pixel bands (`lsbScaleRef`, lines ~210-216), must be re-verified after the change, not assumed
unaffected.** This is the single biggest layout risk in building this panel and is exactly the
kind of thing the missing skill would presumably cover in more detail than I can reconstruct from
the code alone.

## 3. What the panel should show

Per the header comment's own description, kept as the target (nothing here invents a new scope):

1. **The selected recording's own PSD curve** — the power at each frequency for one specific
   captured recording, not a heat-map summary across many recordings. Per the house writing rules,
   this must never be labelled bare "spectrum": say which quantity it is — "the device's own FFT
   snapshot" for a device-computed one, or "the PSD computed from the voltage trace" for one built
   from the raw signal.
2. **The raw voltage trace** — the actual microvolt-scale waveform for that same recording window,
   where one exists (streaming or survey recordings carry it; the device's own periodic band-power
   readings and FFT snapshots do not).
3. **The calibrated band-power (LSB) trend** around the selected point — how this channel's power
   moved over nearby time, on the device's own LSB scale, not a raw microvolt number.

**Where it appears and how it opens.** A right-hand panel, matching the header comment's own word
"inspector": it should sit beside the timeline (or below it on a narrow screen), and open when
someone clicks a mark on a channel's lane — a coverage block (time-domain recording), a tick (PSD
snapshot), or a point on the band-power trend line. The existing heat-map grid
(`BiomarkerHeatmapGrids.js`, line 332) already wires exactly this kind of interaction — a
`plotly_click` listener that is torn down and re-attached on each redraw so old listeners cannot
pile up (the crash decision 91 fixed) — and the panel should reuse that pattern rather than invent
a second one. Selecting a new mark should update the panel in place; it should not require closing
and reopening it. The comment's "zoom-to-waveform" (the same handoff item mentions it, and it is
equally unbuilt) is the natural companion: clicking a PSD tick or a point on the trend line jumps
the raw-trace view to the matching few seconds, if a raw trace exists for that recording.

## 4. What it reads from the server

**Nothing here currently exists on the wire for this purpose**, and this is the main gap for
whoever scopes the build, not just the frontend component. The page's one existing call for this
view, `/api/queryDataAvailability` (decision 216: "the acquisition timeline"), returns compact,
render-cheap summaries only — per-channel records with `{channel, label, hemisphere, dtype,
product, t_start, dur_s, meta:{center_hz, peak_hz, n}}`, and a decimated `lsb_overview` (a chronic
line plus one block per streaming session) built to keep the page responsive against tens of
thousands of points. It carries no full-resolution PSD curve and no raw voltage trace for any single
recording; those never leave the server today for this page.

The natural source for the PSD curve is the per-recording spectrum store the project already
keeps: decision 51 kept a directory of about 6,309 per-recording spectrum files, "fronted by a
stamp over the recording set," specifically because rebuilding one per-kind snapshot on every new
recording was rejected as too costly. A new, narrow endpoint reading a single recording's entry
from that store (by channel and recording start time) is the cheapest path to item 1. Item 2 (the
raw trace) and item 3 (a full-resolution trend, if the decimated overview is not enough once someone
is looking at one recording closely) would need their own reads, from wherever the decoded
time-domain trace already lives for other pipeline steps — I did not trace that path further, since
this document is a specification, not a build plan, and CLAUDE.md restricts this task to writing
one document. **Whoever picks up the build should read `DEVICE_percept_rc.md` and
`ARCHITECTURE_modules_and_store.md`'s file map before choosing where the new endpoint's data comes
from, and should expect a new backend route, not a repurposed existing one.**

## 5. What it must not claim

- **Never write "spectrum" or "spectral" bare.** Per the house writing rules' replacement table:
  say which quantity is on screen — the device's own FFT snapshot, the PSD computed from the
  voltage trace, or (if a modelled value is ever shown here) that it is modelled and from what.
- **No log-scaled power, ever, on this panel.** Project rule (CLAUDE.md §8 rule 14, decisions 202,
  204-206): log power enters no calculation and no plot anywhere in this codebase. The PSD curve
  and the LSB trend must be drawn on their raw scale.
- **Never pool the two brain sides into one figure.** Each channel belongs to one hemisphere; the
  panel shows one selected channel's own data. This mirrors the existing rule that a page judges a
  band on its own side (decision 141).
- **No pain rating enters the key or the payload of this panel's data.** The store's rule (CLAUDE.md
  §8 rule 5; `ARCHITECTURE_cache_store.md` §3) is that a recording-derived product carries no pain
  score in what decides whether to rebuild it or in what it serves. The PSD curve, the raw trace and
  the LSB trend are all recording-derived; a pain rating must not be joined into that request or
  that cached answer. The existing timeline already keeps this separation (decision 216: the
  acquisition timeline "reads no pain report"; the pain row is a separate call to
  `/api/queryPainScores`). The detail panel may show, as context, that a pain report fell near the
  selected time — the same way the existing pain row already does — but that display must stay a
  separate overlay, never a value merged into the recording data's own request or its stored answer.
- **The panel shows what was recorded; it does not compute, score, or gate anything.** It is a
  viewer, not a fourth statistical product. It must not print a correlation, a verdict, a q-value or
  a word like "established," "supported," or "usable" — those belong to the heat-map grid and the
  Closed-Loop page's own machinery, built and worded under their own rules (decisions 199, 210, 217,
  242). Showing a raw trace or a PSD curve next to a nearby pain score is descriptive, not a claim
  that the two are related.
- **Say plainly when a piece is missing**, rather than leaving a blank chart. Many device products
  (chronic band-power readings, most FFT snapshots) carry no raw voltage trace at all; the panel
  should say "no raw recording for this point" rather than show an empty axis.

## 6. Scope note for the orchestrator

This is a specification only, per this task's instructions ("Specification only. Build nothing.").
The two open questions that block a build estimate are (a) which existing skill file, if any, holds
the fuller `bravo-timeline-layout` conventions this document could not locate, and (b) which
existing backend module should serve a single recording's PSD curve and raw trace on request,
since no such endpoint exists on the Biomarkers page today. Both should be resolved before anyone
scopes hours for the build.
