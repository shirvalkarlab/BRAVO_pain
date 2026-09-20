# Task Plan: Calibration usage audit and acquisition timeline without pain matching

## Goal
Two audits (the PI, 2026-09-20): every use of a calibration constant is on raw power and every LSB is derived
the right way; every stored time-domain or device-FFT value is LSB before storage; the top Biomarkers timeline
drops pain-report matching for a fast acquisition timeline. Fix confirmed errors test-first, one at a time.

## Next Step
His order (2026-09-20): 0a joined recordings + 0b both legs DONE (213). Next: item 1 the 0.146 cross-check;
2 the constants in the Closed-Loop `inputs` key; 3 the acquisition timeline; 4 the sandwich rule on the
screen; 5 flip the 20 s margin switch.

## Current Phase
Phase 2

### Phase 1: Audits (two read-only sub-agents)
- [x] A: every reader of `LSB_PER_UV2_TRANSFORM` / `LSB_PER_DEVICE_PSD` / the frozen model traced; input unit and scale stated; TD route uses the transform, device-FFT route the bridge; stale literals and contradicting comments listed
- [x] B: every stored product carrying converted band power inventoried (unit, convert-before-store, constant in key, no rating); the timeline's matching step costed and its consumers named; acquisition-timeline design keyed on the recording set
- **Status:** complete

### Phase 2: Verify and fix (his order, test-first, one commit each)
- [x] 0a/0b: join recordings across a short restart; both legs measured; leg tagged; rule versions bumped; live proof; decision 213
- [ ] 1: the 0.146-scaled cross-check on the Closed-Loop "LSB & power" card
- [ ] 2: the constants and a rule version in the Closed-Loop `inputs` key
- [ ] 4: the sandwich rule on the readiness screen (a pair containing the stimulating contact is never offered)
- [ ] 5: `USE_POST_RAMP_MARGIN` ON, with the 9/16 session as the evidence
- **Status:** in_progress

### Phase 3: Acquisition timeline (after the PI's go-ahead)
- [ ] Endpoint keyed on the recording set alone (no report digest, no rating); reuses the per-recording LSB index
- [ ] Timeline component reads it; matching removed from this endpoint; jest fixture test; rebuild; alternating timings beside the equality proof of what did not move
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Sub-agents audit read-only; fixes by the main session | two agents editing the one live mount collide; every fix needs tests, a live proof and one commit |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
