# Task Plan: Calibration usage audit and acquisition timeline without pain matching

## Goal
Two audits (the PI, 2026-09-20): every use of a calibration constant is on raw power and every LSB is derived
the right way; every stored time-domain or device-FFT value is LSB before storage; the top Biomarkers timeline
drops pain-report matching for a fast acquisition timeline. Fix confirmed errors test-first, one at a time.

## Next Step
All five done (213-217). Nothing queued. For the PI: the clinic implication of 217 (L 0-3+ needs L C+1-2-); the stale-constant comments (audit A item 6); audit B's per-recording tile value (not built).

## Current Phase
Phase 3

### Phase 1: Audits (two read-only sub-agents)
- [x] A: every reader of `LSB_PER_UV2_TRANSFORM` / `LSB_PER_DEVICE_PSD` / the frozen model traced; input unit and scale stated; TD route uses the transform, device-FFT route the bridge; stale literals and contradicting comments listed
- [x] B: every stored product carrying converted band power inventoried (unit, convert-before-store, constant in key, no rating); the timeline's matching step costed and its consumers named; acquisition-timeline design keyed on the recording set
- **Status:** complete

### Phase 2: Verify and fix (his order, test-first, one commit each)
- [x] 0a/0b: join recordings across a short restart; both legs measured; leg tagged; rule versions bumped; live proof; decision 213
- [x] 1: the 0.146-scaled cross-check on the Closed-Loop "LSB & power" card -- decision 214; the independent pairing gives 0.98× the constant
- [x] 2: the constants and a rule version in the Closed-Loop `inputs` key -- decision 215; the stale entry was live
- [x] 4: the flanking-pair rule on the readiness screen, per lead from the cathode in force -- decision 217; usable 11 -> 0
- [x] 5: the margin switch STAYS OFF by the PI's ruling (use as much data as we can); recorded in 217, no code flip
- **Status:** complete

### Phase 3: Acquisition timeline (the PI: "go all")
- [x] Endpoint keyed on the recording set and the constants; the raw kind `acquisition_timeline`; the sample index on its own endpoint
- [x] Timeline component reads it; matching removed; jest source tests; rebuild; timings beside the equality proof; zero writes on a report; decision 216
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Sub-agents audit read-only; fixes by the main session | two agents editing the one live mount collide; every fix needs tests, a live proof and one commit |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
