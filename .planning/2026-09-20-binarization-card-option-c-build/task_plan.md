# Task Plan: Binarization card, option C, built

## Goal
Build option C (the PI, 2026-09-21): coverage sentence without its second clause; Plotly timing histogram, translucent bars per source, x-axis tied to the window slider with 25% greyed tails, direction-aware; control stack keeps per-report cap, gap, 'time domain signal', reuse as 'none / allow reuse', REDCap-only vs +clinic; the binarized histogram and its cards unchanged. Then fix the sharing warning's false 'no cap', review the matching path for dead code, and read every card sentence for concision.

## Next Step
Watch the card on the served page once the PI has logged in; then the decision row for option C and the review, and the push.

## Current Phase
Phase 3

### Phase 1: Sentence and the sharing warning
- [x] Coverage sentence: bold clause only (jest)
- [x] `align_pros` honours the page's MaxPerRating (sessions per report, nearest first); the warning names the cap; no "no cap is applied" (container tests, live counts)
- **Status:** complete

### Phase 2: Option C on the page
- [x] `TimingHistogram.js`: Plotly, overlay bars with alpha per source, x range ±1.25 window, tails greyed, direction-aware (prior hides the after-side colour), tests on a fixture
- [x] Section layout: top band (sentence, window + Split + direction, histogram); below left the restyled control stack; right the existing binarized histogram unchanged; rebuild; chunk proof (482.af03041e)
- **Status:** complete

### Phase 3: Review
- [x] Backend: the unread per-report band-power value (`pro_lsb`) and its 60-minute tolerance helper deleted; one reader for the cap and gap; every Compute field checked as read; 249,322 fields in common, 0 differing, 128,311 removed
- [x] Front end: every sentence on the card's band and left column read and reworded; the preview's readouts untouched by instruction; render tests updated
- [ ] Decision rows; push
- **Status:** in_progress

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The session matcher takes the page's per-report cap | the PI: the page says no reuse and a cap of 3, so a warning saying "no cap" is an error |
| This plan runs in inject-smart autonomous mode, attested | decision 223 (the PI, 2026-09-21): autonomous with attestation allowed on any plan, never gated |
| Report-first stays two-sided on the histogram | the matcher on both sides claims samples either side of a report; only "Before the report" is one-sided |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
