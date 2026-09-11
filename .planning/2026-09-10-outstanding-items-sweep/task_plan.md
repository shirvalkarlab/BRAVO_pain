# Task Plan: Outstanding items sweep

## Goal
Work the outstanding-items list of 2026-09-10 in the PI's order ("start with number one, then
two, three, etc."), each item proven on live data or in the served bundle before the next starts.

## Next Step
Nothing queued. Open on the PI: cap sessions per report in the time-domain lane (decision 118);
the default-branch question (open item 29). Phase 7 waits for its own session. The Phase 5 window question is settled by decision 120 (one window for the page); the cap question stays open. **The PI will open a NEW session for Phase 7, the
Closed-Loop page redesign; his brief is in findings.md §3 and must be read first there.**

## Current Phase
Phase 10 — done; nothing queued

## Phases

### Phase 1: Pictures in the sign-off card
**Status:** complete
- [x] `figureSnapshots.js`: find the drawn Plotly figures (and the evidence panel's SVGs) under the named page sections, image each
- [x] Card: capture before Print, embed in the card for the print stylesheet, carry in Export JSON
- [x] Rebuild; strings present in the served chunk (703.16e31572.chunk.js after the display-size fix)
- [x] Watched live on RCS08 (PI signed in): Print -> 11 pictures in the card, print called once after
      they were in the document; Export JSON -> 567 KB file with the 11 pictures; fold closed -> 6
      pictures and the two folded sections named as NOT ON THIS RECORD

### Phase 2: Timeline circle equals the per-rating LSB value at its centre — a live test
**Status:** complete
- [x] Measured first: 240 of 240 circles (TD or bridge tier) equal the spectrum at the same centre,
      bit for bit, across all 12 sensing contacts on RCS08
- [x] `test_timeline_circle_equals_spectrum_point.py`: constructed identity, the native-tier
      exclusion pinned as a rule, and a live RCS08 test that skips when the participant is absent
- [x] Container 636 passed, 0 failed (+3)
- [x] THEN, at the PI's direction, the many-centre function and the test deleted (decision 115):
      container 626/0, host 1018 passed / 42 skipped / 1 known failure

### Phase 3: Labelling and navigation tidy-ups on the Closed-Loop page
**Status:** complete
- [x] Folded into Phase 7, which redesigns the same page; polishing labels first would be thrown away

### Phase 4: The permanently failing host test made honest
**Status:** complete
- [x] Root cause found by measuring: the old test's override=None survived into the fixture's
      teardown, whose clear_shared_cache() then wiped the PRODUCTION closed_loop cache on every run
- [x] Fixed through the store's off switch alone; old test 2->0 files, new test 2->2, full suite 2->2
- [x] Host 1019 passed / 42 skipped / 0 failed -- first fully green host run in the container

### Phase 5: Shared matching step — migrate the four call sites, one at a time
**Status:** complete
- [x] B4 `build_pooled_detail_from_matrix` (streaming_psd): 9 combos x 7,600,506 fields, 0 diff;
      page 1,018,093 fields, 0 diff. Decision 117.
- [x] B1 `align_pros(target="session")`: found already migrated in 38371d6b (2026-09-08),
      max_per_rating=None; proven through decisions 77/79 and today's page proof. Decision 118.
- [x] B2/B3 assessed: per-rating WINDOW SELECTORS, not sample->report matchers; forcing them onto
      the shared step would be a re-derivation. They stay. Decision 118.
- [x] Independence gap measured: align_pros 60-min window -> 39 reports claimed by >1 session
      (263 sessions, max 24); per_pro_lsb sharing at most 2 pairs per contact. Cap decision -> PI.

### Phase 6: Closed-loop simulation module design; housekeeping (worktrees, .mcp.json)
**Status:** complete
- [x] Three stale agent worktrees at 39dfb2f8 removed; root cause (default branch = v3.1.0) is the
      PI's call, recorded as open item 29
- [x] `.mcp.json` ignored (local tool configuration)
- [x] Closed-loop simulation design deferred to the Phase 7 session, which redesigns that page

### Phase 7: CL closed-loop page redesign — NEXT SESSION, the PI's brief of 2026-09-10
**Status:** pending
The page is far too long and must be distilled. Full brief with his words in findings.md §3. Load
the scientific-visualization and UI/UX skills before designing. In his order:
- [ ] Replace the calibrated grid table at the top with a heat map like the Biomarkers one, turned
      90 degrees so band centres run vertically; columns: correlation, AUC (not "high vs low")
- [ ] Family-wise correction as a symbol per row: X if it does not clear, checkmark if it does
- [ ] Cross-setting stability as a symbol: yellow circle "cannot tell", red cross "behaves
      differently", green checkmark "behaves the same"
- [ ] One "use this band" control (a tick box per row), the label written ONCE at the top, not on
      every row
- [ ] Contact tabs in Medtronic notation (L 1⁻3⁺, L 0⁻3⁺ ...), ordered left-then-right as the
      Biomarkers thumbnails are
- [ ] Every verbose text block behind a reveal/hide control (dropdown or expander)
- [ ] The device rule ledger collapsible
- [ ] Rename "SIGN COHERENT" -> "sign agreement" / "sign concordance"
- [ ] Rename "How stimulation current moved band power, measured three ways" ->
      "Stimulation amplitude effects on band power, measured three ways"
- [ ] The three source titles inside that panel become exactly: "Time domain derived LSB",
      "PSD derived LSB", "Direct LSB recording" (today: "from the voltage trace", "from the device's
      own spectrum", "from the device's own band power")
- [ ] The text under those three panels made much more concise, using the ps-scientific-writing
      skill
- [ ] Three-source panel: drop the per-visit tabs; two tabs only, right-side amplitude change and
      left-side amplitude change, each pooled across all visits (decision 55's pooling)
- [ ] THEN decide what calculation feeds the evidence triangle from the pooled view — undetermined


## Decisions
| # | Decision | Why |
|---|---|---|
| 1 | Figures are snapshotted in the BROWSER with Plotly.toImage, not exported on the server | The figures only exist as drawn Plotly divs; the server-side image tool is what was broken, and it is not needed |
| 3 | The calibrated grid gets its own cache slot (`CL.grid`) instead of sharing `CL.report` | One answer per slot per participant; sharing meant the grid's empty-candidate reply was shown as the report for a chosen band. Watched live. |
| 4 | Stale gunicorn workers are reloaded with SIGHUP, not worked around | Two workers were running code from before decisions 100 and 111; a fresh process imports cleanly, so the code is right and the process was old |
| 2 | PI chose the four sections: ROC, band power in device units, three-source response, evidence links; the per-week refit is left off | His call on what belongs on a signed record; `cl-evidence` is SVG so the helper serialises SVG as well as Plotly |

## Errors
| Error | Attempt | Resolution |
|---|---|---|

### Phase 8: QUEUED BY THE PI 2026-09-10 — the "data available to binarize" count does not update
**Status:** complete
His words: "check code for biomarkers module next to 'data available to binarize' - numbers read:
599 PRO reports across 315 days (this needs to autoupdate, but doesnt look like it does....)".
The availability payload on the same day carried 764 ratings, so the 599 is stale somewhere:
either a held/cached count, a different filter (metric-filtered vs all), or a value built once.
- [x] `BinarizationPreview.js` header caption; counts reports carrying the SELECTED score
- [x] 599/315 = Left Leg VAS (and Back VAS); 764/373 = NRS/VAS/Relief. Not stale -- unlabelled.
- [x] Score named in both captions + "764 reports in the record"; watched switching NRS -> Left Leg
      VAS on the live page. Decision 119.

### Phase 9: DECIDED BY THE PI 2026-09-10 — one match window for the whole Biomarkers page
**Status:** complete
- [x] "Timeline's own match window" slider removed; circles follow the main tolerance slider
- [x] Measured before: 120 s -> 60 min gives 345 -> 790 circles; after: live page returns 790
- [x] Container 626/0; bundle rebuilt; workers reloaded. Decision 120.

### Phase 10: DECIDED BY THE PI 2026-09-10 — heat maps: no dashes; snapshots honour the length axis
**Status:** complete
- [x] Snapshot route counts ceil(N/30) snapshots per row, or contributes nothing (availability.py)
- [x] Dash markers + per-cell hover sentence removed; caption and drawer bullet reworded
- [x] Before/after on RCS08: 36,406 fields, 11,694 differ; 0 on the two contacts with no snapshot
      reports; ZERO_THREE_RIGHT 5-min row 451 -> 140 reports. Four tests rewritten. Container 626/0.
- [x] Watched live. Decision 121.
