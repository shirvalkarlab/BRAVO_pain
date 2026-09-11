# Findings — Closed-Loop Deployment page redesign

## §1 THE PI'S BRIEF (2026-09-10), copied verbatim from the sweep plan's findings §3
"The CL module page is way too long, so we need to distill it down and make it much slimmer."
- "The calibrated grid at the top is really ugly and takes up too much space. We should have a
  visual depiction similar to the heat map from the biomarkers module, flipped 90 degrees so that
  the band centers are oriented vertically. Then you can put maybe correlation high versus low.
  Instead of high versus low, it should be called AUC, and we can have a symbol for family-wise
  correlation. If it doesn't clear, you get a little X; if it does clear, you get a checkmark. For
  cross-setting stability, it can be a yellow circle for when it can't tell, a red cross if it
  behaves differently, and a green checkmark if it's good. It can be a tick mark or a box that
  needs to be clicked or checked instead of writing 'use this band' a million times. Write it once
  on top, and then again for all the tabs you select for which contact."
- Contacts: "they should be in standard Medtronic notation, left 1-3+, left 0-3+, ordered left to
  right as in biomarkers thumbnails."
- "load your scientific visualization skills as well as other UI/UX skills."
- "Text everywhere makes it really verbose, so maybe it should be a dropdown like reveal this,
  don't reveal this panel. The device rule ledger should also be a panel that can be expanded or
  contracted because it's too verbose."
- "SIGN COHERENT should be called SIGN agreement, SIGN concordance, or something similar."
- "This is really critical and important": rename "how stimulation current [moved] band power
  measured three ways" to "stimulation amplitude effects on band power measured three ways".
- The three source titles inside that panel, his exact words: "instead of 'from the voltage trace',
  'from the device's own spectrum', 'from the device's own band power', it should be rephrased to
  'Time domain derived LSB', 'PSD derived LSB', and then finally 'Direct LSB recording'. Those should
  be the three titles. In the text below, it should be significantly made much more concise with
  the scientific visualization skill."
- Three-source panel: "you basically don't want separate visits with separate tabs because you
  pool across all visits for right side and left side. Maybe it's just two tabs for right side
  amplitude change and left side amplitude change pooled across all visits. Then we'll have to
  adjust or massage exactly what calculation goes into the evidence triangle from there, which
  remains to be determined."
- Also belongs in this session (sweep plan, Phase 6): the closed-loop simulation module design,
  deferred from old item 9.

Carried from the sweep handoff: after any backend commit run
`docker exec bravo_pain-bravo-server-1 kill -HUP 1`; the in-app browser caches index.html, so check
the loaded chunk hash; save every suite run to a log and read the count from it.

## §2 Code map of the page as it is today
(filled in during Phase 1)

### §2.1 The page shell — `Client/src/views/Reports/ClosedLoopSim/index.js` (717 lines)
Render order today (each `id=` is what the sign-off card's figure snapshots look for):
1. Title card ("Closed-Loop Deployment", Load BandCandidate JSON, Clear)
2. `#cl-grid` **BandSweepGridPanel** — rendered even with no band committed (it is how a first band
   is chosen). Feeds from `useBandSweepGrid` (slot `CL.grid`).
3. If no band committed: a "go to Biomarkers" card and nothing else. Otherwise:
4. RecomputeBar + CacheStatusLine + **DeploymentDecisionHeader** (sticky verdict)
5. `#cl-what-changes` WhatWouldChangeThis
6. `#cl-rules` **DeviceRuleLedger** (369 lines; the PI wants it collapsible)
7. `#cl-evidence` **EvidenceTrianglePanel** (hand-drawn SVG; "SIGN COHERENT" lives here or in the
   report payload — check)
8. `#cl-stability` BandStabilityPanel
9. `#cl-reliable-change` ReliableChangePanel
10. `#cl-prescription` PrescriptionPanel (714 lines) + `#cl-duty` DutyCyclePanel
11. BandCandidateIdentity (in index.js; discovery-stage statistics ALWAYS shown, PI 2026-09-10:
    "there's no point in hiding it ever" — do NOT fold this one)
12. "Evidence for the analyst" fold button; when opened once, mounts `#cl-roc` DeploymentRocPanel,
    `#cl-lsb` LsbPowerPanel, `#cl-era` EraRefitPanel (hidden-not-unmounted; Plotly zero-width trap:
    never first-draw a Plotly figure inside display:none)
13. `#cl-three-source` **ThreeSourceResponsePanel** — outside the fold on purpose (Plotly trap)
14. `#cl-signoff` DeploySignoffCard (printable)
Data: `useDeploymentSummary` (mixed-effects fit, one per page) and `useDeploymentReport` (device
rules + triangle + band_stability + reliable_change + three-source). Grid comes from
`useBandSweepGrid` -> `report.band_sweep_grid` = the Biomarkers `biomarker_band_sweep` entry read as
consumer="closed_loop".

### §2.2 The grid table — `BandSweepGridPanel.js` (267 lines)
- Channel chips: keys of `grid.band_time_sweep` sorted ALPHABETICALLY (e.g. ONE_THREE_LEFT,
  ZERO_THREE_RIGHT...) with underscores turned to spaces. Not Medtronic notation, not L-then-R order.
- Rows = one per band centre (22 centres, 8.5–29.5 Hz); merged from `best_correlation_rows`
  (`pearson_r`, `family_wise_q_8_to_30hz`, `family_wise_significant_8_to_30hz`) and
  `best_auc_rows` (`auc`, `answer`). Stability: `cross_setting_stability.{answer,reason}` with
  answers "behaves the same" / "behaves differently" / "cannot tell" / "not tested"; absent when
  the grid was built without `IncludeCrossSettingStability` (chip "not yet computed").
- Columns today: Band centre | Correlation r | **High-vs-low** (= AUC; PI wants it called AUC) |
  Family-wise (correlation) chip | Cross-setting stability chip | "Use this band" button on EVERY row.
- Choosing a row commits a BandCandidate (`commitBandCandidate`) with threshold_mode "dual",
  label {}; every panel below recomputes. `hemisphere` comes from the already-committed band (null
  on first pick).
- The family-wise flag shown is the CORRELATION one (`family_wise_significant_8_to_30hz`); the AUC
  grid also carries its own (`family_wise_significant_auc`), merged but not displayed.
- Note: this grid is per band centre only — the Biomarkers heat map has a second axis (length of
  signal). The "best_*_rows" are the best per centre across lengths. Question for design: heat map
  over what second axis? Or a one-column-per-metric strip (centres vertical × {r, AUC})?

### §2.3 The three-source panel — front and back
Frontend `ThreeSourceResponsePanel.js` (320 lines) computes NO text: title is the only literal
("How stimulation current moved band power, measured three ways", at lines ~244 and ~264).
Everything else — tab labels, headline, subtitle, the three column headings, the three captions,
the footer — comes from the server payload `report.data.three_source_response.comparisons[i]`.
- Backend: `BRAVO/modules/ClosedLoopDeployment/three_source_plots.py` `_short()` (line ~106) holds
  the three headings the PI wants replaced: "From the voltage trace" / "From the device's own
  spectrum" / "The device's own band power" -> "Time domain derived LSB" / "PSD derived LSB" /
  "Direct LSB recording". `build_context()` (line ~217) writes headline, subtitle, per-column
  caption, footer. The static matplotlib figure for the report reads the same context, so the
  rename reaches the printed record too.
- One tab per RUN: `three_source_response.build_for_participant` (line ~1167) finds every stretch
  of rising current on one side with the other at zero, newest first, and `adapter.py` ~line 1934
  slices to `THREE_SOURCE_RUNS_ON_PAGE = 4` for the page (all runs only when the amplitude-effect
  and ground-truth entries are not yet stored). A run = one visit x one ramped side x the sensing
  contact ON THAT SIDE that was reporting band power (contact name ends with the side).
- Decision 55's pooling: `amplitude_effect.pooled_shape_for_band` pools the raw (current, settled
  power) pairs across every run on ONE sensing contact, each run its own baseline (mixed model,
  grouping = run label). The stored table `within_visit_pooled_shape` (decision 103) has one row per
  (sensing contact, band centre) with pooled_direction, pooled_slope_per_mA, stderr, p, n,
  n_visits, verdict, curves, peaks_inside, peak_mA, p_curvature, r2_linear, r2_quadratic. It is
  derived from the TIME-DOMAIN route's raw pairs (`_raw_pairs_for_band`) — check whether the other
  two routes are pooled anywhere: they are not in this table.
- So "two tabs, right side / left side, pooled across visits" = group runs by `ramped_side`
  (which fixes the sensing side), overlay every visit's points for each of the three routes, and
  draw the pooled fit from the stored table for the time-domain route. Needs a NEW payload shape
  (backend) and a new draw (frontend). The 4-run page slice would have to go (pool needs all runs)
  — but the pooled table is already stored from a full build, so the page can read it without
  rebuilding all runs; the per-visit POINTS for the overlay, however, live only in the truncated
  build. Design question for the PI / decision: build all runs for the page (32.5 s cold per
  decision 103's measurement) or store the per-run points alongside the pooled table.
- Evidence triangle input from the pooled view: undetermined, the PI's call (brief).

### §2.4 The Biomarkers heat map — `Client/src/views/Reports/Biomarkers/BiomarkerHeatmapGrids.js`
- `PlotlyHeatmap` (line ~268): Plotly `heatmap` trace, x = 22 band centres (labelled every 3rd),
  y = lengths of signal (category axis, reversed), diverging colour scale centred on 0 for r and
  on 0.5 for AUC (`divergingColorscale`, Okabe-Ito blue/vermillion from `binarizationModel`),
  xgap/ygap 1.5, no colour bar, hover "r = … / AUC = …", open circle on the best-of-ten cell where
  the family-wise flag is true. Drawn through `PlotlyRenderManager` then `Plotly.react` with the
  mode bar off.
- `ContactStrip` (line ~483): thumbnails sorted by `contactSortKey`: LEFT before RIGHT, then by
  contact digits (0-2, 0-3, 1-3). Label = server's `display_short` ("L 0⁻2⁺") + `display_region`.
- The server writes `display_short/region/hemisphere/contacts` into EVERY sweep
  (`bravo_service.py` ~7445, via `analytics.format_channel`), and the Closed-Loop adapter passes
  each sweep through whole (`dict(sweep)`, adapter.py ~591) — so the CL grid payload ALREADY
  carries the full `correlation_grid`, `auc_grid`, `center_freqs_hz`,
  `integration_seconds_delivered` and the Medtronic labels. The new heat map needs no backend
  change for its data or its labels. (Confirm on the live payload once OrbStack is up.)
- "Turned 90 degrees" therefore means: band centres run down the y axis (22 rows), and the x axis
  is either the lengths of signal (the full grid, as Biomarkers has it) or just two columns, r and
  AUC (the best-of-lengths values the table shows today). Design question — put both to the PI.

### §2.5 "SIGN COHERENT" — `stateTracks.js` ~line 108
The track label is "Sign coherence" (rendered upper-case by StateTrack), cells "COHERENT" /
"NOT COHERENT" / "NOT ESTABLISHED"; drawn by `EvidenceTrianglePanel.js` line ~497 and read by
`WhatWouldChangeThis.js`. Payload field is `coherence.coherent` (adapter.py ~1256/1283) — the
rename is display-only; the field name stays. Proposed: label "Sign agreement", cells
"SIGNS AGREE" / "SIGNS DISAGREE" / "NOT ESTABLISHED".

### §2.6 The device rule ledger — `DeviceRuleLedger.js` (369 lines)
Every rule outcome in its bucket with a glyph per state; every bucket drawn even when empty. It
already imports `useState`, so a collapsed-by-default card with the bucket COUNTS in the header
(e.g. "51 rules: 44 satisfied · 1 violated · 4 could not be evaluated · 2 counted elsewhere") and
the rows behind a reveal is the natural shape — the counts stay visible, the rows fold.

### §2.7 Where the verbose text is (candidates for reveal/hide), by panel
- index.js: page subtitle; "no band committed" card; BandCandidateIdentity note under the badge;
  analyst-fold caption. (Discovery-stage statistics block: PI said never hide it.)
- BandSweepGridPanel: the 4-line caption about the 51-rule screen.
- ThreeSourceResponsePanel: headline + subtitle + three captions + "rest of the spectrum" caption
  + footer + "informative only" line — seven text blocks around two figures.
- DeviceRuleLedger, EvidenceTrianglePanel (502 lines), WhatWouldChangeThis (281), Prescription
  (714), DutyCycle (447): each carries explanatory captions; to be listed with line refs in Phase 2.

### §2.8 Environment at session start
OrbStack is not running: `docker ps` cannot reach the daemon and the bridge job returned no result
in 30 s (heartbeat 8,463 s old). The live page, the container test suite and the workers' HUP all
need it. Host suite and the frontend build do not.

## §3 The design put to the PI on 2026-09-11 (mock-up: scratchpad/cl_redesign_mockup.html;
## artifact https://claude.ai/code/artifact/b4c4022a-7cbd-459d-810e-7499f65b8bbc)
New page order: title + "Choose a band" (contact tabs L then R in Medtronic notation; heat map with
22 band rows, columns r | AUC | clears-correction symbol | stable-across-settings symbol | one
"Use this band" radio per row, header written once) → verdict header ("Sign agreement" track) →
what would change this (prose folded) → device rules (counts + violated rows visible, ledger
folded) → evidence triangle + stability (method text folded) → parameters + duty cycle + committed
band (statistics visible, method folded) → three-source panel (new title; column titles Time domain
derived LSB / PSD derived LSB / Direct LSB recording; two tabs by ramped side, pooled over visits;
one-line captions; spectrum row and footer folded) → analyst fold → sign-off card.
Questions asked (answers become decisions):
1. Heat map second axis: two columns (r, AUC — recommended) or the full 22×10 grid turned.
2. Tick box = commit, one at a time (radio).
3. "Sign agreement" vs "sign concordance".
4. Ledger folded: keep violated rows visible (drawn) or counts only.
5. Pooled three-source points: (a) build every run per load (~32 s cold) or (b) store per-run
   points beside the pooled table (recommended).
6. Evidence-triangle current→power edge from the pooled view: pooled slope of the stored row
   (recommended) or keep today's single-run edge.
7. Closed-loop simulation design (old item 9): after this lands, or its own plan.

## §4 The PI's answers, 2026-09-11 (decisions 1–7 in task_plan.md)
Overall "looks good (color, orientation)". r and AUC columns 2x wider using the right-hand white
space. One tick at a time. "Sign agreement". Ledger: violated rows stay visible when folded.
"Parameters to transcribe" -> plain language ("How to select a threshold" / "Full parameter
selection" / "Full parameter recommendation" offered). Q5: option B (store per-run points beside the
pooled table). Q6: deeper work — swarm literature research on stimulation amplitude vs LFP power;
descriptive analysis of existing data; the relationship is inverted-U (sometimes M-shaped); focus on
finding the peak. Q7: simulation design at the very end.

## §5 RCS08 capture for the amplitude-vs-power analysis (probe_amp_power_capture.py, 2026-09-11)
- 11 runs found, 11 built, 0 failed, **3.7 s for all of them** with the tile cache warm (the 32.5 s
  in decision 103 was a cold build that also derived and stored the pooled table). So option (a)
  "build every run per load" is cheap when warm; the PI chose (b) anyway — tell him the number.
- Every run: the device's own FFT route has 0 settled points (the device only computes it on a
  button press or a survey, never while current is stepped — the clinic note already says so). On
  this participant the "PSD derived LSB" column will always read "no settled value".
- Runs by side and sensing contact (currents with a settled time-domain value):
  RIGHT, all on ZERO_THREE_RIGHT: 2026-08-18 @55 Hz [1.0,1.5]; 2025-10-21 @145 Hz [2.0..3.5];
  2025-10-02 @55 Hz [3.0]; 2025-10-02 @110 Hz [2.0,2.5]; 2025-09-04 @110 Hz [2.5,3.0]; 2025-09-04
  @110 Hz [1.0] -> 12 points, 4 visits, THREE stimulation rates.
  LEFT, ONE_THREE_LEFT: 2026-08-18 @55 Hz [1.0..3.5] (6); 2025-09-04 @110 Hz [2.5]; 2025-08-21
  @110 Hz [2.5..4.0] (4) and [1.0,1.5] (2) -> 13 points, 3 visits. LEFT, ZERO_TWO_LEFT: 2025-08-21
  @110 Hz [1.0..3.0] (5) -> 1 visit.
- The programmed (device-sensed) centre differs run to run (7.81, 23.44, 9.77, 12.7, 11.72, 10.74
  Hz), so the direct-LSB route is only comparable across runs that sensed the same band. The
  time-domain route carries all 22 centres for every run, which is what decision 55's pooled table
  (294 rows, 194 assessed) is built from. **Design consequence for Phase 5**: a side's tab must be
  drawn at ONE band centre (the committed band's, or a picker), pooling the time-domain points of
  every run on ONE sensing contact (never across contacts, decision 74); the direct-LSB points are
  overlaid only for runs whose programmed centre matches. The left side has two sensing contacts
  with runs, so that tab needs a contact choice. Put to the PI with the research synthesis.
- Files (container, disposable): _agent_bridge/_probe_tl/amp_power_runs.csv (3,001 rows),
  amp_power_runs_meta.json, amp_power_pooled_stored.csv (the stored pooled table).

## §6 RCS08 shape analysis (probe_amp_power_shape.py, 2026-09-11, 14.7 s; outputs
## _agent_bridge/_probe_tl/amp_power_shape.csv, amp_power_per_run.csv)
Time-domain route, whole-range rows (97 centres x 3 contacts = 291 contact-centre pairs, 2,910
points); log power on current with one intercept per run (decision 55's grouping), never across
contacts.
- Points per contact: ONE_THREE_LEFT 13 (4 runs, 3 visits, 2 rates, 1.0–4.0 mA); ZERO_THREE_RIGHT
  12 (6 runs, 4 visits, **3 stimulation rates**, 1.0–3.5 mA); ZERO_TWO_LEFT 5 (1 run) — not fittable.
- 194 pairs fittable (>= 8 points, >= 4 distinct currents). Quadratic beats the straight line
  (F test p < 0.05) in **1 of 194**: ZERO_THREE_RIGHT at 72.5 Hz (outside 8–30 Hz), fitted peak
  3.4 mA, bootstrap 95% interval 2.85–25.9 mA — the peak is not pinned down. Expected by chance at
  p < 0.05 over 194 tests: about 10.
- The stored pooled table (decision 55/103's own cluster-robust model): 194 assessed rows, **9 with
  p_curvature < 0.05 (4.6%, the chance rate)**, 4 with a peak inside the tested range — ONE_THREE_LEFT
  15.5 Hz (peak 3.0 mA, slope p 0.17), ZERO_THREE_RIGHT 68.5 / 69.5 / 90.5 Hz (2.6 / 3.1 / 3.3 mA).
  Only 15.5 Hz on ONE_THREE_LEFT is inside the adaptive sensing range. None would survive a
  correction for 194 tests.
- Per run (388 run-band series with >= 3 currents): the largest power sat at an interior current in
  146 (38%), 86 on bands free of a stimulation harmonic. With 3–6 currents per run the chance rate
  of an interior maximum is 33–67%, so 38% is not evidence of a rise-then-fall.
- Direct-LSB route: 4 runs with >= 3 settled readings; the device's own FFT route: 0 everywhere.
- Reading: on this record no band in 8–30 Hz shows an established bend; the data are 12–13 points
  per contact across 3–4 visits, at most 6 currents per run, and the right side mixes three
  stimulation rates. A peak cannot be estimated from it; a pooled straight-line slope can.

## §7 E1 from the pooled slope — before/after on RCS08 (probe_e1_before_after.py, 2026-09-11)
Report at ONE_THREE_LEFT 20.5 Hz with the swap off, then on: 56,796 fields before, 56,808 after,
55,696 in common, **12 changed** — 11 under `edges.E1` (estimate 4.58 → −3.62 device units per
mA; interval −15.1…24.3 → −23.2…15.9; p 0.648 → 0.726; n 37,878 samples in 66 setting epochs →
13 settled points in 4 runs; sign +1 → −1; both UNRESOLVED) and `coherence.observed_pattern.E1`.
The 15 fields only-after are `edges_historical.E1`, which equals the old E1 exactly; the 3 fields
only-before are the old edge's three named confounders. Verdict `blocked` both times; sign
agreement NOT ESTABLISHED both times. Log /tmp/claude-502/e1_before_after.log.
