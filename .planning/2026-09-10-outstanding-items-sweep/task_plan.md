# Task Plan: Outstanding items sweep

## Goal
Work the outstanding-items list of 2026-09-10 in the PI's order ("start with number one, then
two, three, etc."), each item proven on live data or in the served bundle before the next starts.

## Next Step
Item 1: snapshot the Plotly figures on the Closed-Loop Deployment page into the "Deploy-to-Percept
review" card on Print and into the JSON export — in the browser, so no container is needed.

## Current Phase
Phase 1

## Phases

### Phase 1: Pictures in the sign-off card
**Status:** in_progress
- [x] `figureSnapshots.js`: find the drawn Plotly figures (and the evidence panel's SVGs) under the named page sections, image each
- [x] Card: capture before Print, embed in the card for the print stylesheet, carry in Export JSON
- [x] Rebuild; strings present in the served chunk (703.9c3946c8.chunk.js)
- [ ] Watch it work in the browser (PI signs in; Print and Export pressed live)

### Phase 2: Timeline circle equals spectrum point — a live test
**Status:** pending

### Phase 3: Labelling and navigation tidy-ups on the Closed-Loop page
**Status:** pending

### Phase 4: The permanently failing host test made honest
**Status:** pending

### Phase 5: Shared matching step — migrate the four call sites, one at a time
**Status:** pending

### Phase 6: Closed-loop simulation module design; housekeeping (worktrees, .mcp.json)
**Status:** pending

## Decisions
| # | Decision | Why |
|---|---|---|
| 1 | Figures are snapshotted in the BROWSER with Plotly.toImage, not exported on the server | The figures only exist as drawn Plotly divs; the server-side image tool is what was broken, and it is not needed |
| 2 | PI chose the four sections: ROC, band power in device units, three-source response, evidence links; the per-week refit is left off | His call on what belongs on a signed record; `cl-evidence` is SVG so the helper serialises SVG as well as Plotly |

## Errors
| Error | Attempt | Resolution |
|---|---|---|
