# Task Plan: Outstanding items sweep

## Goal
Work the outstanding-items list of 2026-09-10 in the PI's order ("start with number one, then
two, three, etc."), each item proven on live data or in the served bundle before the next starts.

## Next Step
Item 4: the permanently failing host test made honest. Item 3 is folded into Phase 7 (the
redesign of the same page) rather than polished now, per the PI ("go on to item 4"). **The PI will open a NEW session for Phase 7, the
Closed-Loop page redesign; his brief is in findings.md §3 and must be read first there.**

## Current Phase
Phase 4

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
**Status:** pending

### Phase 5: Shared matching step — migrate the four call sites, one at a time
**Status:** pending

### Phase 6: Closed-loop simulation module design; housekeeping (worktrees, .mcp.json)
**Status:** pending

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
