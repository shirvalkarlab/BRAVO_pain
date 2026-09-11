# Task Plan: Closed-Loop Deployment page redesign

## Goal
Make the Closed-Loop Deployment page much shorter and easier to read, following the PI's brief of
2026-09-10 (findings.md §1, his words), with every visual change shown to him and approved before it
is built, and every built change proven in the served bundle and on the live RCS08 page.

## Next Step
Phase 5, the pooled three-source view, under decisions 9–11: backend first (store each run's
settled points beside the pooled table, option b; equality proof on the pooled table), then the
two side tabs drawn at the committed band's centre on one sensing contact (the left side needs a
contact choice — put the drawing to the PI before building the frontend). Phases 3, 4 and 6 are
landed in commit <see progress.md handoff>.

## Current Phase
Phase 5

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
**Status:** in_progress
- [ ] Backend: store each run's settled points (three routes) beside the pooled table once, read
      them on every request (decision 5, option B); equality proof on the pooled table (0 diff)
- [ ] Frontend: drop the per-visit tabs; two tabs by ramped side, every visit's points overlaid,
      pooled fit from the stored table on the time-domain route
- [ ] Evidence triangle: current->power edge = pooled slope of the stored row + curvature caveat
      (decisions 9, 11); a peak annotation only when established
- [ ] Sign-off card and figure snapshots still find their sections after the layout change

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

**Status:** pending
- [ ] Frontend rebuilt; owned strings found in the served chunks
- [ ] Watched live on RCS08 with the PI; before/after screenshots in findings
- [ ] Container and host suites run and logged (counts from the log, not carried forward)
- [ ] Decisions and open items added to DECISIONS_and_open_items.md; handoff written; committed
      and pushed on PS_closedloop_deployment

### Phase 8: Closed-loop simulation module design (old item 9) — LAST, per the PI (decision 7)
**Status:** pending
- [ ] Design against the BandCandidate contract; put to the PI before any code

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
| 8 | The grid panel commits the SWEEP's own hemisphere (display_hemisphere), not the previously committed band's | Found while rebuilding: index.js passed `bc.hemisphere` down, so a right contact picked while a left band was committed would have been committed as "Left" |
| 5 | Pooled three-source view: store each run's points beside the pooled table once, read them back | PI chose option B over rebuilding every run per page load (32 s cold) |
| 6 | Evidence-triangle input from the pooled view is NOT decided; needs a literature swarm + descriptive analysis of the amplitude-vs-power shape (inverted-U / M) first; the triangle keeps today's edge until then | PI: "needs deeper work ... focus on identifying the peak of the inverted-U" |
| 7 | Closed-loop simulation design goes last, after everything else | PI: "do at the very end" |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
