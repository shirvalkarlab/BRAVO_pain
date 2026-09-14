# Task Plan: Closed-Loop Deployment page redesign

## Goal
Make the Closed-Loop Deployment page much shorter and easier to read, following the PI's brief of
2026-09-10 (findings.md §1, his words), with every visual change shown to him and approved before it
is built, and every built change proven in the served bundle and on the live RCS08 page.

## Next Step
NOTHING QUEUED. The redesign is complete and merged into `v3.1.0` (PR #10, merge `8e18f4bd`,
2026-09-11). Two follow-ups landed the same evening after the PI's questions: decision 130 (the
Biomarkers recording memos keyed on the recording set, so the daily ingest's rows are not served
stale) and decision 131 (the "Choose a band" card reads the same stored grid the Biomarkers page
shows and prints its score, match window, direction and split). Open on him: item 30 (the
titration protocol) and the second half of item 29 (moving the default branch).

## Current Phase
Phase 8 complete; all eight phases landed and pushed

## Phases

### Phase 1: Discovery — map the page as it is today
**Status:** complete
- [x] Find every panel on the Closed-Loop page in render order, its component file, and which
      backend payload feeds it (findings §2)
- [x] Read the calibrated grid table: columns today, which fields carry correlation, AUC,
      family-wise correction, cross-setting stability, and the "use this band" control
- [x] Read the Biomarkers heat map component (the one the PI wants copied, turned 90 degrees)
- [x] Read the three-source panel: its titles, its per-visit tabs, and where decision 55's pooling
      lives
- [x] Read DECISIONS_and_open_items.md: 65 (an uncorrected row stays selectable — the X is a label,
      never a gate), 67 (no device-rule column on the grid; the 51-rule screen is meaningless per
      band), 103 (pooled table stored from a full build only), 55 (pooling across visits)
- [x] Check the contact naming helper used by the Biomarkers thumbnails (Medtronic notation, order)

### Phase 2: Design — a mock-up the PI approves before any code
**Status:** complete
- [x] Load scientific-visualization, UI/UX (design critique) and scientific-writing skills
- [x] Draft the new page layout: grid heat map (bands vertical; columns correlation, AUC; symbols
      for family-wise correction and cross-setting stability; one tick box per row, label once)
- [x] Draft the contact tabs in Medtronic notation, ordered left-then-right as Biomarkers thumbnails
- [x] Draft the reveal/hide treatment for every verbose text block and the device rule ledger
- [x] Draft the renamed three-source panel with its two pooled tabs and concise captions
- [x] Show the mock-up to the PI (sent 2026-09-11; artifact
      https://claude.ai/code/artifact/b4c4022a-7cbd-459d-810e-7499f65b8bbc); his answers recorded as
      decisions 1–8 below; "overall looks good" taken as the go-ahead (told him so)

### Phase 3: Build — the grid heat map and its symbols
**Status:** complete
- [x] Heat map replaces the calibrated grid table; bands vertical; correlation and AUC columns,
      each TWICE the mock-up's width, using the card's right-hand white space (decision 1)
- [x] Family-wise correction symbol per row (X / checkmark)
- [x] Cross-setting stability symbol per row (yellow circle / red cross / green checkmark)
- [x] One "use this band" tick box per row, label written once at the top
- [x] Contact tabs in Medtronic notation, ordered left then right

### Phase 4: Build — collapse the text, rename the labels
**Status:** complete
- [x] Every verbose text block behind a reveal/hide control
- [x] Device rule ledger collapsible
- [x] "SIGN COHERENT" -> "Sign agreement" (decision 3)
- [x] "Parameters to transcribe" -> "Full parameter recommendation" (decision 4b)
- [x] Panel title -> "Stimulation amplitude effects on band power, measured three ways"
- [x] Three source titles -> "Time domain derived LSB", "PSD derived LSB", "Direct LSB recording"
- [x] Captions under the three panels rewritten concisely (scientific-writing skill)

### Phase 5: Build — the three-source panel pooled across visits
**Status:** complete
- [x] Backend: store each run's settled points (three routes) beside the pooled table once, read
      them on every request (decision 5, option B); equality proof on the pooled table (0 diff)
- [x] Frontend: drop the per-visit tabs; two tabs by ramped side, every visit's points overlaid,
      pooled fit from the stored table on the time-domain route
- [x] Evidence triangle: current->power edge = pooled slope of the stored row + curvature caveat
      (decisions 9, 11); a peak annotation only when established
- [x] Sign-off card and figure snapshots still find their sections after the layout change

### Phase 6: Research — stimulation amplitude vs LFP band power (decision 6)
**Status:** complete
- [x] Swarm literature research: four workers (A shape, B fitting, C artifact, D pain targets),
      artifacts/research_2026-09-11_amp_power_{A,B,C,D}_*.md; synthesis in
      artifacts/research_2026-09-11_stim_amplitude_vs_lfp_power.md
- [x] Descriptive analysis of RCS08's own runs (findings §5–§6): 1 of 194 pairs with a bend by
      the F test, 9 of 194 by the stored model (chance rate), none inside 8–30 Hz established
- [x] Recommendation written (synthesis §1): pooled straight-line slope per contact + curvature
      caveat; peak only as an annotation when established. PUT TO THE PI 2026-09-11; awaiting answer

### Phase 7: Prove, record, land

**Status:** complete
- [x] Frontend rebuilt; owned strings found in the served chunks (every phase, last: build e)
- [x] Watched live on RCS08 in the PI's own Chrome (every phase)
- [x] Container and host suites run and logged (counts from the log, not carried forward)
- [x] Decisions 122-129 in DECISIONS_and_open_items.md; handoff in progress.md; committed and
      pushed on PS_closedloop_deployment

### Phase 8: Closed-loop simulation module design (old item 9) — LAST, per the PI (decision 7)
**Status:** complete
- [x] Design written: artifacts/design_2026-09-11_closed_loop_simulation_module.md (three plant
      models M0/M1/M2 + run-resampled intervals, outputs, placement, seven tests, five questions)
- [x] The PI's answers to its §7 questions and his go-ahead (decisions 15-21 below)
- [x] Step 1: pooled fit returns the quadratic's coefficients (within_visit), additive
- [x] Step 2: stored pooled table carries them; POOLED_RULE_VERSION -> v2; view fields too
- [x] Step 3: StimOptimizer/routines/amplitude_response.py -- ResponseCurve (linear, quadratic +
      post-peak line), pure numpy, importable by every module
- [x] Step 4: DROPPED -- the simulation reads the 3 s pieces, not the report's series (the chronic
      series cannot resolve the ramp); the stash was removed again after the payload test caught it
- [x] Step 5: ClosedLoopDeployment/simulation.py -- M0/M1/M2 one loop, M3 run-resampled
- [x] Step 6: stored kind closed_loop_simulation; adapter write + read; bravo_service serves it
      alone on ClosedLoopSimulation: 1 (fetched after the first figures)
- [x] Step 7: tests/test_simulation.py (design §6's seven + coefficients + regridding + per-candidate read)
- [x] Step 8: host 1053 passed / 42 skipped / 0 failed; container 626 / 0 (13:44-13:46, settled code);
      M0 vs the replay on the same 114 stretches: 5 fields, 0 differing
- [x] Step 9: load bravo-stimoptimizer-figures, tufte-viz, tufte-test, ps-plotly BEFORE drawing
- [x] Step 10: card "CL-DBS simulations" after the sign-off card; cl-duty card removed; visual-first
- [x] Step 11: bundle (main.8a55.. + chunk 761), HUP, watched live in the PI's Chrome, decisions 128-129, committed, pushed

## Decisions Made
| # | Decision | Rationale |
|---|---|---|
| 1 | Heat map = two colour columns (r, AUC), 22 band rows; r and AUC columns twice the mock-up's width, filling the card's right-hand space | PI 2026-09-11: "looks good (color, orientation)"; "make R and AUC bands 2x wider; use right-side whitespace" |
| 2 | The tick box commits the band; one at a time; ticking another row moves it | PI: "agree with one tick at a time" |
| 3 | Track renamed "Sign agreement" (SIGNS AGREE / SIGNS DISAGREE / NOT ESTABLISHED) | PI: "Sign agreement = OK" |
| 4 | Device rule ledger folds; violated rows stay visible when folded | PI: "keep R shown; remain visible when folded" |
| 4b | "Parameters to transcribe" -> "Full parameter recommendation" | PI asked for plain language and offered three; this one names what the panel is |
| 9 | Evidence triangle's current->power edge = the pooled straight-line slope per sensing contact (stored table), with the curvature answer as a caveat; a peak only as an annotation once established | PI 2026-09-11: "Accept the pooled slope recommendation" |
| 10 | Pooled three-source points: option (b) stands (store per-run points beside the pooled table) even though a warm full build measured 3.7 s | PI: "keep option b" |
| 11 | STANDING EXPECTATION: the analysis will very likely have to identify the response peak and model the post-peak descent (decision 55's second fit); build so that pivot is cheap | PI: "High likelihood we must model or identify the response peak ... model the post-peak descent ... be prepared to pivot" |
| 12 | The pooled line's anchor = the mean of the per-run centroids in linear device units (each run counts once) | The pooled model has one baseline per run and no single intercept; per-run centroids match its grouping. Implemented by me at the PI's instruction ("you implement everything") |
| 13 | The pooled view is a separate request (`ThreeSourcePooled: 1`) fired after the report's data arrives, cached under its own slot | PI: "prefetch the data after the first figures load" |
| 14 | A missing points table for the current recording set forces a full build of every run | Without it the steady-state page refused to write the table forever (first live probe) |
| 8 | The grid panel commits the SWEEP's own hemisphere (display_hemisphere), not the previously committed band's | Found while rebuilding: index.js passed `bc.hemisphere` down, so a right contact picked while a left band was committed would have been committed as "Left" |
| 5 | Pooled three-source view: store each run's points beside the pooled table once, read them back | PI chose option B over rebuilding every run per page load (32 s cold) |
| 6 | Evidence-triangle input from the pooled view is NOT decided; needs a literature swarm + descriptive analysis of the amplitude-vs-power shape (inverted-U / M) first; the triangle keeps today's edge until then | PI: "needs deeper work ... focus on identifying the peak of the inverted-U" |
| 7 | Closed-loop simulation design goes last, after everything else | PI: "do at the very end" |
| 15 | M1's settling time: the measured response latency where a run supports it, else the 30 s settled window | PI 2026-09-11, §7 Q1: "Default measured when available; else 30s" |
| 16 | Amplitude limits held to the capture range, as the replay does | PI, Q2: "agree hold, keep module capturing range like replay" |
| 17 | Wrong-side-of-the-peak time is a number with a warning line; it blocks nothing | PI, Q3: "numeric value + a warning threshold/value (no blocker)" |
| 18 | M3 (run-resampled intervals) runs on every page load | PI, Q4: "report if low-cost; show M3 on every page" (11 runs on RCS08 is cheap) |
| 19 | A NEW card "CL-DBS simulations" at the bottom after the sign-off card; the duty-cycle ("replay analysis") card above is removed because M0 replicates it | PI: "add new card at bottom after deployment ... remove existing replay analysis outputs/card sections above since M0 will replicate it" |
| 20 | The card is visual-first: plots and diagrams wherever possible, minimal caption text; the sign-off card's simulation section likewise | PI: "Critical: apply scientific visualization ... Replace text outputs with plots/images/diagrams wherever possible" |
| 22 | The simulation's series is the 3 s voltage-trace pieces (every recording on the contact), put on the device's 3 s clock per stretch, NOT the report's chronic series | the chronic series (230 s apart) cannot resolve the 150 s ramp, which is why the old duty-cycle card said "not answerable"; the pieces resolve it 50x over and are the same calibrated quantity the thresholds sit on; jitter inside a recording refused 33 of 43 stretches until regridded |
| 23 | The stored kind cites its RAW roots (tiles), like the pooled table, so it is released to every module including closed_loop; a chain naming the exploration ladder is the refused case | the refusal fires when the CONSUMER's own output is in the chain; citing the pooled entry itself would have refused it to closed_loop |
| 24 | One stored simulation per candidate band (KEEP_NEWEST_BY_KIND = 6) and the read-back matches the sidecar's candidate tag; the page sends its candidate with the fetch | met live: the page's own report (L 0-2+ at 24.5 Hz) evicted the probe's entry and the newest-of-any read served the wrong band -- the decision-107 defect again |
| 21 | The plant is a pluggable RESPONSE CURVE (power offset = g(amp_sim) - g(amp_obs)); linear today, quadratic + post-peak line when a bend is established; the pooled table stores the quadratic's coefficients so the switch needs no schema change; the curve lives in a pure-numpy StimOptimizer routine so Biomarkers can import it later | PI: "make this flexible so we can later incorporate the bend ... for Biomarkers"; the per-run baseline cancels in the difference, which is what makes M0 the exact zero-curve case |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
